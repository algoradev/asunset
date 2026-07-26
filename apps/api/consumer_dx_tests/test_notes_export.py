from __future__ import annotations

import csv
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal
from asunset_core.features.codegen import assert_generated_current
from asunset_core.testing import StaticAuthorizer, grant_feature
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from asunset_api.db.models import Note
from asunset_api.routers import deps, notes


class FakeResult:
    def __init__(self, rows: list[Note]) -> None:
        self._rows = rows

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Note]:
        return self._rows


class FakeSession:
    def __init__(self, rows: list[Note]) -> None:
        self._rows = rows
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self._rows)


class FakeAuditSink:
    def __init__(self) -> None:
        self.events: list[tuple[object, dict[str, object]]] = []

    async def emit(self, event_type: object, **kwargs: object) -> None:
        self.events.append((event_type, kwargs))


def principal() -> Principal:
    return Principal(
        user_id=uuid4(),
        email="alice@example.test",
        display_name="Alice",
    )


def note(*, owner_id, org_id, title: str, created_at: datetime) -> Note:
    return Note(
        id=uuid4(),
        org_id=org_id,
        owner_id=owner_id,
        title=title,
        body="",
        created_at=created_at,
        updated_at=created_at,
    )


async def client_for(
    *,
    principal_: Principal,
    authorizer: StaticAuthorizer,
    session: FakeSession,
    audit: FakeAuditSink | None = None,
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(notes.router)

    async def override_principal() -> Principal:
        return principal_

    async def override_authorizer() -> StaticAuthorizer:
        return authorizer

    async def override_db() -> AsyncIterator[FakeSession]:
        yield session

    async def override_audit() -> FakeAuditSink:
        return audit or FakeAuditSink()

    app.dependency_overrides[get_current_principal] = override_principal
    app.dependency_overrides[deps.get_authorizer] = override_authorizer
    app.dependency_overrides[deps.get_db] = override_db
    app.dependency_overrides[deps.get_audit_sink] = override_audit

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_notes_export_denied_without_feature() -> None:
    user = principal()
    authz = StaticAuthorizer()
    session = FakeSession([])
    audit = FakeAuditSink()

    async for client in client_for(
        principal_=user,
        authorizer=authz,
        session=session,
        audit=audit,
    ):
        response = await client.get("/notes/export")

    assert response.status_code == 403
    assert "feature notes.export not enabled" in response.text
    assert session.statements == []
    assert len(audit.events) == 1


@pytest.mark.asyncio
async def test_notes_export_allowed_with_feature() -> None:
    user = principal()
    org_id = uuid4()
    authz = StaticAuthorizer()
    grant_feature(authz, user.fga_user(), "notes.export")

    owned = note(
        owner_id=user.user_id,
        org_id=org_id,
        title="Owned note",
        created_at=datetime(2026, 7, 25, 12, 0, tzinfo=UTC),
    )
    shared = note(
        owner_id=uuid4(),
        org_id=org_id,
        title="Shared, quoted",
        created_at=datetime(2026, 7, 25, 12, 5, tzinfo=UTC),
    )
    authz.allow(user.fga_user(), "can_view", f"note:{shared.id}")
    session = FakeSession([owned, shared])

    async for client in client_for(
        principal_=user,
        authorizer=authz,
        session=session,
    ):
        response = await client.get("/notes/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="notes.csv"'

    rows = list(csv.DictReader(StringIO(response.text)))
    assert rows == [
        {
            "id": str(owned.id),
            "title": owned.title,
            "created_at": owned.created_at.isoformat(),
        },
        {
            "id": str(shared.id),
            "title": shared.title,
            "created_at": shared.created_at.isoformat(),
        },
    ]

    compiled = str(session.statements[0])
    assert "note.owner_id" in compiled
    assert "note.id IN" in compiled


def test_feature_codegen_current() -> None:
    api_root = Path(__file__).resolve().parents[1]
    repo_root = api_root.parents[1]

    assert_generated_current(
        str(api_root / "features.yaml"),
        py_path=str(api_root / "src/asunset_api/features_gen.py"),
        ts_path=str(repo_root / "apps/web/src/config/features.gen.ts"),
    )
