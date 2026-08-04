"""Team rename + org-removal team cascade (rook's swat-01 request letter).

Direct handler invocation against a REAL migrated Postgres (the rls_db
container fixture) with the StaticAuthorizer recording FGA traffic —
the rename must touch no tuples; the cascade must delete exactly the
member's team tuples (admin tuple included for team admins).
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from asunset_core.db.models import (
    AppUser,
    MemberRole,
    Organization,
    OrgMember,
    Team,
    TeamMember,
)
from asunset_core.testing import StaticAuthorizer
from asunset_api.routers.deps import OrgContext
from asunset_api.routers.orgs import _cascade_team_memberships
from asunset_api.routers.schemas import TeamRenameIn
from asunset_api.routers.teams import rename_team

from .conftest import SeededDb


class _FakeSink:
    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, event_type, **kw):  # noqa: ANN001, ANN003
        self.events.append((event_type, kw))


def _sessionmaker(db: SeededDb):
    engine = create_async_engine(
        db.owner_dsn.replace("postgresql://", "postgresql+asyncpg://")
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_org_user_team(session):
    org = Organization(id=uuid4(), name="Cascade Org")
    user = AppUser(id=uuid4(), email=f"u-{uuid4().hex[:6]}@t", display_name="U")
    team_a = Team(id=uuid4(), org_id=org.id, name="Alpha")
    team_b = Team(id=uuid4(), org_id=org.id, name="Beta")
    session.add_all([org, user, team_a, team_b])
    await session.flush()
    session.add_all(
        [
            OrgMember(org_id=org.id, user_id=user.id, role=MemberRole.member),
            TeamMember(team_id=team_a.id, user_id=user.id, role=MemberRole.admin),
            TeamMember(team_id=team_b.id, user_id=user.id, role=MemberRole.member),
        ]
    )
    await session.flush()
    return org, user, team_a, team_b


async def test_rename_updates_row_emits_audit_touches_no_fga(rls_db: SeededDb) -> None:
    engine, maker = _sessionmaker(rls_db)
    sink = _FakeSink()
    try:
        async with maker() as session:
            org, _, team_a, _ = await _seed_org_user_team(session)
            out = await rename_team(
                team_id=team_a.id,
                body=TeamRenameIn(name="Alpha Renamed"),
                session=session,
                org=OrgContext(org_id=org.id, role=MemberRole.admin),
                audit=sink,
            )
            assert out.name == "Alpha Renamed"
            await session.commit()

        async with maker() as session:
            row = (
                await session.execute(select(Team).where(Team.id == team_a.id))
            ).scalar_one()
            assert row.name == "Alpha Renamed"
            # roster untouched by rename
            members = (
                (
                    await session.execute(
                        select(TeamMember).where(TeamMember.team_id == team_a.id)
                    )
                )
                .scalars()
                .all()
            )
            assert len(members) == 1

        (event_type, kw) = sink.events[0]
        assert event_type.value == "team.renamed"
        assert kw["payload"] == {"prev_name": "Alpha", "new_name": "Alpha Renamed"}
    finally:
        await engine.dispose()


async def test_cascade_removes_rows_and_tuples_admin_included(rls_db: SeededDb) -> None:
    engine, maker = _sessionmaker(rls_db)
    authz = StaticAuthorizer()
    try:
        async with maker() as session:
            org, user, team_a, team_b = await _seed_org_user_team(session)
            n = await _cascade_team_memberships(session, authz, org.id, user.id)
            assert n == 2
            await session.commit()

        async with maker() as session:
            leftover = (
                (
                    await session.execute(
                        select(TeamMember).where(TeamMember.user_id == user.id)
                    )
                )
                .scalars()
                .all()
            )
            assert leftover == []

        deleted = {(t.user, t.relation, t.object) for t in authz.deletes}
        assert deleted == {
            (f"user:{user.id}", "member", f"team:{team_a.id}"),
            (f"user:{user.id}", "admin", f"team:{team_a.id}"),  # team admin: both
            (f"user:{user.id}", "member", f"team:{team_b.id}"),
        }
    finally:
        await engine.dispose()


async def test_cascade_noop_when_no_team_memberships(rls_db: SeededDb) -> None:
    engine, maker = _sessionmaker(rls_db)
    authz = StaticAuthorizer()
    try:
        async with maker() as session:
            org = Organization(id=uuid4(), name="Lonely Org")
            user = AppUser(
                id=uuid4(), email=f"solo-{uuid4().hex[:6]}@t", display_name="S"
            )
            session.add_all([org, user])
            await session.flush()
            session.add(
                OrgMember(org_id=org.id, user_id=user.id, role=MemberRole.member)
            )
            await session.flush()
            n = await _cascade_team_memberships(session, authz, org.id, user.id)
            assert n == 0
            assert authz.deletes == []
    finally:
        await engine.dispose()
