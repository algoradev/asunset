"""Agent session token suite (D4 mint) — sign/validate/scope semantics.

Pure-core tests: no docker, no Keycloak. The signing authority is the
process itself (D7 = option A), so the full mint → validate → intersect
path is testable hermetically. Row-state (revocation/expiry) and RLS on
agent_session ride the DB suites.
"""

from __future__ import annotations

import time
from uuid import uuid4

import jwt
import pytest

from asunset_core.auth.session_tokens import (
    SESSION_TOKEN_TYP,
    SessionScopedAuthorizer,
    SessionSigner,
    SessionTokenError,
    mint_session_token,
    peek_issuer,
    session_allows,
    validate_session_token,
)

from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope="module")
def signer() -> SessionSigner:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return SessionSigner(private_key=key, kid="test-kid", issuer="urn:asunset:sessions:asunset")


def _mint(signer: SessionSigner, **overrides) -> str:
    args = dict(
        user_id=uuid4(),
        agent_id="vanta",
        session_id=uuid4(),
        audiences=["asunset-api", "opsroom-api"],
        ttl_seconds=600,
    )
    args.update(overrides)
    return mint_session_token(signer, **args)


# --- mint → validate roundtrip --------------------------------------------


def test_roundtrip_claims(signer: SessionSigner) -> None:
    uid, sid = uuid4(), uuid4()
    token = _mint(signer, user_id=uid, session_id=sid)
    claims = validate_session_token(token, signer, expected_audience="asunset-api")

    assert claims["sub"] == str(uid)          # sub is the HUMAN (D1)
    assert claims["sid"] == str(sid)          # fresh session id, not the SSO sid
    assert claims["act"] == {"sub": "agent:vanta"}
    assert claims["typ"] == SESSION_TOKEN_TYP
    assert claims["iss"] == signer.issuer
    assert "opsroom-api" in claims["aud"]


def test_each_rs_validates_its_own_audience(signer: SessionSigner) -> None:
    token = _mint(signer, audiences=["opsroom-api"])
    # The RS named in aud accepts…
    validate_session_token(token, signer, expected_audience="opsroom-api")
    # …an RS NOT in the subset rejects — D6's cryptographic distinction.
    with pytest.raises(SessionTokenError, match="wrong audience"):
        validate_session_token(token, signer, expected_audience="asunset-api")


def test_expired_token_rejected(signer: SessionSigner) -> None:
    token = _mint(signer, ttl_seconds=-10)
    with pytest.raises(SessionTokenError, match="expired"):
        validate_session_token(token, signer, expected_audience="asunset-api")


def test_wrong_issuer_rejected(signer: SessionSigner) -> None:
    other = SessionSigner(
        private_key=signer.private_key, kid=signer.kid, issuer="urn:asunset:sessions:other"
    )
    token = _mint(signer)
    with pytest.raises(SessionTokenError):
        validate_session_token(token, other, expected_audience="asunset-api")


def test_wrong_key_rejected(signer: SessionSigner) -> None:
    imposter_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    imposter = SessionSigner(private_key=imposter_key, kid="x", issuer=signer.issuer)
    token = mint_session_token(
        imposter,
        user_id=uuid4(), agent_id="evil", session_id=uuid4(),
        audiences=["asunset-api"], ttl_seconds=600,
    )
    with pytest.raises(SessionTokenError):
        validate_session_token(token, signer, expected_audience="asunset-api")


def test_login_shaped_token_without_typ_rejected(signer: SessionSigner) -> None:
    # A token signed with our key but missing typ/act (i.e. not a
    # session token) must not pass the session path.
    now = int(time.time())
    forged = jwt.encode(
        {"iss": signer.issuer, "sub": str(uuid4()), "aud": "asunset-api",
         "iat": now, "exp": now + 600, "sid": "abc"},
        signer.private_key, algorithm="RS256",
    )
    with pytest.raises(SessionTokenError, match="not a session token"):
        validate_session_token(forged, signer, expected_audience="asunset-api")


def test_peek_issuer_reads_without_verifying(signer: SessionSigner) -> None:
    assert peek_issuer(_mint(signer)) == signer.issuer
    assert peek_issuer("not-a-jwt") is None


def test_jwks_shape(signer: SessionSigner) -> None:
    jwks = signer.jwks()
    (key,) = jwks["keys"]
    assert key["kid"] == "test-kid"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert key["kty"] == "RSA"
    assert "d" not in key  # never the private half


# --- grant subset semantics -----------------------------------------------


@pytest.mark.parametrize(
    ("grants", "relation", "obj", "expected"),
    [
        ([{"relation": "can_view", "object": "note:abc"}], "can_view", "note:abc", True),
        ([{"relation": "can_view", "object": "note:abc"}], "can_view", "note:xyz", False),
        ([{"relation": "can_view", "object": "note:abc"}], "can_edit", "note:abc", False),
        ([{"relation": "can_view", "object": "note:*"}], "can_view", "note:xyz", True),
        ([{"relation": "can_view", "object": "note:*"}], "can_view", "report:xyz", False),
        ([{"relation": "*", "object": "note:abc"}], "can_delete", "note:abc", True),
        ([{"relation": "can_view", "object": "*"}], "can_view", "report:xyz", True),
        ([], "can_view", "note:abc", False),  # deny-by-default
    ],
)
def test_session_allows(grants, relation, obj, expected) -> None:
    assert session_allows(grants, relation, obj) is expected


# --- intersection at the authorizer ---------------------------------------


class _FakeAuthorizer:
    def __init__(self, allow: bool) -> None:
        self.allow = allow
        self.checked: list[tuple[str, str, str]] = []

    async def check(self, user: str, relation: str, obj: str) -> bool:
        self.checked.append((user, relation, obj))
        return self.allow

    async def list_objects(self, user: str, relation: str, object_type: str) -> list[str]:
        return ["note:a", "note:b", "report:c"]


async def test_intersection_requires_both() -> None:
    grants = [{"relation": "can_view", "object": "note:*"}]

    # session allows + human allows → allowed
    inner = _FakeAuthorizer(allow=True)
    scoped = SessionScopedAuthorizer(inner, grants)  # type: ignore[arg-type]
    assert await scoped.check("user:u", "can_view", "note:a") is True

    # session allows + human DENIES → denied (revoked human kills session)
    inner = _FakeAuthorizer(allow=False)
    scoped = SessionScopedAuthorizer(inner, grants)  # type: ignore[arg-type]
    assert await scoped.check("user:u", "can_view", "note:a") is False

    # session DENIES → denied without even asking the inner authorizer
    inner = _FakeAuthorizer(allow=True)
    scoped = SessionScopedAuthorizer(inner, grants)  # type: ignore[arg-type]
    assert await scoped.check("user:u", "can_edit", "note:a") is False
    assert inner.checked == []


async def test_list_objects_filtered_by_grants() -> None:
    grants = [{"relation": "can_view", "object": "note:*"}]
    scoped = SessionScopedAuthorizer(_FakeAuthorizer(allow=True), grants)  # type: ignore[arg-type]
    assert await scoped.list_objects("user:u", "can_view", "note") == ["note:a", "note:b"]


async def test_admin_surfaces_refused() -> None:
    scoped = SessionScopedAuthorizer(_FakeAuthorizer(allow=True), [])  # type: ignore[arg-type]
    with pytest.raises(PermissionError):
        await scoped.write(writes=[])
    with pytest.raises(PermissionError):
        await scoped.read_tuples()
