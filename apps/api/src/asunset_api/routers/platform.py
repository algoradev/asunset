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

        # Org now exists — apply the feature manifest immediately so
        # default grants are live before the first user request.
        from asunset_api.config import get_settings as _gs
        from asunset_api.features_boot import reconcile_features_startup

        await reconcile_features_startup(authorizer, _gs())

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


# --- agent sessions (D4 mint — docs/session-token-mint-spec.md) ----------

from datetime import UTC, datetime, timedelta  # noqa: E402
from uuid import uuid4  # noqa: E402

from asunset_core.auth.session_tokens import (  # noqa: E402
    AGENT_ID_RE,
    get_session_signer,
    mint_session_token,
)
from asunset_core.db.models import AgentSession  # noqa: E402
from asunset_api.config import get_settings  # noqa: E402
from asunset_api.routers.deps import get_audit_sink  # noqa: E402


class SessionGrant(BaseModel):
    relation: str = Field(min_length=1, max_length=64)
    object: str = Field(min_length=1, max_length=255)


class SessionMintIn(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    audiences: list[str] = Field(min_length=1, max_length=16)
    grants: list[SessionGrant] = Field(min_length=1, max_length=64)
    ttl_seconds: int = Field(default=1800, ge=60)
    label: str | None = Field(default=None, max_length=200)


class SessionMintOut(BaseModel):
    session_id: UUID
    token: str
    expires_at: datetime


class SessionOut(BaseModel):
    session_id: UUID
    agent_id: str
    label: str | None
    audiences: list[str]
    grants: list[SessionGrant]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


@router.get("/sessions/jwks")
async def session_jwks() -> dict:
    """Session-token JWKS — unauthenticated, like any JWKS endpoint.

    Resource servers fetch this (in-network) to validate tokens whose
    `iss` is the session issuer; Keycloak's JWKS still validates login
    tokens. Selection is by `iss` (contract §5 amendment, D7=A).
    """
    return get_session_signer(get_settings()).jwks()


@router.post("/sessions", response_model=SessionMintOut, status_code=status.HTTP_201_CREATED)
async def mint_session(
    body: SessionMintIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
    audit: AuditSink = Depends(get_audit_sink),
) -> SessionMintOut:
    """Mint a scoped agent session from the calling human's login.

    Only a LOGIN token may mint (an agent session must not spawn further
    credentials). sub stays the human; the token's fresh sid is the
    agent_session row id, so audit distinguishes agent sessions through
    the existing session_id plumbing.
    """
    settings = get_settings()
    if principal.is_agent_session:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "agent sessions cannot mint sessions"
        )
    if not AGENT_ID_RE.match(body.agent_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "agent_id must match ^[a-z0-9][a-z0-9_-]{0,63}$",
        )
    allowed = set(settings.allowed_audiences)
    bad = [a for a in body.audiences if a not in allowed]
    if bad:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"audiences not in this deployment's allowed set: {bad}",
        )

    ttl = min(body.ttl_seconds, settings.session_token_max_ttl_seconds)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    row = AgentSession(
        id=uuid4(),
        org_id=org.org_id,
        user_id=principal.user_id,
        agent_id=body.agent_id,
        label=body.label,
        audiences=body.audiences,
        grants=[g.model_dump() for g in body.grants],
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush([row])

    token = mint_session_token(
        get_session_signer(settings),
        user_id=principal.user_id,
        agent_id=body.agent_id,
        session_id=row.id,
        audiences=body.audiences,
        ttl_seconds=ttl,
    )
    await audit.emit(
        EventType.SESSION_MINTED,
        action="mint",
        resource_type="agent_session",
        resource_id=row.id,
        resource_label=body.label,
        payload={
            "agent_id": body.agent_id,
            "audiences": body.audiences,
            "ttl_seconds": ttl,
            "grant_count": len(body.grants),
        },
    )
    return SessionMintOut(session_id=row.id, token=token, expires_at=expires_at)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> list[SessionOut]:
    """Own sessions; org admins see the whole org's (RLS already fences)."""
    stmt = select(AgentSession).order_by(AgentSession.created_at.desc())
    if not org.is_admin:
        stmt = stmt.where(AgentSession.user_id == principal.user_id)
    result = await db.execute(stmt)
    return [
        SessionOut(
            session_id=r.id,
            agent_id=r.agent_id,
            label=r.label,
            audiences=r.audiences,
            grants=[SessionGrant(**g) for g in r.grants],
            created_at=r.created_at,
            expires_at=r.expires_at,
            revoked_at=r.revoked_at,
        )
        for r in result.scalars().all()
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: UUID,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
    audit: AuditSink = Depends(get_audit_sink),
) -> None:
    """Revoke = set revoked_at; takes effect on the session's next
    request (the authorizer dep re-reads the row every time). Allowed to
    the minting human, org admins, and platform_admin."""
    result = await db.execute(select(AgentSession).where(AgentSession.id == session_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown session")
    if not (
        row.user_id == principal.user_id or org.is_admin or principal.is_platform_admin
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your session")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await audit.emit(
            EventType.SESSION_REVOKED,
            action="revoke",
            resource_type="agent_session",
            resource_id=row.id,
            resource_label=row.label,
            payload={"agent_id": row.agent_id},
        )


# --- feature-level permissions (docs/feature-permissions-spec.md §6) ------


@router.get("/me/features", response_model=list[str])
async def my_features(
    principal: Principal = Depends(get_current_principal),
    authorizer: Authorizer = Depends(get_authorizer),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """Feature keys the caller may use — drives frontend menu/route
    gating (UX only; the API-side require_feature check is the control).
    Frozen features are excluded (deny-all-now); for agent sessions the
    list is additionally filtered by the session's grant subset."""
    from asunset_api.routers.features import active_freeze_keys

    objs = await authorizer.list_objects(principal.fga_user(), "can_use", "feature")
    frozen = await active_freeze_keys(db)
    return sorted(
        k for k in (o.removeprefix("feature:") for o in objs) if k not in frozen
    )


class FeatureReconcileIn(BaseModel):
    prune: bool = False
    # Read-only drift assessment: full report, zero writes, no audit
    # event (it's a read). Consumer doctors consume this instead of
    # reimplementing the manifest-vs-FGA diff.
    dry_run: bool = False


class FeatureReconcileOut(BaseModel):
    added: int
    orphans: list[str]
    pruned: int
    disabled: int


@router.post("/features/reconcile", response_model=FeatureReconcileOut)
async def reconcile_features_endpoint(
    body: FeatureReconcileIn,
    principal: Principal = Depends(get_current_principal),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> FeatureReconcileOut:
    """Apply features.yaml on demand — manifest edits (grants changed,
    a feature disabled) take effect without an api restart (feat-ops 2).
    Orphans are reported (as `user relation object` strings) and removed
    only when prune=true; enabled:false features are always swept."""
    from asunset_api.config import get_settings as _gs
    from asunset_api.features_boot import run_feature_reconcile

    # dry_run is a READ — platform_support (the doctor/on-call identity,
    # held by the asunset-api service account per init.sh) may call it.
    # Mutating runs stay platform_admin-only.
    if body.dry_run:
        if not (principal.is_platform_admin or principal.is_platform_support):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "operator role required")
    elif not principal.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "platform_admin required")
    try:
        report = await run_feature_reconcile(
            authorizer, _gs(), prune=body.prune, dry_run=body.dry_run
        )
    except Exception as e:  # ManifestError / gate mismatch → operator-visible
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    if report is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "nothing to reconcile — no manifest configured or no org yet",
        )
    if not body.dry_run:
        await audit.emit(
            EventType.FEATURES_RECONCILED,
        action="reconcile",
        resource_type="feature_manifest",
        payload={
            "added": len(report.added),
            "orphans": len(report.orphans),
            "pruned": len(report.pruned),
            "disabled": len(report.disabled),
            "prune_requested": body.prune,
        },
    )
    return FeatureReconcileOut(
        added=len(report.added),
        orphans=[" ".join(t) for t in report.orphans],
        pruned=len(report.pruned),
        disabled=len(report.disabled),
    )
