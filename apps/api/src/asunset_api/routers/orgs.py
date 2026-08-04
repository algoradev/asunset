"""Org-level endpoints: read current org, manage members, invite + revoke."""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_core.audit.events import EventType
from asunset_core.audit.sink import AuditSink
from asunset_core.auth.authorizer import Authorizer, Tuple
from asunset_core.auth.keycloak_admin import (
    KeycloakAdminError,
    create_user,
    find_user_by_email,
    generate_temporary_password,
    get_user,
    send_actions_email,
    set_temporary_password,
)
from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal
from asunset_core.db.models import AppUser, MemberRole, Organization, OrgMember, Team, TeamMember
from asunset_core.logging import get_logger
from asunset_core.notifications import EmailService
from asunset_api.config import Settings, get_settings
from asunset_api.routers.deps import (
    OrgContext,
    get_audit_sink,
    get_authorizer,
    get_current_org,
    get_db,
    get_email_service,
    require_org_admin,
)
from asunset_api.routers.schemas import (
    MemberRoleUpdateIn,
    OrgInviteIn,
    OrgInviteOut,
    OrgInviteResendOut,
    OrgMemberAddIn,
    OrgMemberOut,
    OrgOut,
    UserOut,
)

log = get_logger(__name__)

# Keycloak's web client — `executeActionsEmail` uses it to resolve the
# post-set-password redirect, which `keycloak-init` has already pinned
# per deployment mode (tailnet host / TLS host / dev). So the magic
# link works without us caring about hostnames.
INVITE_CLIENT_ID = "asunset-web"
INVITE_LINK_LIFESPAN_SECONDS = 7 * 24 * 60 * 60  # 7 days

# Required-actions that mean "the recipient hasn't finished accepting
# their invite." Other Keycloak required-actions exist (CONFIGURE_TOTP
# is the one keycloak-init adds for platform_admin holders, per the
# HIPAA loop) but those are operational gates, not invite acceptance —
# we deliberately do NOT count them as "pending" so the badge keeps
# its single, precise meaning. If we ever want MFA-enrollment
# visibility, that's a separate signal.
BOOTSTRAP_ACTIONS = frozenset({"UPDATE_PASSWORD", "VERIFY_EMAIL"})


def _is_pending(kc_user: dict | None) -> bool:
    """True iff the recipient hasn't finished the credential bootstrap.

    Proxy is "any BOOTSTRAP_ACTIONS still queued in the Keycloak user's
    requiredActions list." Works for both invite modes:

    - magic_link: clicking the link clears UPDATE_PASSWORD (and
      VERIFY_EMAIL) → empty intersection → not pending.
    - temp_password: setting a new password clears UPDATE_PASSWORD →
      empty intersection → not pending.

    The previous proxy (emailVerified=False) only happened to flip in
    the magic_link flow because the link itself sets emailVerified as
    a side effect; in temp_password mode it never flips at all,
    leaving fully-onboarded users stuck Pending forever (centum-flagged
    2026-05-12). requiredActions is the honest source.
    """
    if not isinstance(kc_user, dict):
        return False
    return bool(BOOTSTRAP_ACTIONS & set(kc_user.get("requiredActions") or []))


