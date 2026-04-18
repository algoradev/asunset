"""User directory endpoints.

`POST /users/lookup` resolves a Keycloak user by email, lazily creating
the local `app_user` mirror row so downstream endpoints (add to org,
add to team, share note with user) can reference a stable app-side id
without waiting for the target user to log in first.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_core.auth.keycloak_admin import find_user_by_email
from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal
from asunset_api.config import Settings, get_settings
from asunset_core.db.models import AppUser
from asunset_api.routers.deps import OrgContext, get_current_org, get_db
from asunset_api.routers.schemas import UserOut

router = APIRouter(prefix="/users", tags=["users"])


class LookupIn(BaseModel):
    email: str


@router.post("/lookup", response_model=UserOut)
async def lookup_user(
    body: LookupIn,
    principal: Principal = Depends(get_current_principal),
    org: OrgContext = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    kc_user = await find_user_by_email(settings, body.email.strip())
    if kc_user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no user with that email")

    user_id = UUID(kc_user["id"])
    email = kc_user.get("email") or body.email
    first = kc_user.get("firstName") or ""
    last = kc_user.get("lastName") or ""
    display_name = (f"{first} {last}").strip() or kc_user.get("username") or email

    stmt = (
        pg_insert(AppUser)
        .values(id=user_id, email=email, display_name=display_name)
        .on_conflict_do_update(
            index_elements=[AppUser.id],
            set_={"email": email, "display_name": display_name},
        )
        .returning(AppUser)
    )
    result = await session.execute(stmt)
    user = result.scalar_one()

    return UserOut(id=user.id, email=user.email, display_name=user.display_name)
