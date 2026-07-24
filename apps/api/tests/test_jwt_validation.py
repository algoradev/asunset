"""JWT validation suite — converts identity-contract §5 to test-verified.

Runs against a real ephemeral Keycloak that imported the REAL
realm-export.json (see conftest.keycloak): every token is genuinely
Keycloak-minted through the real protocol mappers, and every assertion
goes through the real `_validate_token` — the exact code path every
authenticated request crosses.

Covers the §5 contract: RS256-only, audience enforcement (the D6
property that a token without your aud entry is rejected
cryptographically), exact public-issuer matching (the split-issuer
rule), real expiry, required-claims rejection, and the JWKS behaviors —
300s cache, single force-refresh on unknown kid (key-rotation
tolerance), and refusal of forged/unknown/none-alg tokens.
"""

from __future__ import annotations

import base64
import json
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import PyJWKSet

from asunset_core.auth import oidc

from .conftest import KeycloakServer

ALICE_PW = "AliceDev-1234!"
BOB_PW = "BobDev-12345!"


@pytest.fixture(autouse=True)
def _fresh_jwks_cache():
    """The JWKS cache is a module singleton — isolate every test."""
    oidc._cache.keyset = None
    oidc._cache.fetched_at = 0.0
    yield
    oidc._cache.keyset = None
    oidc._cache.fetched_at = 0.0


async def _validate(keycloak: KeycloakServer, token: str, settings=None) -> dict:
    return await oidc._validate_token(token, settings or keycloak.settings())


def _expect_401(exc_info: pytest.ExceptionInfo, fragment: str) -> None:
    assert isinstance(exc_info.value, HTTPException)
    assert exc_info.value.status_code == 401
    assert fragment in str(exc_info.value.detail), (
        f"expected {fragment!r} in {exc_info.value.detail!r}"
    )


# --- happy path ------------------------------------------------------------


async def test_real_token_validates_with_contract_claims(keycloak: KeycloakServer) -> None:
    token = keycloak.user_token("bob", BOB_PW)
    claims = await _validate(keycloak, token)

    # The five required claims are present and coherent (§2.2).
    for required in ("exp", "iat", "sub", "iss", "aud"):
        assert required in claims
    assert claims["iss"] == keycloak.issuer
    aud = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
    assert "asunset-api" in aud  # the audience-api mapper did its job
    assert claims.get("sid"), "sid missing — audit session correlation depends on it"


async def test_realm_roles_flow_through_mapper(keycloak: KeycloakServer) -> None:
    token = keycloak.user_token("alice", ALICE_PW)
    claims = await _validate(keycloak, token)
    assert "platform_admin" in claims.get("realm_access", {}).get("roles", [])

    bob_claims = await _validate(keycloak, keycloak.user_token("bob", BOB_PW))
    assert "platform_admin" not in bob_claims.get("realm_access", {}).get("roles", [])


# --- audience (D6's cryptographic distinction) -----------------------------


async def test_token_without_aud_claim_rejected(keycloak: KeycloakServer) -> None:
    """No audience mapper → no aud claim at all → rejected as a MISSING
    required claim (§2.2: rejected, not defaulted) — a distinct branch
    from wrong-audience below, both of which must refuse."""
    token = keycloak.user_token("bob", BOB_PW, client_id="no-audience-client")
    with pytest.raises(HTTPException) as exc_info:
        await _validate(keycloak, token)
    _expect_401(exc_info, "aud")


async def test_token_with_foreign_audience_rejected(keycloak: KeycloakServer) -> None:
    """aud present but names another resource server → wrong audience.
    This is D6's cryptographic distinction doing its job."""
    token = keycloak.user_token("bob", BOB_PW, client_id="wrong-audience-client")
    with pytest.raises(HTTPException) as exc_info:
        await _validate(keycloak, token)
    _expect_401(exc_info, "wrong audience")


# --- expiry (real, not crafted) --------------------------------------------


async def test_expired_token_rejected(keycloak: KeycloakServer) -> None:
    token = keycloak.user_token("bob", BOB_PW, client_id="short-lived-client")
    time.sleep(2.5)  # lifespan is 1s
    with pytest.raises(HTTPException) as exc_info:
        await _validate(keycloak, token)
    _expect_401(exc_info, "expired")


# --- issuer (the split-issuer rule) ----------------------------------------


