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
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_core.audit.events import EventType
from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import Authorizer
from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal
from asunset_core.db.models import MemberRole, OrgMember
from asunset_core.db.session import get_session_factory
from asunset_core.notifications import EmailService


@dataclass(frozen=True, slots=True)
class OrgContext:
    org_id: UUID
    role: MemberRole

    @property
    def is_admin(self) -> bool:
        return self.role == MemberRole.admin


def _select_membership(memberships: list[OrgMember], header_value: str | None) -> OrgMember:
    """Pick the caller's org membership, honoring an explicit X-Org-Id.

    D5 (identity contract §11): one org per instance remains the
    deployment model, so with no header this is memberships[0] exactly
    as before — inert on every current instance. When the header IS
    sent, it must name an org the caller actually belongs to (403
    otherwise), which is what makes multi-org later "send the header"
    instead of a migration.
    """
    if header_value:
        try:
            wanted = UUID(header_value)
        except ValueError as e:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "X-Org-Id must be a UUID"
            ) from e
        for m in memberships:
            if m.org_id == wanted:
                return m
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "not a member of the requested org"
        )
    return memberships[0]


async def get_current_org(
    request: Request,
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

    m = _select_membership(list(memberships), request.headers.get("x-org-id"))
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


def _base_authorizer(request: Request) -> Authorizer:
    authz: Authorizer | None = getattr(request.app.state, "authorizer", None)
    if authz is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "authorizer not initialized"
        )
    return authz


async def get_authorizer(
    request: Request,
    principal: Principal = Depends(get_current_principal),
) -> Authorizer:
    """The platform Authorizer — wrapped for agent sessions.

    For login tokens this is the app-scoped OpenFGA authorizer as-is.
    For asunset-minted session tokens (D4) the agent_session row is
    loaded ON EVERY REQUEST — revoked/expired/foreign rows 401 here,
    which is what makes revocation instant — and the authorizer is
    wrapped so every decision is: session's declared grant subset AND
    the human's live permission.

    The row is loaded with only app.current_user_id set (self arm of the
    RLS policy), deliberately NOT through get_db: this dependency must
    also work for flows that predate org context.
    """
    base = _base_authorizer(request)
    if not principal.is_agent_session:
        return base

    from asunset_core.auth.session_tokens import SessionScopedAuthorizer
    from asunset_core.db.models import AgentSession

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true), "
                 "set_config('app.current_org_id', '', true)"),
            {"uid": str(principal.user_id)},
        )
        result = await session.execute(
            select(AgentSession).where(AgentSession.id == UUID(str(principal.session_id)))
        )
        row = result.scalar_one_or_none()

    if row is None or row.user_id != principal.user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown agent session")
    if row.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "agent session revoked")
    if row.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "agent session expired")

    return SessionScopedAuthorizer(base, row.grants)


def get_email_service(request: Request) -> EmailService:
    """App-scoped EmailService. Routes that send mail depend on this.

    Backend is whatever NOTIFIER picked (log|resend) at startup. Don't
    instantiate `EmailService` per request — the httpx client inside
    `ResendNotifier` is meant to be reused.
    """
    svc: EmailService | None = getattr(request.app.state, "email_service", None)
    if svc is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "email service not initialized"
        )
    return svc


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


# Every gate declared via require_feature registers here; startup
# validates the set against the manifest so a typo'd key is a loud boot
# failure, not a permanent silent 403 (feature spec §6, feat-ops 1).
DECLARED_FEATURE_GATES: set[str] = set()


def require_feature(key: str):  # noqa: ANN201 — returns a FastAPI dependency
    """Gate an endpoint on feature-level permission (feature spec §6).

    One Authorizer check — `can_use feature:<key>` — so grants defined
    in features.yaml (or written at runtime) decide access, never role
    strings. Denials are audited with the standard actor snapshot so
    feature denials are SIEM-visible like every other authz event.

    Usage:
        @router.get("/export",
                    dependencies=[Depends(require_feature("reports.export"))])
    """

    # Accept plain strings AND str-enums (generated Feature constants).
    # NB: for `class X(str, Enum)` an f-string renders "X.MEMBER", not the
    # value — normalizing here prevents a gate that validates (set
    # membership works by value) yet checks a nonexistent FGA object.
    key = getattr(key, "value", key)
    DECLARED_FEATURE_GATES.add(key)

    async def _dep(
        principal: Principal = Depends(get_current_principal),
        authz: Authorizer = Depends(get_authorizer),
        sink: AuditSink = Depends(get_audit_sink),
        session: AsyncSession = Depends(get_db),
    ) -> None:
        # Incident freeze (v1.1): deny-all-now regardless of grants, with
        # a distinct message so UIs can render paused-not-ungranted.
        from asunset_core.db.models import FeatureFreeze

        frozen = (
            await session.execute(
                select(FeatureFreeze).where(
                    FeatureFreeze.feature_key == key,
                    FeatureFreeze.unfrozen_at.is_(None),
                ).limit(1)
            )
        ).scalars().first()
        if frozen is not None:
            await sink.emit(
                EventType.ACCESS_DENIED,
                action="feature_check",
                resource_type="feature",
                resource_id=key,
                permission="can_use",
                success=False,
                payload={"frozen": True},
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"feature {key} is temporarily unavailable"
            )
        allowed = await authz.check(principal.fga_user(), "can_use", f"feature:{key}")
        if not allowed:
            await sink.emit(
                EventType.ACCESS_DENIED,
                action="feature_check",
                resource_type="feature",
                resource_id=key,
                permission="can_use",
                success=False,
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"feature {key} not enabled for this user"
            )

    return _dep
