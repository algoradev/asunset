"""Audit log viewer API — thin pagination over the `audit_event` table.

Scoped to the current org via RLS. Org admins see everything in their org;
regular members see their own actions only. The *durable* HIPAA record lives
in the SIEM — this endpoint is for UX convenience, not compliance retention.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_api.auth.principal import Principal
from asunset_api.auth.oidc import get_current_principal
from asunset_api.db.models import AuditEvent
from asunset_api.routers.deps import OrgContext, get_current_org, get_db
from asunset_api.routers.schemas import AuditEventOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=list[AuditEventOut])
async def list_events(
    since: datetime | None = Query(None, description="only events newer than this"),
    until: datetime | None = Query(None, description="only events older than this"),
    event_type: str | None = Query(None),
    actor_id: UUID | None = Query(None),
    trace_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> list[AuditEvent]:
    stmt = select(AuditEvent)

    if not org.is_admin:
        # Non-admins see their own actions only.
        stmt = stmt.where(AuditEvent.actor_id == principal.user_id)

    if since is not None:
        stmt = stmt.where(AuditEvent.timestamp >= since)
    if until is not None:
        stmt = stmt.where(AuditEvent.timestamp <= until)
    if event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if trace_id is not None:
        stmt = stmt.where(AuditEvent.trace_id == trace_id)

    stmt = stmt.order_by(AuditEvent.timestamp.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
