"""Unit tests for the Keycloak admin client.

Mocks httpx via MockTransport so we assert the exact request shape
(method, URL, params, body, auth header) without standing up a real
Keycloak. Token-fetch is intercepted on the same transport.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest

from asunset_core.auth import keycloak_admin
from asunset_core.auth.keycloak_admin import (
    KeycloakAdminError,
    UserAlreadyExistsError,
    create_user,
    find_user_by_email,
    generate_temporary_password,
    get_user,
    send_actions_email,
    set_temporary_password,
)


REALM = "asunset"
INTERNAL = f"http://keycloak:8080/auth/realms/{REALM}"
ADMIN_BASE = f"http://keycloak:8080/auth/admin/realms/{REALM}/users"


class _Settings:
    """Minimal duck-typed Settings — only the fields keycloak_admin reads."""

    keycloak_internal_issuer = INTERNAL
    keycloak_realm = REALM
    keycloak_api_client_id = "asunset-api"
    keycloak_api_client_secret = "test-secret"

    @property
    def keycloak_internal_base(self) -> str:
        return self.keycloak_internal_issuer.split("/realms/", 1)[0]


@pytest.fixture(autouse=True)
def _reset_token_cache() -> None:
    keycloak_admin._cache.token = None
    keycloak_admin._cache.expires_at = 0.0


def _install_transport(handler) -> None:
    """Patch httpx.AsyncClient so every instance routes through `handler`."""
    real = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    keycloak_admin.httpx.AsyncClient = factory  # type: ignore[attr-defined]


@pytest.fixture
def restore_httpx():
    real = httpx.AsyncClient
    yield
    keycloak_admin.httpx.AsyncClient = real  # type: ignore[attr-defined]


def _token_handler(captured: list[httpx.Request]):
    """Returns a handler that mints a service token on the
    /protocol/openid-connect/token endpoint and delegates everything
    else to the caller-provided dispatch."""

    def make(dispatch):
        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            if request.url.path.endswith("/protocol/openid-connect/token"):
                return httpx.Response(
                    200, json={"access_token": "kc-token", "expires_in": 60}
                )
            return dispatch(request)

        return handler

    return make


# --- find_user_by_email ----------------------------------------------


async def test_find_user_by_email_returns_first_match(restore_httpx) -> None:
    captured: list[httpx.Request] = []
    make = _token_handler(captured)

    def dispatch(req: httpx.Request) -> httpx.Response:
        assert req.method == "GET"
        assert req.url.path == f"/auth/admin/realms/{REALM}/users"
        assert req.url.params["email"] == "alice@example.com"
        assert req.url.params["exact"] == "true"
        assert req.headers["authorization"] == "Bearer kc-token"
        return httpx.Response(
            200,
            json=[{"id": "u-1", "email": "alice@example.com", "username": "alice"}],
        )

    _install_transport(make(dispatch))
    user = await find_user_by_email(_Settings(), "alice@example.com")
    assert user is not None
    assert user["id"] == "u-1"


async def test_find_user_by_email_returns_none_on_empty(restore_httpx) -> None:
    make = _token_handler([])
    _install_transport(make(lambda req: httpx.Response(200, json=[])))
    assert await find_user_by_email(_Settings(), "nobody@example.com") is None


# --- get_user --------------------------------------------------------


async def test_get_user_returns_dict(restore_httpx) -> None:
    make = _token_handler([])

    def dispatch(req: httpx.Request) -> httpx.Response:
        assert req.method == "GET"
        assert req.url.path == f"/auth/admin/realms/{REALM}/users/u-42"
        return httpx.Response(
            200, json={"id": "u-42", "emailVerified": True, "email": "x@y"}
        )

    _install_transport(make(dispatch))
    u = await get_user(_Settings(), "u-42")
    assert u is not None
    assert u["emailVerified"] is True


async def test_get_user_returns_none_on_404(restore_httpx) -> None:
    make = _token_handler([])
    _install_transport(make(lambda req: httpx.Response(404)))
    assert await get_user(_Settings(), "missing") is None


# --- create_user -----------------------------------------------------


async def test_create_user_returns_uuid_from_location(restore_httpx) -> None:
    make = _token_handler([])

    def dispatch(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        assert req.url.path == f"/auth/admin/realms/{REALM}/users"
        body = json.loads(req.content.decode())
        assert body["email"] == "bob@example.com"
        assert body["username"] == "bob@example.com"
        assert body["enabled"] is True
        assert body["emailVerified"] is False
        assert body["requiredActions"] == ["UPDATE_PASSWORD"]
        return httpx.Response(
            201,
            headers={
                "Location": f"http://keycloak:8080/auth/admin/realms/{REALM}/users/new-uuid-123"
            },
        )

    _install_transport(make(dispatch))
    uid = await create_user(
        _Settings(),
        email="bob@example.com",
        required_actions=["UPDATE_PASSWORD"],
    )
    assert uid == "new-uuid-123"


async def test_create_user_409_raises_user_already_exists(restore_httpx) -> None:
    make = _token_handler([])
    _install_transport(make(lambda req: httpx.Response(409, text="conflict")))
    with pytest.raises(UserAlreadyExistsError) as exc:
        await create_user(_Settings(), email="dup@example.com")
    assert exc.value.email == "dup@example.com"


async def test_create_user_other_4xx_raises_admin_error(restore_httpx) -> None:
    make = _token_handler([])
    _install_transport(make(lambda req: httpx.Response(400, text="bad request")))
    with pytest.raises(KeycloakAdminError):
        await create_user(_Settings(), email="x@y")


async def test_create_user_falls_back_to_email_lookup_when_no_location(
    restore_httpx,
) -> None:
    """If Keycloak doesn't return a Location header for some reason,
    create_user should still resolve the user's UUID by looking it up
    by email rather than crashing."""
    state = {"calls": 0}

    def dispatch(req: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if req.method == "POST":
            return httpx.Response(201)  # no Location header
        # The fallback find_user_by_email
        assert req.method == "GET"
        return httpx.Response(
            200, json=[{"id": "fallback-uuid", "email": "no-loc@example.com"}]
        )

    make = _token_handler([])
    _install_transport(make(dispatch))
    uid = await create_user(_Settings(), email="no-loc@example.com")
    assert uid == "fallback-uuid"


# --- send_actions_email ----------------------------------------------


async def test_send_actions_email_puts_with_correct_query(restore_httpx) -> None:
    captured: dict = {}

    def dispatch(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["client_id"] = req.url.params["client_id"]
        captured["lifespan"] = req.url.params["lifespan"]
        captured["actions"] = json.loads(req.content.decode())
        captured["auth"] = req.headers["authorization"]
        return httpx.Response(204)

    make = _token_handler([])
    _install_transport(make(dispatch))

    await send_actions_email(
        _Settings(),
        user_id="u-99",
        actions=["UPDATE_PASSWORD"],
        client_id="asunset-web",
        lifespan_seconds=86400,
    )
    assert captured == {
        "method": "PUT",
        "path": f"/auth/admin/realms/{REALM}/users/u-99/execute-actions-email",
        "client_id": "asunset-web",
        "lifespan": "86400",
        "actions": ["UPDATE_PASSWORD"],
        "auth": "Bearer kc-token",
    }


# --- set_temporary_password -----------------------------------------


async def test_set_temporary_password_puts_with_temporary_true(restore_httpx) -> None:
    captured: dict = {}

    def dispatch(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.content.decode())
        captured["auth"] = req.headers["authorization"]
        return httpx.Response(204)

    make = _token_handler([])
    _install_transport(make(dispatch))

    await set_temporary_password(
        _Settings(),
        user_id="u-77",
        password="StrongPass-1234!",
    )
    assert captured == {
        "method": "PUT",
        "path": f"/auth/admin/realms/{REALM}/users/u-77/reset-password",
        "body": {"type": "password", "value": "StrongPass-1234!", "temporary": True},
        "auth": "Bearer kc-token",
    }


async def test_set_temporary_password_raises_on_4xx(restore_httpx) -> None:
    make = _token_handler([])
    _install_transport(
        make(lambda req: httpx.Response(400, text="policy violation"))
    )
    with pytest.raises(KeycloakAdminError):
        await set_temporary_password(
            _Settings(),
            user_id="u-1",
            password="weak",
        )


async def test_send_actions_email_raises_on_5xx(restore_httpx) -> None:
    make = _token_handler([])
    _install_transport(
        make(lambda req: httpx.Response(503, text="smtp dead"))
    )
    with pytest.raises(KeycloakAdminError):
        await send_actions_email(
            _Settings(),
            user_id="u-1",
            actions=["UPDATE_PASSWORD"],
            client_id="asunset-web",
        )


# --- generate_temporary_password ------------------------------------


def test_generate_temp_password_meets_realm_policy() -> None:
    """The realm requires min 12 + lower + upper + digit + special.
    Run a sample so we'd catch any class-omission regression."""
    specials = "!@#$%^&*-_"
    for _ in range(200):
        pw = generate_temporary_password()
        assert len(pw) == 16
        assert any(c.islower() for c in pw), pw
        assert any(c.isupper() for c in pw), pw
        assert any(c.isdigit() for c in pw), pw
        assert any(c in specials for c in pw), pw


