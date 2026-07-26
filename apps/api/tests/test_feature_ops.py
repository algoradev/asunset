"""v1.1 feature-ops suite: freeze semantics, grant/role guards,
tombstone refusal + orphan-hole closure.

Hermetic mix: pure helper tests, require_feature freeze behavior via
the consumer testing kit + dependency overrides (dogfooding the recipe
skeleton), and reconcile refusal against the live ephemeral OpenFGA.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from asunset_core.auth.authorizer import OpenFGAAuthorizer, Tuple, make_openfga_client
from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal
from asunset_core.features import ReconcileRefused, parse_manifest, reconcile_features
from asunset_core.testing import StaticAuthorizer, grant_feature

from asunset_api.routers import deps
from asunset_api.routers.features import GrantIn, _known_key_or_422, _role_or_422

from .conftest import FgaServer

# --- pure helper guards ----------------------------------------------------


def test_grant_target_requires_exactly_one() -> None:
    with pytest.raises(HTTPException):
        GrantIn().target()
    with pytest.raises(HTTPException):
        GrantIn(user_id=uuid4(), team_id=uuid4()).target()
    t, _ = GrantIn(user_id=uuid4()).target()
    assert t == "user"
    t, _ = GrantIn(team_id=uuid4()).target()
    assert t == "team"


def test_no_shadow_features_and_disabled_refuse() -> None:
    m = parse_manifest(
        {
            "features": {
                "a.live": {"grants": ["organization#member"]},
                "a.dead": {"grants": ["organization#member"], "enabled": False},
            }
        }
    )
    _known_key_or_422(m, "a.live")  # no raise
    with pytest.raises(HTTPException) as e:
        _known_key_or_422(m, "a.ghost")
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        _known_key_or_422(m, "a.dead")
    assert "disabled" in str(e.value.detail)


def test_no_shadow_roles() -> None:
    m = parse_manifest(
        {"features": {"a.b": {"grants": ["role:billing_ops#assignee"]}}}
    )
    _role_or_422(m, "billing_ops")  # no raise
    with pytest.raises(HTTPException) as e:
        _role_or_422(m, "phantom_role")
    assert e.value.status_code == 422


# --- freeze semantics through the real gate --------------------------------


class _FakeFreezeRow:
    frozen_at = datetime.now(UTC)
    unfrozen_at = None


class _FakeResult:
    def __init__(self, row):  # noqa: ANN001
        self._row = row

    def scalars(self):  # noqa: ANN201
        return self

    def first(self):  # noqa: ANN201
        return self._row


class _FakeSession:
    """Answers the FeatureFreeze lookup require_feature performs."""

    def __init__(self, frozen: bool) -> None:
        self._frozen = frozen

    async def execute(self, stmt):  # noqa: ANN001, ANN201
        return _FakeResult(_FakeFreezeRow() if self._frozen else None)


class _FakeSink:
    def __init__(self) -> None:
        self.events = []

    async def emit(self, event_type, **kw):  # noqa: ANN001, ANN003
        self.events.append((event_type, kw))


def _gated_app(authz: StaticAuthorizer, principal: Principal, frozen: bool) -> FastAPI:
    app = FastAPI()

    @app.get("/gated", dependencies=[Depends(deps.require_feature("audit.view"))])
    async def gated() -> dict:
        return {"ok": True}

    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[deps.get_authorizer] = lambda: authz
    app.dependency_overrides[deps.get_audit_sink] = lambda: _FakeSink()
    app.dependency_overrides[deps.get_db] = lambda: _FakeSession(frozen)
    return app


async def test_frozen_denies_even_when_granted() -> None:
    p = Principal(user_id=uuid4(), email="u@t", display_name="U")
    authz = StaticAuthorizer()
    grant_feature(authz, p.fga_user(), "audit.view")

    app = _gated_app(authz, p, frozen=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/gated")).status_code == 200

    app = _gated_app(authz, p, frozen=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/gated")
    assert resp.status_code == 403
    # Distinct message: paused, not ungranted — UIs depend on this.
    assert "temporarily unavailable" in resp.json()["detail"]


async def test_unfrozen_ungranted_still_plain_403() -> None:
    p = Principal(user_id=uuid4(), email="u@t", display_name="U")
    app = _gated_app(StaticAuthorizer(), p, frozen=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/gated")
    assert resp.status_code == 403
    assert "not enabled" in resp.json()["detail"]


# --- tombstone refusal + orphan-hole closure (live FGA) --------------------

ORG_ID = uuid4()


@pytest_asyncio.fixture
async def authz(fga_server: FgaServer) -> AsyncIterator[OpenFGAAuthorizer]:
    client = make_openfga_client(
        fga_server.settings(), fga_server.store_id, fga_server.model_id
    )
    a = OpenFGAAuthorizer(client, fga_server.store_id, fga_server.model_id)
    try:
        yield a
    finally:
        await client.close()


async def test_removed_key_with_grants_refuses_then_prune_overrides(
    authz: OpenFGAAuthorizer,
) -> None:
    """The tombstone rule made mechanical: a runtime user grant on a key
    that vanished from the manifest (discoverable only via the
    bookkeeping index — the closed orphan hole) refuses the reconcile;
    prune=True is the explicit override; dry_run reports without raising."""
    full = parse_manifest({"features": {"ops.keep": {"grants": []},
                                        "ops.gone": {"grants": []}}})
    await reconcile_features(authz, full, ORG_ID)
    # Runtime user grant on ops.gone — exactly what v1's reads couldn't
    # rediscover once the key left the manifest.
    await authz.write(
        writes=[Tuple(user="user:someone", relation="can_use", object="feature:ops.gone")],
        tolerate_existing=True,
    )
    # ALSO a managed (role) grant on it — the v1-invisible class.
    await authz.write(
        writes=[Tuple(user="role:ghosts#assignee", relation="can_use",
                      object="feature:ops.gone")],
        tolerate_existing=True,
    )

    shrunk = parse_manifest({"features": {"ops.keep": {"grants": []}}})
    index = {"ops.gone"}  # what the FeatureGrant bookkeeping supplies

    # dry_run: reports the orphan, does not raise, writes nothing.
    preview = await reconcile_features(
        authz, shrunk, ORG_ID, dry_run=True, known_extra_keys=index
    )
    assert any(o[2] == "feature:ops.gone" for o in preview.orphans)

    # live: refuses.
    with pytest.raises(ReconcileRefused, match="ops.gone"):
        await reconcile_features(authz, shrunk, ORG_ID, known_extra_keys=index)
    assert await authz.check("role:ghosts#assignee", "can_use", "feature:ops.gone")

    # explicit override: prune removes the MANAGED orphan; the runtime
    # user grant stays reconcile-invisible (it's runtime data — its
    # lifecycle is the revoke endpoint, never reconcile).
    report = await reconcile_features(
        authz, shrunk, ORG_ID, prune=True, known_extra_keys=index
    )
    assert any(o[2] == "feature:ops.gone" for o in report.pruned)
    assert not await authz.check("role:ghosts#assignee", "can_use", "feature:ops.gone")
    assert await authz.check("user:someone", "can_use", "feature:ops.gone")

    # cleanup
    await authz.write(
        deletes=[Tuple(user="user:someone", relation="can_use", object="feature:ops.gone")]
    )
