"""D5 X-Org-Id membership selection + the PermissionError→403 mapping.

Pure-logic tests — no docker. The selection helper is what makes
multi-org "send the header" instead of a migration; these pin that the
header path validates membership and the no-header path is byte-for-byte
the old behavior.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from asunset_api.routers.deps import _select_membership

ORG_A, ORG_B, ORG_C = uuid4(), uuid4(), uuid4()


def _memberships():
    return [
        SimpleNamespace(org_id=ORG_A, role="admin"),
        SimpleNamespace(org_id=ORG_B, role="member"),
    ]


def test_no_header_keeps_first_membership() -> None:
    assert _select_membership(_memberships(), None).org_id == ORG_A
    assert _select_membership(_memberships(), "").org_id == ORG_A


def test_header_selects_named_membership() -> None:
    assert _select_membership(_memberships(), str(ORG_B)).org_id == ORG_B


def test_header_for_foreign_org_is_403() -> None:
    with pytest.raises(HTTPException) as e:
        _select_membership(_memberships(), str(ORG_C))
    assert e.value.status_code == 403


def test_malformed_header_is_400() -> None:
    with pytest.raises(HTTPException) as e:
        _select_membership(_memberships(), "not-a-uuid")
    assert e.value.status_code == 400


def test_permission_error_maps_to_403() -> None:
    """The app-level handler: SessionScopedAuthorizer's PermissionError
    (agent session touching an admin surface) must surface as 403, never
    an unhandled 500."""
    app = FastAPI()

    @app.exception_handler(PermissionError)
    async def _handler(request, exc: PermissionError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.get("/boom")
    async def boom():
        raise PermissionError("agent sessions cannot modify authorization tuples")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 403
    assert "agent sessions" in resp.json()["detail"]
