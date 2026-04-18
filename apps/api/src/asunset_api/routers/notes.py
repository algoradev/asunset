"""Notes CRUD + sharing — the demo resource the template is built around.

Authorization pattern:
  1. For list endpoints, ask OpenFGA for the set of note IDs the caller
     can view, then fetch only those from the DB.
  2. For single-resource endpoints, call authorizer.check() up front and
     return 404 on deny (don't leak existence).
  3. DB writes and FGA writes are dual-written in the same request; they
     can drift under crash — a reconciliation job is the production pattern.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uuid import UUID as _UUID

from asunset_core.audit.events import EventType
from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import AccessPath, Authorizer, Tuple
from asunset_core.auth.principal import Principal
from asunset_core.auth.oidc import get_current_principal
from asunset_core.db.models import Organization, Team, TeamMember
from asunset_api.db.models import Note
from asunset_api.routers.deps import (
    OrgContext,
    get_audit_sink,
    get_authorizer,
    get_current_org,
    get_db,
)
from asunset_api.routers.schemas import (
    NoteCreateIn,
    NoteOut,
    NoteScope,
    NoteShareIn,
    NoteShareOut,
    NoteUpdateIn,
)

router = APIRouter(prefix="/notes", tags=["notes"])


def _fga_note(note_id: UUID) -> str:
    return f"note:{note_id}"


async def _resolve_path_label(
    session: AsyncSession,
    principal: Principal,
    note: Note,
    path: AccessPath | None,
) -> str:
    """Turn an AccessPath into an audit-friendly human label.

    Owner is detected here rather than round-tripping through FGA —
    owner == note.owner_id is the app-layer source of truth and faster
    than another check call.
    """
    if note.owner_id == principal.user_id:
        return "owner"
    if path is None:
        return "unknown"
    if path.kind == "direct":
        return f"direct:{path.via_relation}"
    if path.kind == "team":
        team_id = path.via_object.split(":", 1)[1] if path.via_object else None
        name = None
        if team_id:
            name = (
                await session.execute(
                    select(Team.name).where(Team.id == _UUID(team_id))
                )
            ).scalar_one_or_none()
        return f"team '{name or team_id}' as {path.via_relation}"
    if path.kind == "organization":
        org_id = path.via_object.split(":", 1)[1] if path.via_object else None
        name = None
        if org_id:
            name = (
                await session.execute(
                    select(Organization.name).where(Organization.id == _UUID(org_id))
                )
            ).scalar_one_or_none()
        return f"organization '{name or org_id}' as {path.via_relation}"
    return "unknown"


@router.get("", response_model=list[NoteOut])
async def list_notes(
    scope: NoteScope = Query("mine"),
    team_id: UUID | None = None,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
) -> list[NoteOut]:
    """List notes filtered by scope. Each scope is mutually exclusive:

    * mine:   owner == caller
    * team:   notes with team_id == ?team_id= (caller must be in that team)
    * shared: caller has a direct user grant (viewer/editor tuple to `user:X`)
    * org:    caller sees the note only via an org-wide share

    Every returned note carries an `access_path` describing how THIS caller
    sees it — drives UI badges and makes scope semantics obvious.

    Cost: one FGA tuple read per candidate note. Acceptable for the
    demo's list sizes; production forks with thousands of notes per user
    should paginate and/or batch-read tuples.
    """
    if scope == "team":
        if team_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "team scope requires ?team_id="
            )
        in_team = (
            await session.execute(
                select(TeamMember).where(
                    TeamMember.team_id == team_id,
                    TeamMember.user_id == principal.user_id,
                )
            )
        ).scalar_one_or_none()
        if in_team is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not a team member")

    # Always start from the FGA-authoritative set of notes this user can
    # see. Owner-only fast path skips the FGA round-trip.
    if scope == "mine":
        stmt = select(Note).where(Note.owner_id == principal.user_id)
    else:
        viewable = await authorizer.list_objects(
            principal.fga_user(), "can_view", "note"
        )
        ids = [UUID(obj.split(":", 1)[1]) for obj in viewable]
        if not ids:
            return []
        stmt = select(Note).where(Note.id.in_(ids))
        if scope == "team":
            stmt = stmt.where(Note.team_id == team_id)

    result = await session.execute(stmt.order_by(Note.updated_at.desc()))
    notes = list(result.scalars().all())

    enriched: list[NoteOut] = []
    for n in notes:
        if n.owner_id == principal.user_id:
            label = "owner"
        else:
            path = await authorizer.explain(
                principal.fga_user(), "can_view", _fga_note(n.id)
            )
            label = await _resolve_path_label(session, principal, n, path)

        # Narrow shared/org scopes to just that access path — the whole
        # point of the user's complaint was that "Organization" was
        # showing everything rather than strictly org-wide shares.
        if scope == "shared" and not label.startswith("direct"):
            continue
        if scope == "org" and not label.startswith("organization"):
            continue

        out = NoteOut.model_validate(n)
        out.access_path = label
        enriched.append(out)

    return enriched


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteCreateIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> Note:
    if body.team_id is not None:
        # Caller must be a team member to assign the note to that team.
        membership = (
            await session.execute(
                select(TeamMember).where(
                    TeamMember.team_id == body.team_id,
                    TeamMember.user_id == principal.user_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "not a member of that team"
            )

    note = Note(
        org_id=org.org_id,
        team_id=body.team_id,
        owner_id=principal.user_id,
        title=body.title,
        body=body.body,
    )
    session.add(note)
    await session.flush([note])

    writes = [
        Tuple(user=principal.fga_user(), relation="owner", object=_fga_note(note.id)),
    ]
    if body.team_id is not None:
        writes.append(
            Tuple(user=f"team:{body.team_id}", relation="team", object=_fga_note(note.id))
        )
    await authorizer.write(writes=writes)

    await audit.emit(
        EventType.NOTE_CREATED,
        action="create",
        resource_type="note",
        resource_id=note.id,
        resource_label=note.title,
        permission="owner",
        permission_path="owner",
        payload={"team_id": str(body.team_id) if body.team_id else None},
    )
    return note


async def _load_note_or_404(
    session: AsyncSession,
    authorizer: Authorizer,
    principal: Principal,
    note_id: UUID,
    relation: str,
) -> Note:
    allowed = await authorizer.check(
        principal.fga_user(), relation, _fga_note(note_id)
    )
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "note not found")
    note = (
        await session.execute(select(Note).where(Note.id == note_id))
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "note not found")
    return note


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(
    note_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> Note:
    note = await _load_note_or_404(session, authorizer, principal, note_id, "can_view")
    path = await authorizer.explain(
        principal.fga_user(), "can_view", _fga_note(note_id)
    )
    path_label = await _resolve_path_label(session, principal, note, path)
    await audit.emit(
        EventType.NOTE_VIEWED,
        action="read",
        resource_type="note",
        resource_id=note_id,
        resource_label=note.title,
        permission="can_view",
        permission_path=path_label,
    )
    out = NoteOut.model_validate(note)
    out.access_path = path_label
    return out


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: UUID,
    body: NoteUpdateIn,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> Note:
    note = await _load_note_or_404(session, authorizer, principal, note_id, "can_edit")
    path = await authorizer.explain(
        principal.fga_user(), "can_edit", _fga_note(note_id)
    )
    path_label = await _resolve_path_label(session, principal, note, path)

    changed: dict[str, object] = {}
    if body.title is not None:
        note.title = body.title
        changed["title"] = True
    if body.body is not None:
        note.body = body.body
        changed["body"] = True
    await session.flush([note])

    await audit.emit(
        EventType.NOTE_UPDATED,
        action="update",
        resource_type="note",
        resource_id=note_id,
        resource_label=note.title,
        permission="can_edit",
        permission_path=path_label,
        payload={"fields": sorted(changed.keys())},
    )
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> None:
    note = await _load_note_or_404(
        session, authorizer, principal, note_id, "can_delete"
    )
    path = await authorizer.explain(
        principal.fga_user(), "can_delete", _fga_note(note_id)
    )
    path_label = await _resolve_path_label(session, principal, note, path)

    # Snapshot the title before the delete — once the row is gone we
    # can't reconstruct what was deleted, which is exactly the signal
    # auditors need.
    deleted_title = note.title

    await session.delete(note)
    await session.flush()

    tuples = await authorizer.read_tuples(object=f"note:{note_id}")
    if tuples:
        await authorizer.write(deletes=tuples)

    await audit.emit(
        EventType.NOTE_DELETED,
        action="delete",
        resource_type="note",
        resource_id=note_id,
        resource_label=deleted_title,
        permission="can_delete",
        permission_path=path_label,
    )


# --- Sharing ---

def _share_target_fga(share: NoteShareIn, org_id: UUID) -> str:
    n = sum(x is not None and x is not False for x in (share.user_id, share.team_id, share.org))
    if n != 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "exactly one of user_id / team_id / org must be set",
        )
    if share.user_id is not None:
        return f"user:{share.user_id}"
    if share.team_id is not None:
        return f"team:{share.team_id}#member"
    return f"organization:{org_id}#member"


@router.post(
    "/{note_id}/shares",
    response_model=NoteShareOut,
    status_code=status.HTTP_201_CREATED,
)
async def share_note(
    note_id: UUID,
    body: NoteShareIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> NoteShareOut:
    # Only owners (and team admins, via the FGA model) can share.
    note = await _load_note_or_404(
        session, authorizer, principal, note_id, "can_delete"
    )
    path = await authorizer.explain(
        principal.fga_user(), "can_delete", _fga_note(note_id)
    )
    path_label = await _resolve_path_label(session, principal, note, path)

    target = _share_target_fga(body, org.org_id)
    await authorizer.write(
        writes=[Tuple(user=target, relation=body.relation, object=_fga_note(note_id))]
    )

    await audit.emit(
        EventType.NOTE_SHARED,
        action="create",
        resource_type="note_share",
        resource_id=note_id,
        resource_label=note.title,
        permission="can_delete",
        permission_path=path_label,
        payload={"target": target, "relation": body.relation},
    )

    return NoteShareOut(
        user_id=body.user_id,
        team_id=body.team_id,
        org_id=org.org_id if body.org else None,
        relation=body.relation,
    )


@router.delete("/{note_id}/shares", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_note(
    note_id: UUID,
    body: NoteShareIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> None:
    note = await _load_note_or_404(
        session, authorizer, principal, note_id, "can_delete"
    )
    path = await authorizer.explain(
        principal.fga_user(), "can_delete", _fga_note(note_id)
    )
    path_label = await _resolve_path_label(session, principal, note, path)

    target = _share_target_fga(body, org.org_id)
    await authorizer.write(
        deletes=[Tuple(user=target, relation=body.relation, object=_fga_note(note_id))]
    )

    await audit.emit(
        EventType.NOTE_UNSHARED,
        action="delete",
        resource_type="note_share",
        resource_id=note_id,
        resource_label=note.title,
        permission="can_delete",
        permission_path=path_label,
        payload={"target": target, "relation": body.relation},
    )
