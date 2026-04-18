"""OIDC token validation against Keycloak.

The app fetches JWKS from the *internal* issuer URL (service DNS inside
the compose network) but validates the `iss` claim against the *public*
issuer URL — because the JWT was minted against the URL the browser used.
This split is the single most common cause of "works on localhost, breaks
in compose" bugs; it's called out in every relevant error message below.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKSet
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from asunset_api.auth.principal import Principal
from asunset_api.config import Settings, get_settings
from asunset_api.db.models import AppUser
from asunset_api.db.session import session_scope

bearer_scheme = HTTPBearer(auto_error=False)

JWKS_CACHE_TTL_SECONDS = 300


@dataclass
class _JwksCache:
    keyset: PyJWKSet | None = None
    fetched_at: float = 0.0


_cache = _JwksCache()


async def _fetch_jwks(settings: Settings) -> PyJWKSet:
    now = time.monotonic()
    if _cache.keyset is not None and (now - _cache.fetched_at) < JWKS_CACHE_TTL_SECONDS:
        return _cache.keyset

    url = f"{settings.keycloak_internal_issuer}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    _cache.keyset = PyJWKSet.from_dict(resp.json())
    _cache.fetched_at = now
    return _cache.keyset


async def _validate_token(token: str, settings: Settings) -> dict:
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"malformed token: {e}") from e

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing kid")

    keyset = await _fetch_jwks(settings)
    try:
        signing_key = keyset[kid].key
    except KeyError:
        # kid not in current JWKS — force-refresh once in case of key rotation
        _cache.keyset = None
        keyset = await _fetch_jwks(settings)
        try:
            signing_key = keyset[kid].key
        except KeyError as e:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "signing key not found in JWKS"
            ) from e

    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.keycloak_api_client_id,
            issuer=settings.keycloak_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired") from e
    except jwt.InvalidAudienceError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong audience") from e
    except jwt.InvalidIssuerError as e:
        # Reminder for the classic misconfig: iss claim is the browser-facing
        # URL, which must match settings.keycloak_issuer exactly.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "issuer mismatch — check KEYCLOAK_PUBLIC_URL matches what the browser uses",
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e

    return claims


async def _upsert_app_user(session: AsyncSession, claims: dict) -> AppUser:
    sub = UUID(claims["sub"])
    email = claims.get("email") or f"{claims.get('preferred_username', sub)}@unknown"
    display_name = (
        claims.get("name")
        or f"{claims.get('given_name', '')} {claims.get('family_name', '')}".strip()
        or claims.get("preferred_username")
        or email
    )

    # Insert-or-update so the local mirror always reflects the latest
    # profile data from Keycloak (email / name changes propagate on login).
    stmt = (
        pg_insert(AppUser)
        .values(id=sub, email=email, display_name=display_name)
        .on_conflict_do_update(
            index_elements=[AppUser.id],
            set_={"email": email, "display_name": display_name},
        )
        .returning(AppUser)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")

    claims = await _validate_token(credentials.credentials, settings)

    # The app_user mirror write must happen with RLS disabled for the
    # upsert (the user might be the first one ever, no org_id yet).
    # We're okay here because app_user is NOT in TENANT_TABLES — it has
    # no RLS policy, so an empty session context is fine.
    async with session_scope() as session:
        user = await _upsert_app_user(session, claims)

    roles = frozenset(claims.get("realm_access", {}).get("roles", []))
    principal = Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        realm_roles=roles,
        session_id=claims.get("sid"),
    )
    request.state.principal = principal
    return principal


async def require_platform_admin(
    principal: Principal = Depends(get_current_principal),
) -> Principal:
    if not principal.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "platform_admin required")
    return principal
