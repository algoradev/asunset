"""Thin wrapper around Keycloak's admin API.

Uses the `asunset-api` confidential client's service account
(client_credentials grant) plus the `view-users` / `query-users` /
`manage-users` roles from `realm-management`. Caches the service token
until just before expiry so every admin lookup doesn't pay an auth
round-trip.

Scope: just enough to support the invite flow — find / create users,
fetch their state, and trigger Keycloak's magic-link email. Anything
heavier (password resets, role grants, deletes) belongs in Keycloak's
own admin console or a SCIM provisioner.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from asunset_core.config import CoreSettings as Settings
from asunset_core.logging import get_logger

log = get_logger(__name__)

# Renew a bit before expiry to avoid racing a 401 from a token used
# milliseconds before it would have expired anyway.
TOKEN_RENEW_MARGIN_SECONDS = 30


@dataclass
class _TokenCache:
    token: str | None = None
    expires_at: float = 0.0


_cache = _TokenCache()


async def _get_service_token(settings: Settings) -> str:
    now = time.monotonic()
    if _cache.token is not None and now < (_cache.expires_at - TOKEN_RENEW_MARGIN_SECONDS):
        return _cache.token

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{settings.keycloak_internal_issuer}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.keycloak_api_client_id,
                "client_secret": settings.keycloak_api_client_secret,
            },
        )
        resp.raise_for_status()
        body = resp.json()

    _cache.token = body["access_token"]
    _cache.expires_at = now + float(body.get("expires_in", 60))
    return _cache.token


class KeycloakAdminError(RuntimeError):
    """Raised when Keycloak's admin API returns a non-2xx for an
    operation that doesn't have a more specific error type."""


class UserAlreadyExistsError(KeycloakAdminError):
    """Raised when `create_user` hits a 409 — username or email
    collides with an existing user in the realm."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"Keycloak user with email {email!r} already exists")


def _users_base(settings: Settings) -> str:
    return f"{settings.keycloak_internal_base}/admin/realms/{settings.keycloak_realm}/users"


async def find_user_by_email(settings: Settings, email: str) -> dict[str, Any] | None:
    """Resolve a Keycloak user by email. Returns None if not found.

    Uses `exact=true` to avoid partial matches (Keycloak's default is
    substring-match, which would make alice@foo match alice@foo.com).
    """
    token = await _get_service_token(settings)
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            _users_base(settings),
            params={"email": email, "exact": "true", "max": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        users = resp.json()

    return users[0] if users else None


async def get_user(settings: Settings, user_id: str) -> dict[str, Any] | None:
    """Fetch a Keycloak user by UUID. Returns None on 404."""
    token = await _get_service_token(settings)
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_users_base(settings)}/{user_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


async def create_user(
    settings: Settings,
    *,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    enabled: bool = True,
    email_verified: bool = False,
    required_actions: list[str] | None = None,
) -> str:
    """Create a Keycloak user. Returns the new user's UUID.

    Username is set to the email — matches the realm's policy and means
    callers don't need to invent one. Raises `UserAlreadyExistsError`
    on 409 so the caller can fall back to a "find + add to org" path
    instead of failing the whole invite.
    """
    token = await _get_service_token(settings)
    payload: dict[str, Any] = {
        "email": email,
        "username": email,
        "enabled": enabled,
        "emailVerified": email_verified,
    }
    if first_name:
        payload["firstName"] = first_name
    if last_name:
        payload["lastName"] = last_name
    if required_actions:
        payload["requiredActions"] = required_actions

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _users_base(settings),
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 409:
            raise UserAlreadyExistsError(email)
        if resp.status_code >= 400:
            log.error(
                "keycloak.create_user_failed",
                status=resp.status_code,
                body=resp.text[:500],
                email=email,
            )
            raise KeycloakAdminError(
                f"create_user returned {resp.status_code}: {resp.text[:200]}"
            )

        # Keycloak puts the new user's UUID in the Location header
        # (`.../users/<uuid>`). Fall back to an email lookup only if
        # the header is missing — shouldn't happen on a sane server
        # but the fallback avoids an opaque KeyError.
        location = resp.headers.get("location") or resp.headers.get("Location") or ""

    user_id = location.rsplit("/", 1)[-1] if "/" in location else ""
    if not user_id:
        existing = await find_user_by_email(settings, email)
        if existing is None:
            raise KeycloakAdminError(
                f"Created Keycloak user but couldn't resolve UUID for {email!r}"
            )
        user_id = existing["id"]
    return user_id


async def send_actions_email(
    settings: Settings,
    *,
    user_id: str,
    actions: list[str],
    client_id: str,
    lifespan_seconds: int = 7 * 24 * 60 * 60,
) -> None:
    """Trigger Keycloak's magic-link email.

    The recipient gets a one-time link that, when clicked, runs the
    listed `actions` (e.g. UPDATE_PASSWORD, VERIFY_EMAIL) and then
    redirects to `client_id`'s configured root URL — which is already
    per-deployment correct via the keycloak-init script, so the link
    works for tailnet / TLS / dev without any client-side branching.

    `lifespan_seconds` defaults to 7 days — long enough to cover "sent
    Friday, opened Monday" and Keycloak's default tends to be too short
    for invite-flow ergonomics.
    """
    token = await _get_service_token(settings)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.put(
            f"{_users_base(settings)}/{user_id}/execute-actions-email",
            json=actions,
            params={"client_id": client_id, "lifespan": lifespan_seconds},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code >= 400:
            log.error(
                "keycloak.send_actions_email_failed",
                status=resp.status_code,
                body=resp.text[:500],
                user_id=user_id,
                actions=actions,
            )
            raise KeycloakAdminError(
                f"send_actions_email returned {resp.status_code}: {resp.text[:200]}"
            )