async def test_issuer_mismatch_names_the_classic_misconfig(keycloak: KeycloakServer) -> None:
    """iss is validated against the PUBLIC issuer — a validator whose
    configured public URL differs from what minted the token must
    reject, and the error must name KEYCLOAK_PUBLIC_URL (§5.1)."""
    token = keycloak.user_token("bob", BOB_PW)
    settings = keycloak.settings().model_copy(
        update={"keycloak_issuer": "https://wrong.example.test/auth/realms/asunset"}
    )
    with pytest.raises(HTTPException) as exc_info:
        await _validate(keycloak, token, settings)
    _expect_401(exc_info, "KEYCLOAK_PUBLIC_URL")


# --- malformed / forged / downgrade ----------------------------------------


async def test_garbage_token_rejected(keycloak: KeycloakServer) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await _validate(keycloak, "not-a-jwt-at-all")
    _expect_401(exc_info, "malformed")


async def test_token_without_kid_rejected(keycloak: KeycloakServer) -> None:
    token = pyjwt.encode({"sub": "x"}, "hs256-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        await _validate(keycloak, token)
    _expect_401(exc_info, "missing kid")


async def test_alg_none_downgrade_rejected(keycloak: KeycloakServer) -> None:
    """The classic none-alg attack: a hand-built token claiming alg=none
    (with a plausible kid) must never validate."""
    real = keycloak.user_token("bob", BOB_PW)
    real_kid = pyjwt.get_unverified_header(real)["kid"]
    payload = pyjwt.decode(real, options={"verify_signature": False})

    def b64(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    forged = f"{b64({'alg': 'none', 'kid': real_kid, 'typ': 'JWT'})}.{b64(payload)}."
    with pytest.raises(HTTPException) as exc_info:
        await _validate(keycloak, forged)
    _expect_401(exc_info, "invalid token")


async def test_forged_signature_with_real_kid_rejected(keycloak: KeycloakServer) -> None:
    """Attacker signs with their own key but spoofs the realm's kid —
    signature verification against the real JWKS key must fail."""
    real = keycloak.user_token("bob", BOB_PW)
    real_kid = pyjwt.get_unverified_header(real)["kid"]
    payload = pyjwt.decode(real, options={"verify_signature": False})

    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = pyjwt.encode(
        payload, attacker_key, algorithm="RS256", headers={"kid": real_kid}
    )
    with pytest.raises(HTTPException) as exc_info:
        await _validate(keycloak, forged)
    _expect_401(exc_info, "invalid token")


async def test_unknown_kid_rejected_after_one_refresh(keycloak: KeycloakServer) -> None:
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    real = keycloak.user_token("bob", BOB_PW)
    payload = pyjwt.decode(real, options={"verify_signature": False})
    forged = pyjwt.encode(
        payload, attacker_key, algorithm="RS256", headers={"kid": "attacker-kid"}
    )
    with pytest.raises(HTTPException) as exc_info:
        await _validate(keycloak, forged)
    _expect_401(exc_info, "signing key not found")


# --- JWKS cache + key-rotation tolerance -----------------------------------


def _foreign_keyset() -> PyJWKSet:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = pyjwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update({"kid": "stale-kid", "use": "sig", "alg": "RS256"})
    return PyJWKSet.from_dict({"keys": [jwk]})


async def test_rotation_tolerance_force_refreshes_once(keycloak: KeycloakServer) -> None:
    """Key rotation: the cached JWKS doesn't contain the token's kid →
    the validator invalidates and refetches ONCE, then succeeds. This is
    what lets Keycloak rotate signing keys without a platform restart."""
    oidc._cache.keyset = _foreign_keyset()  # a cache from "before rotation"
    oidc._cache.fetched_at = time.monotonic()  # still fresh — TTL won't save us

    token = keycloak.user_token("bob", BOB_PW)
    claims = await _validate(keycloak, token)  # must refresh + succeed
    assert claims["iss"] == keycloak.issuer


async def test_jwks_cache_is_reused_within_ttl(keycloak: KeycloakServer) -> None:
    await _validate(keycloak, keycloak.user_token("bob", BOB_PW))
    cached = oidc._cache.keyset
    assert cached is not None
    await _validate(keycloak, keycloak.user_token("bob", BOB_PW))
    assert oidc._cache.keyset is cached, "second validation refetched despite fresh TTL"
