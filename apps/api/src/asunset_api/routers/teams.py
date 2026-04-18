"""Team management: CRUD + membership."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_core.audit.events import EventType
from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import Authorizer, Tuple
from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal
from asunset_core.db.models import AppUser, MemberRole, Team, TeamMember
from asunset_api.routers.deps import (
    OrgContext,
    get_audit_sink,
    get_authorizer,
    get_current_org,
    get_db,
    require_org_admin,
)
from asunset_api.routers.schemas import (
    TeamCreateIn,
    TeamMemberAddIn,
    TeamMemberOut,
    TeamOut,
    UserOut,
)

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamOut])
async def list_teams(
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> list[Team]:
    """Org admins see every team; regular members only see teams they're in.

    Keeps team names (which in healthcare deployments often encode unit /
    specialty info) out of the hands of users who don't belong.
    """
    if org.is_admin:
        stmt = select(Team).order_by(Team.name)
    else:
        stmt = (
            select(Team)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == principal.user_id)
            .order_by(Team.name)
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreateIn,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> Team:
    team = Team(org_id=org.org_id, name=body.name)
    session.add(team)
    await session.flush([team])

    # Auto-enroll the creator as team admin. Avoids the awkward state
    # where an org admin creates a team and can't immediately use it
    # without re-adding themselves.
    session.add(
        TeamMember(
            team_id=team.id,
            user_id=principal.user_id,
            role=MemberRole.admin,
        )
    )
    await session.flush()

    await authorizer.write(
        writes=[
            Tuple(
                user=f"organization:{org.org_id}",
                relation="org",
                object=f"team:{team.id}",
            ),
            Tuple(
                user=principal.fga_user(),
                relation="admin",
                object=f"team:{team.id}",
            ),
            Tuple(
                user=principal.fga_user(),
                relation="member",
                object=f"team:{team.id}",
            ),
        ]
    )

    await audit.emit(
        EventType.TEAM_CREATED,
        action="create",
        resource_type="team",
        resource_id=team.id,
        resource_label=team.name,
        permission="org_admin",
        payload={"creator_auto_admin": True},
    )
    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: UUID,
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> None:
    team = (
        await session.execute(select(Team).where(Team.id == team_id))
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "team not found")

    deleted_name = team.name
    await session.delete(team)
    await session.flush()

    # Exhaustive FGA cleanup: three queries cover every tuple shape that
    # references this team in the model:
    #   1. object = team:X         — org→team, team#admin, team#member
    #   2. user   = team:X#member  — notes / other resources shared to the team
    #   3. user   = team:X#admin   — (currently unused in our model, future-proof)
    # The ordering principle (see auth/authorizer.py top comment) still
    # holds: DB delete flushed first, FGA cleanup second. If FGA deletes
    # fail the request errors and the DB delete rolls back.
    to_delete: list[Tuple] = []
    to_delete.extend(
        await authorizer.read_tuples(object=f"team:{team_id}")
    )
    to_delete.extend(
        await authorizer.read_tuples(user=f"team:{team_id}#member")
    )
    to_delete.extend(
        await authorizer.read_tuples(user=f"team:{team_id}#admin")
    )
    if to_delete:
        await authorizer.write(deletes=to_delete)

    await audit.emit(
        EventType.TEAM_DELETED,
        action="delete",
        resource_type="team",
        resource_id=team_id,
        resource_label=deleted_name,
        permission="org_admin",
    )


@router.get("/{team_id}/members", response_model=list[TeamMemberOut])
async def list_team_members(
    team_id: UUID,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> list[TeamMemberOut]:
    # Enforce membership (or org admin) before enumerating. 404 rather
    # than 403 so non-members don't even learn whether this team exists.
    if not org.is_admin:
        membership = (
            await session.execute(
                select(TeamMember).where(
                    TeamMember.team_id == team_id,
                    TeamMember.user_id == principal.user_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "team not found")

    result = await session.execute(
        select(TeamMember, AppUser)
        .join(AppUser, AppUser.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
    )
    return [
        TeamMemberOut(
            user=UserOut(id=u.id, email=u.email, display_name=u.display_name),
            role=m.role,
            joined_at=m.joined_at,
        )
        for (m, u) in result.all()
    ]


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_team_member(
    team_id: UUID,
    body: TeamMemberAddIn,
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> TeamMemberOut:
    team = (
        await session.execute(select(Team).where(Team.id == team_id))
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "team not found")

    user = (
        await session.execute(select(AppUser).where(AppUser.id == body.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    existing = (
        await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.user_id == body.user_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "already a team member")

    member = TeamMember(team_id=team_id, user_id=body.user_id, role=body.role)
    session.add(member)
    await session.flush([member])

    writes = [Tuple(user=f"user:{body.user_id}", relation="member", object=f"team:{team_id}")]
    if body.role == MemberRole.admin:
        writes.append(Tuple(user=f"user:{body.user_id}", relation="admin", object=f"team:{team_id}"))
    await authorizer.write(writes=writes)

    await audit.emit(
        EventType.TEAM_MEMBER_ADDED,
        action="create",
        resource_type="team_member",
        resource_id=f"{team_id}:{body.user_id}",
        resource_label=f"{user.email} → {team.name}",
        permission="org_admin",
        payload={"role": body.role.value, "team_id": str(team_id)},
    )

    return TeamMemberOut(
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
        role=member.role,
        joined_at=member.joined_at,
    )


@router.delete(
    "/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_team_member(
    team_id: UUID,
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> None:
    member = (
        await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a team member")

    team_name = (
        await session.execute(select(Team.name).where(Team.id == team_id))
    ).scalar_one_or_none()
    user_email = (
        await session.execute(select(AppUser.email).where(AppUser.id == user_id))
    ).scalar_one_or_none()

    prev_role = member.role
    await session.delete(member)

    deletes = [Tuple(user=f"user:{user_id}", relation="member", object=f"team:{team_id}")]
    if prev_role == MemberRole.admin:
        deletes.append(Tuple(user=f"user:{user_id}", relation="admin", object=f"team:{team_id}"))
    await authorizer.write(deletes=deletes)

    await audit.emit(
        EventType.TEAM_MEMBER_REMOVED,
        action="delete",
        resource_type="team_member",
        resource_id=f"{team_id}:{user_id}",
        resource_label=f"{user_email or '?'} → {team_name or '?'}",
        permission="org_admin",
        payload={"prev_role": prev_role.value, "team_id": str(team_id)},
    )
