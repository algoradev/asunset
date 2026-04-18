"""Consolidated FastAPI dependencies used by every router.

Composition order:
  get_current_principal  (from asunset_api.auth.oidc)
       ↓
  get_current_org        (resolves the single org this user belongs to)
       ↓
  get_db                 (RLS-scoped session keyed to user + org)
       ↓
  get_authorizer         (shared OpenFGA authorizer, app-scoped)
       ↓
  get_audit_sink         (request-scoped sink bound to session/actor/trace)

Routers should depend on the composed helpers below, not reach through the
chain manually — the layering is the security property, not a convention.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_api.audit.sink import AuditSink
from asunset_api.auth.authorizer import Authorizer
from asunset_api.auth.oidc import get_current_principal
from asunset_api.auth.principal import Principal
from asunset_api.db.models import MemberRole, OrgMember
from asunset_api.db.session import get_session_factory


@dataclass(frozen=True, slots=True)
class OrgContext:
    org_id: UUID
    role: MemberRole

    @property
    def is_admin(self) -> bool:
        return self.role == MemberRole.admin


async def get_current_org(
    principal: Principal = Depends(get_current_principal),
) -> OrgContext:
    """Resolve which org this principal operates in.

    Runs with only `app.current_user_id` set — `org_member`'s RLS policy
    permits rows where user_id matches, which is what we need here.
    """
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true), "
                 "set_config('app.current_org_id', '', true)"),
            {"uid": str(principal.user_id)},
        )
        result = await session.execute(
            select(OrgMember).where(OrgMember.user_id == principal.user_id)
        )
        memberships = result.scalars().all()

    if not memberships:
        # platform_admin can exist without an org — they're expected to
        # invoke POST /platform/bootstrap before doing anything else.
        if principal.is_platform_admin:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "no org provisioned yet — call POST /platform/bootstrap",
            )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "user has no org membership — contact an admin",
        )

    # Template assumption: one org per instance. If the user somehow has
    # multiple memberships, pick the first and log — future multi-client
    # instances will want an X-Org-Id header to disambiguate.
    m = memberships[0]
    return OrgContext(org_id=m.org_id, role=m.role)


async def get_db(
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
) -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "SELECT set_config('app.current_user_id', :uid, true), "
                "set_config('app.current_org_id', :oid, true)"
            ),
            {"uid": str(principal.user_id), "oid": str(org.org_id)},
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_authorizer(request: Request) -> Authorizer:
    authz: Authorizer | None = getattr(request.app.state, "authorizer", None)
    if authz is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "authorizer not initialized"
        )
    return authz


def _client_source_ip(request: Request) -> str | None:
    """Resolve the browser's IP honoring X-Forwarded-For when present.

    Operators running this behind a reverse proxy (the expected prod
    deployment) MUST configure the proxy to set X-Forwarded-For and to
    strip any client-supplied value so the left-most entry is trusted.
    Without that discipline this header is spoofable.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None
    return request.client.host if request.client else None


async def get_audit_sink(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> AuditSink:
    return AuditSink(
        session,
        org_id=org.org_id,
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_display_name=principal.display_name,
        actor_org_role=org.role,
        actor_realm_roles=list(principal.realm_roles),
        trace_id=getattr(request.state, "trace_id", None),
        source_ip=_client_source_ip(request),
        user_agent=request.headers.get("user-agent"),
        session_id=principal.session_id,
    )


def require_org_admin(org: OrgContext = Depends(get_current_org)) -> OrgContext:
    if not org.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org admin required")
    return org
