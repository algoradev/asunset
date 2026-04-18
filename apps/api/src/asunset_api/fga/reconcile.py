"""Compare Postgres state to OpenFGA, write missing tuples.

Runs forward-only (DB → FGA) by design: the DB is the source of truth for
what relationships *should* exist, and the dual-write ordering guarantees
that drift points one way (orphan tuples in FGA, never phantom DB rows).
So:

  - For every DB membership / ownership row, confirm a matching FGA tuple.
    Missing? Write it and emit `fga.drift_detected` + `fga.drift_fixed`.
  - Orphan FGA tuples (in FGA but no DB referent) are not removed here.
    They're harmless (grant access to nothing the DB returns) and sweeping
    them requires a full FGA scan which is expensive. Operators who want
    to purge them can extend this module.

Reachable both from `POST /platform/reconcile-fga` (interactive, for on-demand
investigation) and from the CLI (`python -m asunset_api.reconcile`, for cron).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_core.audit.events import EventType
from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import Authorizer, Tuple
from asunset_core.db.models import MemberRole, OrgMember, Organization, Team, TeamMember
from asunset_api.db.models import Note
from asunset_core.logging import get_logger

log = get_logger(__name__)


@dataclass
class ReconcileReport:
    checked: int = 0
    missing_tuples: int = 0
    added_tuples: int = 0
    drift_by_type: dict[str, int] = field(default_factory=dict)
    added: list[Tuple] = field(default_factory=list)

    def note_drift(self, kind: str) -> None:
        self.drift_by_type[kind] = self.drift_by_type.get(kind, 0) + 1


async def reconcile(
    authorizer: Authorizer,
    session: AsyncSession,
    audit: AuditSink,
) -> ReconcileReport:
    report = ReconcileReport()

    await _reconcile_org_members(authorizer, session, audit, report)
    await _reconcile_teams(authorizer, session, audit, report)
    await _reconcile_team_members(authorizer, session, audit, report)
    await _reconcile_notes(authorizer, session, audit, report)

    await audit.emit(
        EventType.FGA_RECONCILE_RUN,
        action="run",
        resource_type="fga",
        success=True,
        payload={
            "checked": report.checked,
            "missing_tuples": report.missing_tuples,
            "added_tuples": report.added_tuples,
            "drift_by_type": report.drift_by_type,
        },
    )
    log.info(
        "fga.reconcile.complete",
        checked=report.checked,
        missing_tuples=report.missing_tuples,
        drift_by_type=report.drift_by_type,
    )
    return report


async def _ensure(
    authorizer: Authorizer,
    audit: AuditSink,
    report: ReconcileReport,
    *,
    tuple: Tuple,
    drift_kind: str,
) -> None:
    report.checked += 1
    existing = await authorizer.read_tuples(
        user=tuple.user, relation=tuple.relation, object=tuple.object
    )
    if existing:
        return

    report.missing_tuples += 1
    report.note_drift(drift_kind)
    await audit.emit(
        EventType.FGA_DRIFT_DETECTED,
        action="detect",
        resource_type="fga_tuple",
        resource_id=f"{tuple.user}:{tuple.relation}:{tuple.object}",
        payload={"kind": drift_kind},
    )
    await authorizer.write(writes=[tuple])
    report.added_tuples += 1
    report.added.append(tuple)
    await audit.emit(
        EventType.FGA_DRIFT_FIXED,
        action="fix",
        resource_type="fga_tuple",
        resource_id=f"{tuple.user}:{tuple.relation}:{tuple.object}",
        payload={"kind": drift_kind},
    )


async def _reconcile_org_members(
    authorizer: Authorizer, session: AsyncSession, audit: AuditSink, report: ReconcileReport
) -> None:
    members = (await session.execute(select(OrgMember))).scalars().all()
    for m in members:
        await _ensure(
            authorizer, audit, report,
            tuple=Tuple(
                user=f"user:{m.user_id}",
                relation="member",
                object=f"organization:{m.org_id}",
            ),
            drift_kind="org_member",
        )
        if m.role == MemberRole.admin:
            await _ensure(
                authorizer, audit, report,
                tuple=Tuple(
                    user=f"user:{m.user_id}",
                    relation="admin",
                    object=f"organization:{m.org_id}",
                ),
                drift_kind="org_admin",
            )


async def _reconcile_teams(
    authorizer: Authorizer, session: AsyncSession, audit: AuditSink, report: ReconcileReport
) -> None:
    teams = (await session.execute(select(Team))).scalars().all()
    for t in teams:
        await _ensure(
            authorizer, audit, report,
            tuple=Tuple(
                user=f"organization:{t.org_id}",
                relation="org",
                object=f"team:{t.id}",
            ),
            drift_kind="team_parent",
        )


async def _reconcile_team_members(
    authorizer: Authorizer, session: AsyncSession, audit: AuditSink, report: ReconcileReport
) -> None:
    members = (await session.execute(select(TeamMember))).scalars().all()
    for m in members:
        await _ensure(
            authorizer, audit, report,
            tuple=Tuple(
                user=f"user:{m.user_id}",
                relation="member",
                object=f"team:{m.team_id}",
            ),
            drift_kind="team_member",
        )
        if m.role == MemberRole.admin:
            await _ensure(
                authorizer, audit, report,
                tuple=Tuple(
                    user=f"user:{m.user_id}",
                    relation="admin",
                    object=f"team:{m.team_id}",
                ),
                drift_kind="team_admin",
            )


async def _reconcile_notes(
    authorizer: Authorizer, session: AsyncSession, audit: AuditSink, report: ReconcileReport
) -> None:
    notes = (await session.execute(select(Note))).scalars().all()
    for n in notes:
        await _ensure(
            authorizer, audit, report,
            tuple=Tuple(
                user=f"user:{n.owner_id}",
                relation="owner",
                object=f"note:{n.id}",
            ),
            drift_kind="note_owner",
        )
        if n.team_id is not None:
            await _ensure(
                authorizer, audit, report,
                tuple=Tuple(
                    user=f"team:{n.team_id}",
                    relation="team",
                    object=f"note:{n.id}",
                ),
                drift_kind="note_team",
            )
