"""Shared Pydantic schemas for request/response bodies.

Kept in one file because the domain is small. If a router starts needing
schemas nobody else uses, inline them there — don't grow this file.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from asunset_core.db.models import MemberRole


class _ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- User / principal ---

class UserOut(_ORMBase):
    id: UUID
    # Plain str — Keycloak already validated the email upstream, and pydantic's
    # EmailStr rejects reserved TLDs (.local, .test) that some enterprise
    # directories legitimately use.
    email: str
    display_name: str


class MeOut(BaseModel):
    user: UserOut
    realm_roles: list[str]
    org_id: UUID | None
    org_role: MemberRole | None


# --- Org ---

class OrgOut(_ORMBase):
    id: UUID
    name: str
    created_at: datetime


class OrgMemberOut(BaseModel):
    user: UserOut
    role: MemberRole
    joined_at: datetime
    # True when the recipient hasn't accepted their magic-link invite yet
    # (Keycloak `emailVerified=false`). Only populated for org admins —
    # regular members see `False` regardless. Drives the "Pending" badge
    # in the members table and unlocks the resend/revoke kebab actions.
    pending: bool = False


class OrgMemberAddIn(BaseModel):
    user_id: UUID
    role: MemberRole = MemberRole.member


class MemberRoleUpdateIn(BaseModel):
    role: MemberRole


class OrgInviteIn(BaseModel):
    # Plain str + a minimal sanity check. EmailStr would reject `.local`
    # / `.test` TLDs that enterprise directories legitimately use, and
    # Keycloak does its own validation downstream.
    email: str = Field(min_length=3, max_length=320)
    role: MemberRole = MemberRole.member


class OrgInviteOut(BaseModel):
    """Result of an invite call. Semantics:

    - `member` is the (now-existing) org_member row, same shape as any
      other listing — caller can splice it straight into a members
      table without a refetch.
    - `delivery` says what mail we actually sent: `magic_link` for the
      Keycloak invite email (new or unverified user), `app_email` for
      our own `org_member_added` template (user already verified), or
      `none` if the operator hasn't configured SMTP (we still create
      the membership; the admin shares the password out-of-band).
    """

    member: OrgMemberOut
    delivery: Literal["magic_link", "app_email", "none"]
    was_new_user: bool


# --- Team ---

class TeamOut(_ORMBase):
    id: UUID
    name: str
    created_at: datetime


class TeamCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TeamMemberOut(BaseModel):
    user: UserOut
    role: MemberRole
    joined_at: datetime


class TeamMemberAddIn(BaseModel):
    user_id: UUID
    role: MemberRole = MemberRole.member


# --- Note ---

class NoteOut(_ORMBase):
    id: UUID
    title: str
    body: str
    owner_id: UUID
    team_id: UUID | None
    created_at: datetime
    updated_at: datetime
    # How THIS caller sees the note. Populated per-request by the router.
    # Values: "owner" | "direct:viewer" | "direct:editor" |
    # "team:{name} as {relation}" | "organization:{name} as {relation}" |
    # "unknown". Enables meaningful tab filtering and per-card badges
    # without the UI having to guess.
    access_path: str | None = None


class NoteCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    team_id: UUID | None = None


class NoteUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = None


NoteScope = Literal["mine", "team", "shared", "org"]


class ShareTarget(BaseModel):
    """Who to share with. Exactly one of the three fields must be set."""

    user_id: UUID | None = None
    team_id: UUID | None = None
    org: bool = False  # share with the whole organization


class NoteShareIn(ShareTarget):
    relation: Literal["viewer", "editor"] = "viewer"


class NoteShareOut(BaseModel):
    user_id: UUID | None = None
    team_id: UUID | None = None
    org_id: UUID | None = None
    relation: Literal["viewer", "editor"]


class NoteGrantOut(BaseModel):
    """A single resolved share on a note.

    `kind` selects which of (user_id, team_id, org_id) is populated and
    also tells the UI how to render the row. `label`/`email` are optional
    presentation fields so the caller doesn't need a second round-trip
    to display names; they're empty if the backing record was deleted
    but the FGA tuple survived (reconcile territory).
    """

    kind: Literal["user", "team", "org"]
    relation: Literal["viewer", "editor"]
    user_id: UUID | None = None
    team_id: UUID | None = None
    org_id: UUID | None = None
    label: str | None = None
    email: str | None = None


# --- Audit ---

class AuditEventOut(_ORMBase):
    id: UUID
    timestamp: datetime
    actor_id: UUID | None
    actor_email: str | None = None
    actor_display_name: str | None = None
    actor_org_role: str | None = None
    actor_realm_roles: list[str] = Field(default_factory=list)
    trace_id: str | None
    event_type: str
    resource_type: str | None
    resource_id: str | None
    resource_label: str | None = None
    action: str
    permission: str | None = None
    permission_path: str | None = None
    source_ip: str | None = None
    user_agent: str | None = None
    session_id: str | None = None
    success: bool
    payload: dict

    @field_validator("source_ip", mode="before")
    @classmethod
    def _ip_to_str(cls, v: object) -> str | None:
        # Postgres INET → Python ipaddress.IPv4Address/IPv6Address.
        # Pydantic's string validator would reject it; coerce first.
        return str(v) if v is not None else None