async def _bootstrap_credential(
    settings: Settings,
    *,
    user_id: UUID,
    welcome: dict | None = None,
    email_service: EmailService | None = None,
) -> tuple[str, str | None]:
    """Set up the new user's first-login credential per `INVITE_DELIVERY`.

    Returns `(delivery, temporary_password)` — `temporary_password`
    is set only when `delivery == "temporary_password"`.

    `magic_link`    Try executeActionsEmail. On failure, log + return
                    `("none", None)` — membership stands, operator
                    resets manually in Keycloak.
    `temp_password` Generate + set a one-time password. Return it.
                    When `welcome` + `email_service` are provided, also
                    send a `welcome_temp_password` mail to the recipient
                    (admin still gets the password back as a backup
                    in case the mail bounces). Mail failure does NOT
                    fail the invite.
    `auto`          Try magic_link first; on KeycloakAdminError fall
                    back to temp_password (and same welcome behavior).

    `welcome` shape: `{email, org_name, role, inviter_name}`. The
    login URL is derived here from `settings.keycloak_issuer` so callers
    don't have to repeat the expression.
    """
    mode = (settings.invite_delivery or "magic_link").lower()
    if mode not in {"magic_link", "temp_password", "auto"}:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"INVITE_DELIVERY={settings.invite_delivery!r} is not a valid mode",
        )

    async def _temp_password_path() -> tuple[str, str | None]:
        password = generate_temporary_password()
        await set_temporary_password(
            settings, user_id=str(user_id), password=password
        )
        if welcome and email_service is not None:
            try:
                await email_service.send(
                    template="welcome_temp_password",
                    to=welcome["email"],
                    context={
                        "org_name": welcome["org_name"],
                        "role": welcome["role"],
                        "inviter_name": welcome["inviter_name"],
                        "email": welcome["email"],
                        "temp_password": password,
                        "login_url": settings.keycloak_issuer.rsplit("/realms", 1)[0],
                    },
                )
            except Exception as exc:  # noqa: BLE001
                # Welcome mail is a UX nicety on top of a successful
                # password reset. Admin still has the password in the
                # response and can hand it over via side-channel.
                log.warning(
                    "invite.welcome_temp_password.send_failed",
                    extra={"user_id": str(user_id), "error": str(exc)[:200]},
                )
        return "temporary_password", password

    if mode == "temp_password":
        return await _temp_password_path()

    # magic_link or auto — try the email first.
    try:
        await send_actions_email(
            settings,
            user_id=str(user_id),
            actions=["UPDATE_PASSWORD"],
            client_id=INVITE_CLIENT_ID,
            lifespan_seconds=INVITE_LINK_LIFESPAN_SECONDS,
        )
        return "magic_link", None
    except KeycloakAdminError:
        if mode == "auto":
            return await _temp_password_path()
        # magic_link mode with no fallback — membership stands, but the
        # operator needs to bootstrap the credential another way.
        return "none", None

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
    rows = result.all()

    # `pending` is only meaningful for admins (regular members don't see
    # invite state — that's an admin concern). Cuts most page loads down
    # to zero Keycloak admin calls.
    pending_map: dict[UUID, bool] = {}
    if org.is_admin and rows:
        settings = get_settings()
        kc_users = await asyncio.gather(
            *(get_user(settings, str(u.id)) for (_, u) in rows),
            return_exceptions=True,
        )
        for (_, u), kc in zip(rows, kc_users):
            # If Keycloak is unreachable for one member, fail open
            # (pending=False — _is_pending guards against non-dicts).
            pending_map[u.id] = _is_pending(kc if isinstance(kc, dict) else None)

    return [
        OrgMemberOut(
            user=UserOut(id=u.id, email=u.email, display_name=u.display_name),
            role=m.role,
            joined_at=m.joined_at,
            pending=pending_map.get(u.id, False),
        )
        for (m, u) in rows
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
        # Structured detail: UIs branch on `code`, never on message text
        # (messages are copy, codes are contract — the web-sdk surfaces
        # this as ApiError.code).
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "already_a_member", "message": "already a member"},
        )

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


