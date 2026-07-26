"""Agent session tokens — the D4 mint (docs/session-token-mint-spec.md).

asunset is its own signing authority for session tokens (D7 = option A):
RS256 keypair held by the API process, JWKS published at
GET /platform/sessions/jwks, issuer `urn:asunset:sessions:<realm>` by
default. Login tokens remain Keycloak's; validators select the JWKS
source by the `iss` claim (identity contract §5 amendment).

The token is never a self-sufficient credential: `sub` stays the human,
and effective permission is the session's declared grant subset ∩ the
human's live permissions, enforced by `SessionScopedAuthorizer` at the
decision point. Revocation and expiry are row-state on `agent_session`,
checked on every request — instant, no blocklists.
"""

from __future__ import annotations

import base64
import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from asunset_core.auth.authorizer import Authorizer
from asunset_core.config import CoreSettings
from asunset_core.logging import get_logger

log = get_logger("session_tokens")

SESSION_TOKEN_TYP = "asunset-session"
AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_REQUIRED_CLAIMS = ["exp", "iat", "sub", "iss", "aud"]


@dataclass(frozen=True)
class SessionSigner:
    private_key: RSAPrivateKey
    kid: str
    issuer: str

    def jwks(self) -> dict[str, Any]:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(  # type: ignore[attr-defined]
            self.private_key.public_key(), as_dict=True
        )
        jwk.update({"kid": self.kid, "use": "sig", "alg": "RS256"})
        return {"keys": [jwk]}


_signer: SessionSigner | None = None


def _kid_for(key: RSAPrivateKey) -> str:
    der = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()[:16]


def get_session_signer(settings: CoreSettings) -> SessionSigner:
    """Process-wide signer. Key comes from SESSION_TOKEN_PRIVATE_KEY_B64
    (base64-encoded PEM, generated/persisted by the operator or deploy
    tooling); when unset, an ephemeral key is generated so dev works out
    of the box — with the loud caveat that minted sessions die with the
    process."""
    global _signer
    if _signer is not None:
        return _signer

    pem_b64 = settings.session_token_private_key_b64
    if pem_b64:
        pem = base64.b64decode(pem_b64)
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, RSAPrivateKey):
            raise ValueError("SESSION_TOKEN_PRIVATE_KEY_B64 must be an RSA private key")
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        log.warning(
            "session_tokens.ephemeral_key",
            detail=(
                "SESSION_TOKEN_PRIVATE_KEY_B64 unset — generated an ephemeral "
                "signing key; agent sessions will NOT survive an api restart. "
                "Set a persistent key for any real deployment."
            ),
        )

    _signer = SessionSigner(
        private_key=key, kid=_kid_for(key), issuer=settings.resolved_session_token_issuer
    )
    return _signer


def reset_session_signer() -> None:
    """Test hook."""
    global _signer
    _signer = None


def mint_session_token(
    signer: SessionSigner,
    *,
    user_id: UUID,
    agent_id: str,
    session_id: UUID,
    audiences: list[str],
    ttl_seconds: int,
) -> str:
    now = int(time.time())
    claims = {
        "iss": signer.issuer,
        "sub": str(user_id),
        "aud": audiences,
        "iat": now,
        "exp": now + ttl_seconds,
        "sid": str(session_id),
        "typ": SESSION_TOKEN_TYP,
        # RFC 8693-style actor claim: who is acting for the human.
        "act": {"sub": f"agent:{agent_id}"},
    }
    return jwt.encode(
        claims, signer.private_key, algorithm="RS256", headers={"kid": signer.kid}
    )


class SessionTokenError(Exception):
    """Validation failure — message is safe to surface as a 401 detail."""


def validate_session_token(
    token: str, signer: SessionSigner, *, expected_audience: str
) -> dict[str, Any]:
    """Verify a session token against OUR key (we are the issuer — no
    HTTP fetch). Same posture as contract §5: RS256 only, audience and
    issuer enforced, required claims rejected-not-defaulted."""
    try:
        claims = jwt.decode(
            token,
            signer.private_key.public_key(),
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=signer.issuer,
            options={"require": _REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError as e:
        raise SessionTokenError("session token expired") from e
    except jwt.InvalidAudienceError as e:
        raise SessionTokenError("session token wrong audience") from e
    except jwt.InvalidTokenError as e:
        raise SessionTokenError(f"invalid session token: {e}") from e

    if claims.get("typ") != SESSION_TOKEN_TYP:
        raise SessionTokenError("not a session token")
    if not claims.get("sid"):
        raise SessionTokenError("session token missing sid")
    act_sub = (claims.get("act") or {}).get("sub", "")
    if not act_sub.startswith("agent:"):
        raise SessionTokenError("session token missing act.sub agent identity")
    return claims


def peek_issuer(token: str) -> str | None:
    """Unverified read of `iss` — used ONLY to select which validation
    path (Keycloak JWKS vs local session key) to run; every claim is
    still verified by the selected path."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        return None
    iss = claims.get("iss")
    return iss if isinstance(iss, str) else None


# --- grant subset semantics ------------------------------------------------


def session_allows(grants: list[dict[str, str]], relation: str, obj: str) -> bool:
    """Does the session's declared grant subset cover (relation, object)?

    Grant shape: {"relation": r, "object": pattern} where pattern is an
    exact object id ("note:abc"), a type wildcard ("note:*"), or "*".
    Relation "*" matches any relation. Deny-by-default.
    """
    for g in grants:
        g_rel = g.get("relation", "")
        if g_rel not in ("*", relation):
            continue
        pat = g.get("object", "")
        if pat == "*" or pat == obj:
            return True
        if pat.endswith(":*") and ":" in obj and obj.split(":", 1)[0] == pat[:-2]:
            return True
    return False


class SessionScopedAuthorizer:
    """Wraps the platform Authorizer with the ratified intersection:

        allowed = session's declared subset covers (relation, object)
              AND the human's LIVE permission (inner check)

    so a scoped session can never outlive the human's own access.
    Mutating/administrative surfaces (write, read_tuples) are refused
    outright — agent sessions hold data permissions, not authorization-
    administration rights.
    """

    def __init__(self, inner: Authorizer, grants: list[dict[str, str]]) -> None:
        self._inner = inner
        self._grants = grants

    async def check(self, user: str, relation: str, obj: str) -> bool:
        if not session_allows(self._grants, relation, obj):
            return False
        return await self._inner.check(user, relation, obj)

    async def list_objects(self, user: str, relation: str, object_type: str) -> list[str]:
        objs = await self._inner.list_objects(user, relation, object_type)
        return [o for o in objs if session_allows(self._grants, relation, o)]

    async def explain(self, user: str, relation: str, obj: str):  # noqa: ANN201
        return await self._inner.explain(user, relation, obj)

    async def explain_note_access(self, user: str, obj: str):  # noqa: ANN201
        return await self._inner.explain_note_access(user, obj)

    async def list_users(self, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError("agent sessions cannot enumerate grantees")

    async def read_tuples(self, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError("agent sessions cannot read authorization tuples")

    async def write(self, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError("agent sessions cannot modify authorization tuples")
