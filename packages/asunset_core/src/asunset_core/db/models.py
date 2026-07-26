"""Platform-level SQLAlchemy models shared by every asunset-based product.

Design notes worth preserving:

- `app_user.id` IS the Keycloak `sub` UUID. No separate app-side PK — we
  never need to reconcile two identifier spaces. The row is created lazily
  on first authenticated request for a given sub (see auth layer).
- `org_member` and `team_member` mirror OpenFGA relationships for UI
  presentation. OpenFGA remains the authoritative permission check;
  writes go through the Authorizer port so the two move together.
- `audit_event.payload` is JSONB and deliberately schema-loose; the shape
  of events evolves faster than migrations.
- Consumer-product tables (e.g. Note, Report, Case) inherit from the same
  `Base` so Alembic sees one metadata graph and FKs to org/user work.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MemberRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class Organization(Base):
    __tablename__ = "organization"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    teams: Mapped[list[Team]] = relationship(back_populates="org", cascade="all, delete-orphan")
    members: Mapped[list[OrgMember]] = relationship(
        back_populates="org", cascade="all, delete-orphan"
    )


class Team(Base):
    __tablename__ = "team"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    org: Mapped[Organization] = relationship(back_populates="teams")
    members: Mapped[list[TeamMember]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_team_org_name"),)


class AppUser(Base):
    __tablename__ = "app_user"

    # Stores the Keycloak `sub` claim verbatim — no separate app-side PK.
    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OrgMember(Base):
    __tablename__ = "org_member"

    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="member_role"), nullable=False, default=MemberRole.member
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    org: Mapped[Organization] = relationship(back_populates="members")


class TeamMember(Base):
    __tablename__ = "team_member"

    team_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("team.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="member_role", create_type=False),
        nullable=False,
        default=MemberRole.member,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    team: Mapped[Team] = relationship(back_populates="members")


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organization.id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    # Denormalized identity snapshot at emission time. Survives user
    # deletion — which is exactly when audit matters most.
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    actor_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actor_org_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    actor_realm_roles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Forensic triple: "from where / on what machine / in which SSO session".
    source_ip: Mapped[str | None] = mapped_column(INET, nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Human-readable label snapshot so deleting the resource doesn't erase
    # what was touched from the audit trail.
    resource_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    permission: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Human-readable resolution of *why* the check succeeded.
    permission_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AgentSession(Base):
    """A scoped agent session minted from a human's login (D4 mint).

    Row state is the revocation/expiry authority — the token alone is
    never sufficient (checked on every request by the authorizer dep).
    `grants` holds the declared capability subset as
    [{"relation": r, "object": pattern}]; effective permission is this
    subset ∩ the human's live permissions. Tenant table (RLS), with an
    org_member-style self arm so the row can be loaded before org
    context is established.
    """

    __tablename__ = "agent_session"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    audiences: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    grants: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeatureGrant(Base):
    """Bookkeeping for RUNTIME feature grants (v1.1 surface).

    The FGA tuple is the authorization truth; this row is the provenance
    record (who granted, when, revoked when) AND the object index that
    lets reconcile enumerate feature grants the FGA Read API can't
    discover. Dual-written with the tuple; revocation sets revoked_at
    (history preserved — the app role has no DELETE)."""

    __tablename__ = "feature_grant"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    grantee_type: Mapped[str] = mapped_column(String(10), nullable=False)  # user | team
    grantee_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    granted_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )


class RoleAssignment(Base):
    """Bookkeeping for custom-role membership (role:<name>#assignee).

    Same dual-write/provenance/history posture as FeatureGrant. 'Who
    holds billing_ops right now' is answered here, never by reading
    tuples (review #2, juniper #4)."""

    __tablename__ = "role_assignment"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    role_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )


class FeatureFreeze(Base):
    """Incident freeze state (v1.1): deny-all-now, grants PRESERVED,
    reversible. Active freeze = unfrozen_at IS NULL. Distinct axis from
    the manifest's enabled:false (decommission — destructive, deploy-
    time). require_feature consults this on every gated request."""

    __tablename__ = "feature_freeze"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    frozen_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    frozen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    unfrozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unfrozen_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