def test_generate_temp_password_respects_length_floor() -> None:
    with pytest.raises(ValueError):
        generate_temporary_password(length=8)


def test_generate_temp_passwords_are_unique() -> None:
    seen: set[str] = set()
    for _ in range(50):
        pw = generate_temporary_password()
        assert pw not in seen
        seen.add(pw)


# --- token cache -----------------------------------------------------


async def test_service_token_is_cached_across_calls(restore_httpx) -> None:
    """Two consecutive admin calls should fetch the token at most once
    while it's still well within its TTL."""
    state = {"token_calls": 0, "user_calls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/protocol/openid-connect/token"):
            state["token_calls"] += 1
            return httpx.Response(
                200, json={"access_token": "tok", "expires_in": 600}
            )
        state["user_calls"] += 1
        return httpx.Response(200, json=[])

    _install_transport(handler)

    await find_user_by_email(_Settings(), "a@x")
    await find_user_by_email(_Settings(), "b@x")
    assert state["token_calls"] == 1
    assert state["user_calls"] == 2


async def test_service_token_refreshes_when_expired(restore_httpx) -> None:
    """If the cached token's TTL has elapsed, the next admin call
    should refresh it."""
    state = {"token_calls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/protocol/openid-connect/token"):
            state["token_calls"] += 1
            return httpx.Response(
                200, json={"access_token": f"tok-{state['token_calls']}", "expires_in": 600}
            )
        return httpx.Response(200, json=[])

    _install_transport(handler)

    await find_user_by_email(_Settings(), "a@x")
    # Force the cached token to look expired and confirm next call refreshes.
    keycloak_admin._cache.expires_at = time.monotonic() - 1
    await find_user_by_email(_Settings(), "b@x")
    assert state["token_calls"] == 2
