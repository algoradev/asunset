"""Shared evidence helpers for matrix-row tests (spec §11 skeletons).

Kit-level evidence: the gate honors the authorizer's decision and the
declared scope resolver is the reach authority. Userset→member
expansion is FGA-model territory, evidenced in the live suites
(test_feature_permissions) — matrix rows here prove the GATE and SCOPE
seams per persona."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal

from asunset_api.routers import deps


class _NoFreezeResult:
    def scalars(self):  # noqa: ANN201
        return self

    def first(self):  # noqa: ANN201
        return None


class _Session:
    async def execute(self, stmt):  # noqa: ANN001, ANN201
        return _NoFreezeResult()


class _Sink:
    async def emit(self, *a, **k):  # noqa: ANN002, ANN003
        pass


def persona() -> Principal:
    return Principal(user_id=uuid4(), email="p@t", display_name="P")


def gated_app(key: str, authz, principal: Principal) -> FastAPI:  # noqa: ANN001
    app = FastAPI()

    @app.get("/gated", dependencies=[Depends(deps.require_feature(key))])
    async def gated() -> dict:
        return {"ok": True}

    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[deps.get_authorizer] = lambda: authz
    app.dependency_overrides[deps.get_audit_sink] = lambda: _Sink()
    app.dependency_overrides[deps.get_db] = lambda: _Session()
    return app


async def gate_status(key: str, authz, principal: Principal) -> int:  # noqa: ANN001
    app = gated_app(key, authz, principal)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return (await c.get("/gated")).status_code
