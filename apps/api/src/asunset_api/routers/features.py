"""Feature operations — the v1.1 runtime-grants surface (spec §10).

Everything runtime-granular that v1 lacked, as audited API: the
operator listing with provenance, incident freeze/unfreeze, per-user /
per-team feature grants, and custom-role membership. Every mutation
dual-writes (DB bookkeeping row → FGA tuple → commit, per the platform
ordering) and emits an audit event; revokes are idempotent audited
no-ops, never 404 (re-runnable runbooks).

Authorization tiers:
  - listing + mutations: org admin (or platform_admin);
  - freeze/unfreeze + reconcile dry_run additionally allow
    platform_support — freeze is reversible and grant-preserving, and
    platform_support is the on-call/doctor identity (the asunset-api
    service account holds it; see infra/keycloak/init.sh).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_core.audit.events import EventType
from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import Authorizer, Tuple
from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal
from asunset_core.db.models import FeatureFreeze, FeatureGrant, RoleAssignment
from asunset_core.features import FeatureManifest

from asunset_api.config import get_settings
from asunset_api.features_boot import _load as load_manifest_from_settings
from asunset_api.routers.deps import (
    OrgContext,
    get_audit_sink,
    get_authorizer,
    get_current_org,
    get_db,
)

router = APIRouter(prefix="/platform", tags=["features"])

ROLE_NAME_RE = r"^[a-z0-9][a-z0-9_-]{0,63}$"


# --- shared guards ---------------------------------------------------------


def _require_admin(principal: Principal, org: OrgContext) -> None:
    if not (org.is_admin or principal.is_platform_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org admin required")


def _require_operator(principal: Principal, org: OrgContext) -> None:
    """Freeze tier: admins plus platform_support (the on-call identity)."""
    if not (org.is_admin or principal.is_platform_admin or principal.is_platform_support):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operator role required")


def _manifest_or_503() -> FeatureManifest:
    manifest = load_manifest_from_settings(get_settings())
    if manifest is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "no feature manifest configured on this deployment",
        )
    return manifest


def _known_key_or_422(manifest: FeatureManifest, key: str) -> None:
    if key not in manifest.keys:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown feature {key} — no shadow features; declare it in the manifest first",
        )
    if key in manifest.disabled_keys:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"feature {key} is disabled (enabled: false) — re-enable before granting",
        )


async def _active_freeze(
    session: AsyncSession, key: str
) -> FeatureFreeze | None:
    result = await session.execute(
        select(FeatureFreeze).where(
            FeatureFreeze.feature_key == key, FeatureFreeze.unfrozen_at.is_(None)
        )
    )
    return result.scalars().first()


async def active_freeze_keys(session: AsyncSession) -> set[str]:
    result = await session.execute(
        select(FeatureFreeze.feature_key).where(FeatureFreeze.unfrozen_at.is_(None))
    )
    return {row[0] for row in result.all()}


# --- schemas ---------------------------------------------------------------


class GrantIn(BaseModel):
    user_id: UUID | None = None
    team_id: UUID | None = None

    def target(self) -> tuple[str, UUID]:
        if (self.user_id is None) == (self.team_id is None):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "exactly one of user_id or team_id",
            )
        if self.user_id is not None:
            return "user", self.user_id
        return "team", self.team_id  # type: ignore[return-value]


class FreezeIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class GrantOut(BaseModel):
    grantee_type: str
    grantee_id: UUID
    granted_by: UUID | None
    granted_at: datetime


class FeatureOut(BaseModel):
    key: str
    description: str
    enabled: bool
    frozen: bool
    freeze_reason: str | None
    default_grants: list[str]
    runtime_grants: list[GrantOut]


class AssigneeOut(BaseModel):
    user_id: UUID
    assigned_by: UUID | None
    assigned_at: datetime


def _fga_user(grantee_type: str, grantee_id: UUID) -> str:
    return f"user:{grantee_id}" if grantee_type == "user" else f"team:{grantee_id}#member"


# --- the operator listing (provenance) -------------------------------------


@router.get("/features", response_model=list[FeatureOut])
async def list_features(
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> list[FeatureOut]:
    """Manifest view + per-feature grants with provenance: origin is the
    section (default_grants = manifest, runtime_grants = bookkeeping
    with who/when). The operator answer to 'why does X have this'."""
    _require_operator(principal, org)
    manifest = _manifest_or_503()
    frozen = await active_freeze_keys(session)
    freezes = {
        f.feature_key: f
        for f in (
            await session.execute(
                select(FeatureFreeze).where(FeatureFreeze.unfrozen_at.is_(None))
            )
        ).scalars()
    }
    grants_rows = (
        await session.execute(
            select(FeatureGrant).where(FeatureGrant.revoked_at.is_(None))
        )
    ).scalars().all()
    by_key: dict[str, list[FeatureGrant]] = {}
    for g in grants_rows:
        by_key.setdefault(g.feature_key, []).append(g)

    return [
        FeatureOut(
            key=f.key,
            description=f.description,
            enabled=f.enabled,
            frozen=f.key in frozen,
            freeze_reason=freezes[f.key].reason if f.key in freezes else None,
            default_grants=list(f.grants),
            runtime_grants=[
                GrantOut(
                    grantee_type=g.grantee_type,
                    grantee_id=g.grantee_id,
                    granted_by=g.granted_by,
                    granted_at=g.granted_at,
                )
                for g in by_key.get(f.key, [])
            ],
        )
        for f in manifest.features
    ]


# --- freeze / unfreeze (incident tier) -------------------------------------


@router.post("/features/{key}/freeze", status_code=status.HTTP_200_OK)
async def freeze_feature(
    key: str,
    body: FreezeIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    audit: AuditSink = Depends(get_audit_sink),
) -> dict:
    """Deny-all-now, grants PRESERVED, reversible. Idempotent: freezing
    a frozen feature reports the existing freeze. The response states
    blast radius (review #2: a freeze that doesn't tell you its scope
    is a second incident)."""
    _require_operator(principal, org)
    manifest = _manifest_or_503()
    if key not in manifest.keys:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown feature {key}")

    existing = await _active_freeze(session, key)
    if existing is not None:
        return {
            "frozen": [key],
            "blast_radius": f"already frozen since {existing.frozen_at.isoformat()}",
            "noop": True,
        }
    session.add(
        FeatureFreeze(
            id=uuid4(),
            org_id=org.org_id,
            feature_key=key,
            reason=body.reason,
            frozen_by=principal.user_id,
        )
    )
    await session.flush()
    await audit.emit(
        EventType.FEATURE_FROZEN,
        action="freeze",
        resource_type="feature",
        resource_id=key,
        payload={"reason": body.reason, "blast_radius": "1 capability"},
    )
    return {"frozen": [key], "blast_radius": "1 capability", "noop": False}


@router.post("/features/{key}/unfreeze", status_code=status.HTTP_200_OK)
async def unfreeze_feature(
    key: str,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    audit: AuditSink = Depends(get_audit_sink),
) -> dict:
    _require_operator(principal, org)
    existing = await _active_freeze(session, key)
    if existing is None:
        await audit.emit(
            EventType.FEATURE_UNFROZEN,
            action="unfreeze",
            resource_type="feature",
            resource_id=key,
            payload={"noop": True},
        )
        return {"unfrozen": [], "noop": True}
    existing.unfrozen_at = datetime.now(UTC)
    existing.unfrozen_by = principal.user_id
    await session.flush()
    await audit.emit(
        EventType.FEATURE_UNFROZEN,
        action="unfreeze",
        resource_type="feature",
        resource_id=key,
        payload={"noop": False, "frozen_since": existing.frozen_at.isoformat()},
    )
    return {"unfrozen": [key], "noop": False}


# --- runtime feature grants -------------------------------------------------


@router.post("/features/{key}/grants", status_code=status.HTTP_201_CREATED)
async def grant_feature(
    key: str,
    body: GrantIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> dict:
    _require_admin(principal, org)
    manifest = _manifest_or_503()
    _known_key_or_422(manifest, key)
    if await _active_freeze(session, key) is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"feature {key} is frozen — unfreeze before granting",
        )
    grantee_type, grantee_id = body.target()

    # Idempotency: an identical active grant is an audited no-op.
    dup = (
        await session.execute(
            select(FeatureGrant).where(
                FeatureGrant.feature_key == key,
                FeatureGrant.grantee_type == grantee_type,
                FeatureGrant.grantee_id == grantee_id,
                FeatureGrant.revoked_at.is_(None),
            )
        )
    ).scalars().first()
    if dup is not None:
        return {"granted": False, "noop": True}

    # Dual-write ordering: DB flush → FGA write → commit (get_db).
    session.add(
        FeatureGrant(
            id=uuid4(),
            org_id=org.org_id,
            feature_key=key,
            grantee_type=grantee_type,
            grantee_id=grantee_id,
            granted_by=principal.user_id,
        )
    )
    await session.flush()
    await authorizer.write(
        writes=[Tuple(user=_fga_user(grantee_type, grantee_id),
                      relation="can_use", object=f"feature:{key}")],
        tolerate_existing=True,
    )
    await audit.emit(
        EventType.FEATURE_GRANTED,
        action="grant",
        resource_type="feature",
        resource_id=key,
        payload={"grantee_type": grantee_type, "grantee_id": str(grantee_id)},
    )
    return {"granted": True, "noop": False}


@router.delete("/features/{key}/grants", status_code=status.HTTP_200_OK)
async def revoke_feature_grant(
    key: str,
    body: GrantIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> dict:
    """Idempotent audited no-op when absent — never 404 (runbooks re-run)."""
    _require_admin(principal, org)
    grantee_type, grantee_id = body.target()
    row = (
        await session.execute(
            select(FeatureGrant).where(
                FeatureGrant.feature_key == key,
                FeatureGrant.grantee_type == grantee_type,
                FeatureGrant.grantee_id == grantee_id,
                FeatureGrant.revoked_at.is_(None),
            )
        )
    ).scalars().first()
    noop = row is None
    if row is not None:
        row.revoked_at = datetime.now(UTC)
        row.revoked_by = principal.user_id
        await session.flush()
        await authorizer.write(
            deletes=[Tuple(user=_fga_user(grantee_type, grantee_id),
                           relation="can_use", object=f"feature:{key}")]
        )
    await audit.emit(
        EventType.FEATURE_REVOKED,
        action="revoke",
        resource_type="feature",
        resource_id=key,
        payload={"grantee_type": grantee_type, "grantee_id": str(grantee_id), "noop": noop},
    )
    return {"revoked": not noop, "noop": noop}


# --- custom-role membership -------------------------------------------------


def _role_or_422(manifest: FeatureManifest, role: str) -> None:
    referenced = {
        g.split(":", 1)[1].split("#", 1)[0]
        for f in manifest.features
        for g in f.grants
        if g.startswith("role:")
    }
    if role not in referenced:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"role {role} is not referenced by any manifest grant — no shadow roles",
        )


class AssignIn(BaseModel):
    user_id: UUID


@router.get("/roles", response_model=dict[str, list[AssigneeOut]])
async def list_roles(
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[AssigneeOut]]:
    _require_operator(principal, org)
    rows = (
        await session.execute(
            select(RoleAssignment).where(RoleAssignment.revoked_at.is_(None))
        )
    ).scalars().all()
    out: dict[str, list[AssigneeOut]] = {}
    for r in rows:
        out.setdefault(r.role_name, []).append(
            AssigneeOut(user_id=r.user_id, assigned_by=r.assigned_by, assigned_at=r.assigned_at)
        )
    return out


@router.get("/roles/{role}/assignees", response_model=list[AssigneeOut])
async def list_assignees(
    role: str,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> list[AssigneeOut]:
    _require_operator(principal, org)
    rows = (
        await session.execute(
            select(RoleAssignment).where(
                RoleAssignment.role_name == role, RoleAssignment.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    return [
        AssigneeOut(user_id=r.user_id, assigned_by=r.assigned_by, assigned_at=r.assigned_at)
        for r in rows
    ]


@router.post("/roles/{role}/assignees", status_code=status.HTTP_201_CREATED)
async def assign_role(
    role: str,
    body: AssignIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> dict:
    import re

    if not re.match(ROLE_NAME_RE, role):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid role name")
    _require_admin(principal, org)
    _role_or_422(_manifest_or_503(), role)

    dup = (
        await session.execute(
            select(RoleAssignment).where(
                RoleAssignment.role_name == role,
                RoleAssignment.user_id == body.user_id,
                RoleAssignment.revoked_at.is_(None),
            )
        )
    ).scalars().first()
    if dup is not None:
        return {"assigned": False, "noop": True}

    session.add(
        RoleAssignment(
            id=uuid4(),
            org_id=org.org_id,
            role_name=role,
            user_id=body.user_id,
            assigned_by=principal.user_id,
        )
    )
    await session.flush()
    await authorizer.write(
        writes=[Tuple(user=f"user:{body.user_id}", relation="assignee", object=f"role:{role}")],
        tolerate_existing=True,
    )
    await audit.emit(
        EventType.ROLE_ASSIGNED,
        action="assign",
        resource_type="role",
        resource_id=role,
        payload={"user_id": str(body.user_id)},
    )
    return {"assigned": True, "noop": False}


@router.delete("/roles/{role}/assignees/{user_id}", status_code=status.HTTP_200_OK)
async def unassign_role(
    role: str,
    user_id: UUID,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> dict:
    """Idempotent audited no-op when absent — never 404."""
    _require_admin(principal, org)
    row = (
        await session.execute(
            select(RoleAssignment).where(
                RoleAssignment.role_name == role,
                RoleAssignment.user_id == user_id,
                RoleAssignment.revoked_at.is_(None),
            )
        )
    ).scalars().first()
    noop = row is None
    if row is not None:
        row.revoked_at = datetime.now(UTC)
        row.revoked_by = principal.user_id
        await session.flush()
        await authorizer.write(
            deletes=[Tuple(user=f"user:{user_id}", relation="assignee", object=f"role:{role}")]
        )
    await audit.emit(
        EventType.ROLE_UNASSIGNED,
        action="unassign",
        resource_type="role",
        resource_id=role,
        payload={"user_id": str(user_id), "noop": noop},
    )
    return {"unassigned": not noop, "noop": noop}
