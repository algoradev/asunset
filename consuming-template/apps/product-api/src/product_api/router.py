"""Reports CRUD — the product's resource surface.

Deliberately small: create + list + get. Shows the full pattern (auth
via Principal, authz via Authorizer, RLS-scoped session, audit on every
mutation with permission path) so a consumer has one working reference
they can copy/extend for their own resources.
"""

from __future__ import annotations

from uuid import UUID

from asunset_core.audit.events import EventType
from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import Authorizer, Tuple
from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# asunset_api.routers.deps exposes the shared dependency providers —
# get_db, get_authorizer, get_audit_sink, get_current_org, etc.
# Consumers wire into the exact same providers the platform routers use.
from asunset_api.routers.deps import (
    OrgContext,
    get_audit_sink,
    get_authorizer,
    get_current_org,
    get_db,
)

from product_api.models import Report
from product_api.schemas import ReportCreateIn, ReportOut

router = APIRouter(prefix="/reports", tags=["reports"])


def _fga_report(report_id: UUID) -> str:
    return f"report:{report_id}"


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreateIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> ReportOut:
    report = Report(
        org_id=org.org_id,
        team_id=body.team_id,
        owner_id=principal.user_id,
        title=body.title,
        description=body.description,
        spec=body.spec,
    )
    session.add(report)
    await session.flush([report])

    # Dual-write in the same order asunset uses for Notes:
    # DB-flush → FGA-write → (implicit) DB-commit at end of request.
    # Fails toward orphan FGA tuples, never phantom DB rows.
    writes = [
        Tuple(
            user=principal.fga_user(),
            relation="owner",
            object=_fga_report(report.id),
        ),
    ]
    if body.team_id is not None:
        writes.append(
            Tuple(
                user=f"team:{body.team_id}",
                relation="team",
                object=_fga_report(report.id),
            )
        )
    await authorizer.write(writes=writes)

    await audit.emit(
        # EventType string is open-ended — consumers use their own values.
        # Using a plain string works; or define a product-specific StrEnum.
        "report.created",  # type: ignore[arg-type]
        action="create",
        resource_type="report",
        resource_id=report.id,
        resource_label=report.title,
        permission="owner",
        permission_path="owner",
        payload={"team_id": str(body.team_id) if body.team_id else None},
    )

    out = ReportOut.model_validate(report)
    out.access_path = "owner"
    return out


@router.get("", response_model=list[ReportOut])
async def list_reports(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
) -> list[ReportOut]:
    viewable = await authorizer.list_objects(
        principal.fga_user(), "can_view", "report"
    )
    if not viewable:
        return []
    ids = [UUID(obj.split(":", 1)[1]) for obj in viewable]

    result = await session.execute(
        select(Report).where(Report.id.in_(ids)).order_by(Report.updated_at.desc())
    )
    return [ReportOut.model_validate(r) for r in result.scalars().all()]


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> ReportOut:
    allowed = await authorizer.check(
        principal.fga_user(), "can_view", _fga_report(report_id)
    )
    if not allowed:
        # 404 (not 403) so we don't leak existence to unauthorized callers.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report not found")

    report = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report not found")

    await audit.emit(
        "report.viewed",  # type: ignore[arg-type]
        action="read",
        resource_type="report",
        resource_id=report_id,
        resource_label=report.title,
        permission="can_view",
    )

    return ReportOut.model_validate(report)
