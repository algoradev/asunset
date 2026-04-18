"""Org-level endpoints: read current org, manage members."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from asunset_api.audit.events import EventType
from asunset_api.audit.sink import AuditSink
from asunset_api.auth.authorizer import Authorizer, Tuple
from asunset_api.auth.oidc import get_current_principal
from asunset_api.auth.principal import Principal
from asunset_api.db.models import AppUser, MemberRole, Organization, OrgMember, TeamMember
from asunset_api.routers.deps import (
    OrgContext,
    get_audit_sink,
    get_authorizer,
    get_current_org,
    get_db,
    require_org_admin,
)
from asunset_api.routers.schemas import (
    OrgMemberAddIn,
    OrgMemberOut,
    OrgOut,
    UserOut,
)

router = APIRouter(prefix="/orgs", tags=["orgs"])


@router.get("/current", response_model=OrgOut)
async def get_current(
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> Organization:
    result = await session.execute(select(Organization).where(Organization.id == org.org_id))
    org_row = result.scalar_one()
    return org_row


@router.get("/current/members", response_model=list[OrgMemberOut])
async def list_members(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(get_current_org),
) -> list[OrgMemberOut]:
    """Three visibility tiers on the org roster:

    * Org admin → full list.
    * Team admin on any team → full list (they need to browse the roster
      to build out their team).
    * Regular member → self + anyone they share a team with.

    Rationale: "who's employed doing what" is need-to-know info in
    healthcare deployments. Sharing UX is unaffected because the
    email-lookup path (POST /users/lookup) still resolves arbitrary users.
    """
    stmt = (
        select(OrgMember, AppUser)
        .join(AppUser, AppUser.id == OrgMember.user_id)
        .where(OrgMember.org_id == org.org_id)
    )

    if not org.is_admin:
        is_any_team_admin = (
            await session.execute(
                select(TeamMember)
                .where(
                    TeamMember.user_id == principal.user_id,
                    TeamMember.role == MemberRole.admin,
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        if is_any_team_admin is None:
            my_team_ids = select(TeamMember.team_id).where(
                TeamMember.user_id == principal.user_id
            )
            teammates = select(TeamMember.user_id).where(
                TeamMember.team_id.in_(my_team_ids)
            )
            stmt = stmt.where(
                (OrgMember.user_id.in_(teammates))
                | (OrgMember.user_id == principal.user_id)
            )

    result = await session.execute(stmt)
    return [
        OrgMemberOut(
            user=UserOut(id=u.id, email=u.email, display_name=u.display_name),
            role=m.role,
            joined_at=m.joined_at,
        )
        for (m, u) in result.all()
    ]


@router.post(
    "/current/members",
    response_model=OrgMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    body: OrgMemberAddIn,
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> OrgMemberOut:
    user = (
        await session.execute(select(AppUser).where(AppUser.id == body.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "user not found — they must log in at least once first",
        )

    existing = (
        await session.execute(
            select(OrgMember).where(
                OrgMember.org_id == org.org_id, OrgMember.user_id == body.user_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "already a member")

    member = OrgMember(org_id=org.org_id, user_id=body.user_id, role=body.role)
    session.add(member)
    await session.flush([member])

    writes = [Tuple(user=f"user:{body.user_id}", relation="member", object=f"organization:{org.org_id}")]
    if body.role == MemberRole.admin:
        writes.append(
            Tuple(user=f"user:{body.user_id}", relation="admin", object=f"organization:{org.org_id}")
        )
    await authorizer.write(writes=writes)

    await audit.emit(
        EventType.ORG_MEMBER_ADDED,
        action="create",
        resource_type="org_member",
        resource_id=body.user_id,
        resource_label=user.email,
        permission="org_admin",
        payload={"role": body.role.value},
    )

    return OrgMemberOut(
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
        role=member.role,
        joined_at=member.joined_at,
    )


@router.delete("/current/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> None:
    member = (
        await session.execute(
            select(OrgMember).where(
                OrgMember.org_id == org.org_id, OrgMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a member")

    user_email = (
        await session.execute(select(AppUser.email).where(AppUser.id == user_id))
    ).scalar_one_or_none()

    prev_role = member.role
    await session.delete(member)

    deletes = [Tuple(user=f"user:{user_id}", relation="member", object=f"organization:{org.org_id}")]
    if prev_role == MemberRole.admin:
        deletes.append(
            Tuple(user=f"user:{user_id}", relation="admin", object=f"organization:{org.org_id}")
        )
    await authorizer.write(deletes=deletes)

    await audit.emit(
        EventType.ORG_MEMBER_REMOVED,
        action="delete",
        resource_type="org_member",
        resource_id=user_id,
        resource_label=user_email,
        permission="org_admin",
        payload={"prev_role": prev_role.value},
    )
