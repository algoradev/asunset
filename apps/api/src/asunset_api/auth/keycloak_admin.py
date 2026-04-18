"""Thin wrapper around Keycloak's admin API.

Uses the `asunset-api` confidential client's service account (client_credentials
grant) plus the `view-users` / `query-users` roles from `realm-management`.
Caches the service token until just before expiry so every admin lookup
doesn't pay an auth round-trip.

Scope kept intentionally narrow — only operations the app needs (find a
user by email). Real user provisioning (create / disable / reset password)
happens in Keycloak's own admin console or via SCIM, not here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from asunset_api.config import Settings
from asunset_api.logging import get_logger

log = get_logger(__name__)

# Renew a bit before expiry to avoid racing a 401 from a token used
# milliseconds before it would have expired anyway.
TOKEN_RENEW_MARGIN_SECONDS = 30


@dataclass
class _TokenCache:
    token: str | None = None
    expires_at: float = 0.0


_cache = _TokenCache()


async def _get_service_token(settings: Settings) -> str:
    now = time.monotonic()
    if _cache.token is not None and now < (_cache.expires_at - TOKEN_RENEW_MARGIN_SECONDS):
        return _cache.token

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{settings.keycloak_internal_issuer}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.keycloak_api_client_id,
                "client_secret": settings.keycloak_api_client_secret,
            },
        )
        resp.raise_for_status()
        body = resp.json()

    _cache.token = body["access_token"]
    _cache.expires_at = now + float(body.get("expires_in", 60))
    return _cache.token


async def find_user_by_email(settings: Settings, email: str) -> dict[str, Any] | None:
    """Resolve a Keycloak user by email. Returns None if not found.

    Uses `exact=true` to avoid partial matches (Keycloak's default is
    substring-match, which would make alice@foo match alice@foo.com).
    """
    token = await _get_service_token(settings)
    url = f"{settings.keycloak_internal_base}/admin/realms/{settings.keycloak_realm}/users"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            url,
            params={"email": email, "exact": "true", "max": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        users = resp.json()

    return users[0] if users else None
