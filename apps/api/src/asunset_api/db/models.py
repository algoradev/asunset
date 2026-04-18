"""SQLAlchemy models.

Design notes worth preserving:

- `app_user.id` IS the Keycloak `sub` UUID. No separate app-side PK — we
  never need to reconcile two identifier spaces. The row is created lazily
  on first authenticated request for a given sub (see auth layer).
- `org_member` and `team_member` mirror OpenFGA relationships for UI
  presentation (listing members, invite flows). OpenFGA remains the
  authoritative permission check. Both must stay in sync; writes go
  through the Authorizer port so the two move together.
- `audit_event.payload` is JSONB and deliberately schema-loose; the shape
  of events evolves faster than migrations.
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
    Text,
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


class Note(Base):
    __tablename__ = "note"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("team.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


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
    # source_ip respects X-Forwarded-For when set by a trusted proxy;
    # session_id is Keycloak's `sid` claim — stable for the lifetime of
    # one browser's SSO session, so two different `sid`s on the same
    # actor_id at the same time is a reliable credential-misuse signal.
    source_ip: Mapped[str | None] = mapped_column(INET, nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Human-readable label for the resource at the moment of the action
    # (e.g. note title). Snapshot so deleting the resource doesn't erase
    # what-was-touched from the audit trail.
    resource_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # Which authorization relation gated this call (can_view, can_edit,
    # can_delete, owner, org_admin, etc). Tells auditors *how* access
    # was granted.
    permission: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Human-readable resolution of *why* the check succeeded — e.g.
    # "owner", "direct:editor", "team 'Cardiology' as editor",
    # "organization as viewer". For forensics ("did they get in via
    # an unexpected path?") and breach-investigation readiness.
    permission_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The FGA resolution path — "owner", "team_viewer", "org_viewer", etc.
    # Answers the forensic question "WHY was this allowed?" without
    # replaying the authorization model against historical state.
    permission_path: Mapped[str | None] = mapped_column(String(64), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
