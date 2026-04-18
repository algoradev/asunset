"""Platform-level endpoints: one-time instance bootstrap + /me.

`POST /platform/bootstrap` is the "first run" setup — a platform_admin
creates the single organization this instance will serve and registers
themselves as its first org admin. Idempotent: calling a second time
returns 409 rather than creating a second org (template model assumes
one-org-per-instance).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_core.audit.events import EventType
from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import Authorizer, Tuple
from asunset_core.auth.oidc import get_current_principal, require_platform_admin
from asunset_core.auth.principal import Principal
from asunset_core.db.models import MemberRole, Organization, OrgMember
from asunset_core.db.session import get_admin_session_factory, get_session_factory
from asunset_api.fga.reconcile import reconcile
from asunset_api.routers.deps import (
    OrgContext,
    _client_source_ip,
    get_authorizer,
    get_current_org,
    get_db,
)
from asunset_api.routers.schemas import MeOut, UserOut

router = APIRouter(prefix="/platform", tags=["platform"])


class BootstrapIn(BaseModel):
    org_name: str = Field(min_length=1, max_length=200)


class BootstrapOut(BaseModel):
    org_id: UUID


@router.post("/bootstrap", response_model=BootstrapOut)
async def bootstrap_instance(
    body: BootstrapIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    authorizer: Authorizer = Depends(get_authorizer),
) -> BootstrapOut:
    """One-time: creates the single org and adds the caller as org admin.

    Runs on the admin session (schema owner) — the app role can't see any
    rows yet (no org context), but the owner bypasses RLS and can write
    the initial bootstrap state. Restricted to platform_admin, audit-logged,
    and idempotent-by-refusal.
    """
    factory = get_admin_session_factory()
    async with factory() as session:
        async with session.begin():
            existing = await session.execute(select(Organization).limit(1))
            if existing.scalar() is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "instance already bootstrapped"
                )

            org = Organization(name=body.org_name)
            session.add(org)
            await session.flush([org])

            session.add(
                OrgMember(
                    org_id=org.id,
                    user_id=principal.user_id,
                    role=MemberRole.admin,
                )
            )

            # Mirror into OpenFGA so the ReBAC layer knows the admin too.
            await authorizer.write(
                writes=[
                    Tuple(
                        user=principal.fga_user(),
                        relation="admin",
                        object=f"organization:{org.id}",
                    ),
                    Tuple(
                        user=principal.fga_user(),
                        relation="member",
                        object=f"organization:{org.id}",
                    ),
                ]
            )

            # Audit: emitted directly because the normal AuditSink dep
            # requires an org context we're only just now creating.
            sink = AuditSink(
                session,
                org_id=org.id,
                actor_id=principal.user_id,
                actor_email=principal.email,
                actor_display_name=principal.display_name,
                actor_realm_roles=list(principal.realm_roles),
                trace_id=getattr(request.state, "trace_id", None),
                source_ip=_client_source_ip(request),
                user_agent=request.headers.get("user-agent"),
                session_id=principal.session_id,
            )
            await sink.emit(
                EventType.ORG_CREATED,
                action="create",
                resource_type="organization",
                resource_id=org.id,
                resource_label=org.name,
                permission="platform_admin",
            )

        return BootstrapOut(org_id=org.id)


@router.get("/me", response_model=MeOut)
async def whoami(
    principal: Principal = Depends(get_current_principal),
) -> MeOut:
    # Soft-resolve org: unauthenticated-to-org principals still get /me.
    org_id: UUID | None = None
    org_role: MemberRole | None = None
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true), "
                 "set_config('app.current_org_id', '', true)"),
            {"uid": str(principal.user_id)},
        )
        result = await session.execute(
            select(OrgMember).where(OrgMember.user_id == principal.user_id).limit(1)
        )
        m = result.scalar_one_or_none()
        if m is not None:
            org_id = m.org_id
            org_role = m.role

    return MeOut(
        user=UserOut(
            id=principal.user_id,
            email=principal.email,
            display_name=principal.display_name,
        ),
        realm_roles=sorted(principal.realm_roles),
        org_id=org_id,
        org_role=org_role,
    )


class ReconcileOut(BaseModel):
    checked: int
    missing_tuples: int
    added_tuples: int
    drift_by_type: dict[str, int]


@router.post("/reconcile-fga", response_model=ReconcileOut)
async def reconcile_fga_endpoint(
    request: Request,
    principal: Principal = Depends(require_platform_admin),
    authorizer: Authorizer = Depends(get_authorizer),
) -> ReconcileOut:
    """Interactive reconcile — platform_admin only, every call audit-logged.

    Walks DB ownership/membership rows and ensures OpenFGA has a matching
    tuple for each; writes any missing. Orphan tuples (in FGA, no DB row)
    are not removed here — see `fga/reconcile.py`.
    """
    factory = get_admin_session_factory()
    async with factory() as session:
        async with session.begin():
            audit = AuditSink(
                session,
                org_id=None,
                actor_id=principal.user_id,
                actor_email=principal.email,
                actor_display_name=principal.display_name,
                actor_realm_roles=list(principal.realm_roles),
                trace_id=getattr(request.state, "trace_id", None),
                source_ip=_client_source_ip(request),
                user_agent=request.headers.get("user-agent"),
                session_id=principal.session_id,
            )
            report = await reconcile(authorizer, session, audit)

    return ReconcileOut(
        checked=report.checked,
        missing_tuples=report.missing_tuples,
        added_tuples=report.added_tuples,
        drift_by_type=report.drift_by_type,
    )