@router.patch("/current/members/{user_id}", response_model=OrgMemberOut)
async def update_member_role(
    user_id: UUID,
    body: MemberRoleUpdateIn,
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
) -> OrgMemberOut:
    member = (
        await session.execute(
            select(OrgMember).where(
                OrgMember.org_id == org.org_id, OrgMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a member")

    user = (
        await session.execute(select(AppUser).where(AppUser.id == user_id))
    ).scalar_one()

    prev_role = member.role
    if prev_role == body.role:
        return OrgMemberOut(
            user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
            role=member.role,
            joined_at=member.joined_at,
        )

    member.role = body.role
    await session.flush([member])

    # Admin is an additive tuple on top of member. DB flip above is the
    # source of truth; FGA is reconciled by adding/removing the admin tuple.
    admin_tuple = Tuple(
        user=f"user:{user_id}", relation="admin", object=f"organization:{org.org_id}"
    )
    if body.role == MemberRole.admin:
        await authorizer.write(writes=[admin_tuple])
    else:
        await authorizer.write(deletes=[admin_tuple])

    await audit.emit(
        EventType.ORG_MEMBER_ROLE_CHANGED,
        action="update",
        resource_type="org_member",
        resource_id=user_id,
        resource_label=user.email,
        permission="org_admin",
        payload={"prev_role": prev_role.value, "new_role": body.role.value},
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
    principal: Principal = Depends(get_current_principal),
) -> None:
    # Self-removal lockout guard. An admin who clicks Remove on their
    # own row deletes their org_member row + FGA tuple, then the very
    # next page-load 403s with no membership. Recovery requires another
    # admin (or a SQL operator) to put them back. The cost of refusing
    # is far smaller than the cost of the lockout. Cf. centum follow-up
    # 2026-05-12.
    if user_id == principal.user_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "you can't remove yourself — ask another admin",
        )

    member = (
        await session.execute(
            select(OrgMember).where(
                OrgMember.org_id == org.org_id, OrgMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a member")

    # Last-admin guard. Removing the only remaining admin leaves the org
    # with no one who can manage members or invite — same lockout class
    # as self-removal but reachable even when the actor is removing
    # someone else (the actor could then demote themselves, etc.).
    if member.role == MemberRole.admin:
        admin_count = (
            await session.execute(
                select(func.count())
                .select_from(OrgMember)
                .where(
                    OrgMember.org_id == org.org_id,
                    OrgMember.role == MemberRole.admin,
                )
            )
        ).scalar_one()
        if admin_count <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "cannot remove the last admin — promote another member first",
            )

    user_email = (
        await session.execute(select(AppUser.email).where(AppUser.id == user_id))
    ).scalar_one_or_none()

    prev_role = member.role
    await session.delete(member)

    teams_cascaded = await _cascade_team_memberships(
        session, authorizer, org.org_id, user_id
    )

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


async def _cascade_team_memberships(session, authorizer, org_id, user_id) -> int:
    """Remove ALL of a user's team memberships in this org (rows + FGA).

    Called on org-member removal AND invite revoke: leaving TeamMember
    rows/tuples behind is harmless today (access dies at get_current_org)
    but becomes a latent authority leak the day any consumer grants
    resources to team:X#member (rook's swat-01 letter, P2). Platform
    correctness: org membership is the root — when it goes, the team
    memberships under it go in the same transaction.
    """
    rows = (
        await session.execute(
            select(TeamMember)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.org_id == org_id, TeamMember.user_id == user_id)
        )
    ).scalars().all()
    if not rows:
        return 0
    deletes = []
    for tm in rows:
        deletes.append(
            Tuple(user=f"user:{user_id}", relation="member", object=f"team:{tm.team_id}")
        )
        if tm.role == MemberRole.admin:
            deletes.append(
                Tuple(user=f"user:{user_id}", relation="admin", object=f"team:{tm.team_id}")
            )
        await session.delete(tm)
    await session.flush()
    await authorizer.write(deletes=deletes)
    return len(rows)


# --- invite flow -----------------------------------------------------
#
# Three endpoints, all org-admin-only. The invite endpoint handles every
# branch (new KC user, existing-unverified, existing-verified-but-not-
# in-org) so the caller types an email and hits one button — no UI-side
# branching on "is this person already in our system?".


async def _ensure_app_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    email: str,
    display_name: str,
) -> AppUser:
    """Upsert an AppUser row mirroring the Keycloak identity.

    Same shape as /users/lookup's upsert — keeps the local mirror in
    sync. Display name comes from KC's firstName+lastName when
    available, else falls back to the email so list endpoints have a
    label to render.
    """
    stmt = (
        pg_insert(AppUser)
        .values(id=user_id, email=email, display_name=display_name)
        .on_conflict_do_update(
            index_elements=[AppUser.id],
            set_={"email": email, "display_name": display_name},
        )
        .returning(AppUser)
    )
    return (await session.execute(stmt)).scalar_one()


def _display_from_kc(kc_user: dict | None, fallback_email: str) -> str:
    if not kc_user:
        return fallback_email
    first = (kc_user.get("firstName") or "").strip()
    last = (kc_user.get("lastName") or "").strip()
    full = f"{first} {last}".strip()
    return full or kc_user.get("username") or fallback_email


@router.post(
    "/current/invites",
    response_model=OrgInviteOut,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    body: OrgInviteIn,
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
    email_service: EmailService = Depends(get_email_service),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(get_current_principal),
) -> OrgInviteOut:
    """Invite a user to this org by email.

    Two cases handled internally:

    1. **No Keycloak user yet** — create one, then bootstrap a
       credential per `INVITE_DELIVERY` (`was_new_user: true`).
    2. **Keycloak user exists** — bootstrap a credential regardless of
       prior state (`was_new_user: false`). The previous "fully-onboarded
       user → notify only" branch was removed (centum follow-up
       2026-05-13): clicking Invite should always issue access. If an
       admin wants to add an existing user without resetting their
       password, the `POST /current/members` endpoint covers that case
       (lookup by email + add). Resending a welcome reminder to a
       pending user is `POST /invites/{id}/resend`.

    Always re-bootstrapping makes the admin's mental model unambiguous
    ("Invite gives this person fresh access") and removes a sharp edge
    where an unrelated `emailVerified=true` (from a magic-link click,
    a manual kcadm hack, anything) silently changed what Invite did.

    If realm SMTP is unavailable, `_bootstrap_credential` degrades to
    `delivery: none` — the membership lands, the operator resets
    out-of-band. That preserves the pre-SMTP-setup escape hatch.
    """
    email_input = body.email.strip()
    if "@" not in email_input:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "email must contain '@'"
        )

    kc_user = await find_user_by_email(settings, email_input)
    was_new_user = kc_user is None

    if was_new_user:
        try:
            new_id = await create_user(
                settings,
                email=email_input,
                required_actions=["UPDATE_PASSWORD"],
                email_verified=False,
                enabled=True,
            )
        except KeycloakAdminError as exc:
            # Surface as a clean 502 so the admin UI can show a useful
            # error instead of a generic 500.
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"keycloak: {exc}",
            ) from exc
        user_id = UUID(new_id)
        # Re-fetch so display_name uses whatever KC normalized.
        kc_user = await get_user(settings, new_id)
    else:
        user_id = UUID(kc_user["id"])

    display_name = _display_from_kc(kc_user, email_input)
    canonical_email = (kc_user.get("email") if kc_user else None) or email_input

    # Welcome context — identical inputs feed the welcome_temp_password
    # mail sent from inside _bootstrap_credential. Loaded once here so
    # the existing-member resend branch + the new-member branch both
    # see the same labels.
    org_row = (
        await session.execute(
            select(Organization).where(Organization.id == org.org_id)
        )
    ).scalar_one()
    inviter_name = principal.display_name or principal.email or "an admin"
    welcome = {
        "email": canonical_email,
        "org_name": org_row.name,
        "role": body.role.value,
        "inviter_name": inviter_name,
    }

    async def bootstrap() -> tuple[str, str | None]:
        """Wrap _bootstrap_credential with the standard 502 surface."""
        try:
            return await _bootstrap_credential(
                settings,
                user_id=user_id,
                welcome=welcome,
                email_service=email_service,
            )
        except KeycloakAdminError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"keycloak: {exc}"
            ) from exc

    # Already a member of this org? Treat as resend regardless of the
    # user's onboarding state — Invite means "issue access," and the
    # bootstrap is idempotent (re-setting a temp password is fine, and
    # `set_temporary_password` puts UPDATE_PASSWORD back on the user
    # so the Pending badge reflects the fresh credential). The only
    # disallowed case is the role mismatch, which is genuinely
    # ambiguous (change role? new invite? — point at PATCH).
    #
    # The partial-failure retry case (KC + FGA committed, OrgMember
    # missing) falls *through* this check because `existing` is None;
    # the FGA write below uses `tolerate_existing=True` so the orphan
    # tuple from a prior attempt doesn't 400.
    existing = (
        await session.execute(
            select(OrgMember).where(
                OrgMember.org_id == org.org_id, OrgMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.role != body.role:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "already_a_member",
                    "message": "already a member with a different role — "
                    "use PATCH to change role",
                },
            )
        delivery, temp_password = await bootstrap()
        await audit.emit(
            EventType.ORG_INVITE_RESENT,
            action="update",
            resource_type="org_member",
            resource_id=user_id,
            resource_label=canonical_email,
            permission="org_admin",
            payload={"role": body.role.value, "delivery": delivery},
        )
        return OrgInviteOut(
            member=OrgMemberOut(
                user=UserOut(
                    id=user_id, email=canonical_email, display_name=display_name
                ),
                role=existing.role,
                joined_at=existing.joined_at,
                pending=True,
            ),
            delivery=delivery,  # type: ignore[arg-type]
            was_new_user=False,
            temporary_password=temp_password,
        )

    await _ensure_app_user(
        session,
        user_id=user_id,
        email=canonical_email,
        display_name=display_name,
    )

    member = OrgMember(org_id=org.org_id, user_id=user_id, role=body.role)
    session.add(member)
    await session.flush([member])

    writes = [
        Tuple(
            user=f"user:{user_id}",
            relation="member",
            object=f"organization:{org.org_id}",
        )
    ]
    if body.role == MemberRole.admin:
        writes.append(
            Tuple(
                user=f"user:{user_id}",
                relation="admin",
                object=f"organization:{org.org_id}",
            )
        )
    # tolerate_existing covers the partial-failure retry: KC user +
    # FGA tuple already landed on a prior attempt that failed before
    # OrgMember committed. Without this flag the retry 400s here.
    await authorizer.write(writes=writes, tolerate_existing=True)

    delivery, temp_password = await bootstrap()

    await audit.emit(
        EventType.ORG_MEMBER_INVITED,
        action="create",
        resource_type="org_member",
        resource_id=user_id,
        resource_label=canonical_email,
        permission="org_admin",
        payload={
            "role": body.role.value,
            "delivery": delivery,
            "was_new_user": was_new_user,
        },
    )

    return OrgInviteOut(
        member=OrgMemberOut(
            user=UserOut(
                id=user_id, email=canonical_email, display_name=display_name
            ),
            role=member.role,
            joined_at=member.joined_at,
            pending=True,
        ),
        delivery=delivery,  # type: ignore[arg-type]
        was_new_user=was_new_user,
        temporary_password=temp_password,
    )


@router.post(
    "/current/invites/{user_id}/resend",
    response_model=OrgInviteResendOut,
)
async def resend_invite(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    audit: AuditSink = Depends(get_audit_sink),
    settings: Settings = Depends(get_settings),
    email_service: EmailService = Depends(get_email_service),
    principal: Principal = Depends(get_current_principal),
) -> OrgInviteResendOut:
    """Re-bootstrap a credential for a user who hasn't accepted yet.

    Same per-mode behavior as create-invite: `magic_link` resends the
    Keycloak email, `temp_password` generates a fresh password and
    returns it (the previous one becomes invalid because reset
    overwrites it), `auto` tries email then falls back. In any
    temp_password outcome the recipient also gets the welcome mail.
    """
    member = (
        await session.execute(
            select(OrgMember).where(
                OrgMember.org_id == org.org_id, OrgMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a member")

    kc_user = await get_user(settings, str(user_id))
    if kc_user is None:
        # FGA/DB has them but Keycloak doesn't — orphan row.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "user not found in Keycloak — revoke this membership instead",
        )
    if not _is_pending(kc_user):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "user has already accepted — nothing to resend"
        )

    user_row = (
        await session.execute(select(AppUser).where(AppUser.id == user_id))
    ).scalar_one_or_none()
    user_email = user_row.email if user_row else None
    org_row = (
        await session.execute(
            select(Organization).where(Organization.id == org.org_id)
        )
    ).scalar_one()
    welcome = (
        {
            "email": user_email,
            "org_name": org_row.name,
            "role": member.role.value,
            "inviter_name": principal.display_name or principal.email or "an admin",
        }
        if user_email
        else None
    )

    try:
        delivery, temp_password = await _bootstrap_credential(
            settings,
            user_id=user_id,
            welcome=welcome,
            email_service=email_service,
        )
    except KeycloakAdminError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"keycloak: {exc}"
        ) from exc

    await audit.emit(
        EventType.ORG_INVITE_RESENT,
        action="update",
        resource_type="org_member",
        resource_id=user_id,
        resource_label=user_email,
        permission="org_admin",
        payload={"delivery": delivery},
    )

    return OrgInviteResendOut(
        delivery=delivery,  # type: ignore[arg-type]
        temporary_password=temp_password,
    )


@router.delete(
    "/current/invites/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invite(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
    org: OrgContext = Depends(require_org_admin),
    authorizer: Authorizer = Depends(get_authorizer),
    audit: AuditSink = Depends(get_audit_sink),
    settings: Settings = Depends(get_settings),
) -> None:
    """Revoke a pending invite — drops the org_member row + FGA tuples.

    Only valid for users who haven't accepted yet. For an already-
    accepted member, use DELETE /current/members/{user_id} (regular
    removal) so the audit trail distinguishes "I revoked an unanswered
    invite" from "I removed a member who was actually here".

    The Keycloak user is left in place. Re-inviting later picks up the
    same `sub` and the user can finally set a password if they want to.
    Operators who actually want to delete the orphan KC account do so
    from the Keycloak admin console.
    """
    member = (
        await session.execute(
            select(OrgMember).where(
                OrgMember.org_id == org.org_id, OrgMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a member")

    kc_user = await get_user(settings, str(user_id))
    if kc_user is not None and not _is_pending(kc_user):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "user has already accepted — use DELETE /members/{user_id} to remove",
        )

    user_email = (
        await session.execute(select(AppUser.email).where(AppUser.id == user_id))
    ).scalar_one_or_none()

    prev_role = member.role
    await session.delete(member)

    teams_cascaded = await _cascade_team_memberships(
        session, authorizer, org.org_id, user_id
    )

    deletes = [
        Tuple(
            user=f"user:{user_id}",
            relation="member",
            object=f"organization:{org.org_id}",
        )
    ]
    if prev_role == MemberRole.admin:
        deletes.append(
            Tuple(
                user=f"user:{user_id}",
                relation="admin",
                object=f"organization:{org.org_id}",
            )
        )
    await authorizer.write(deletes=deletes)

    await audit.emit(
        EventType.ORG_INVITE_REVOKED,
        action="delete",
        resource_type="org_member",
        resource_id=user_id,
        resource_label=user_email,
        permission="org_admin",
        payload={"teams_cascaded": teams_cascaded, "prev_role": prev_role.value},
    )
