"""Matrix-row evidence for audit.view (filled from the generated skeleton)."""

from asunset_core.features.codegen import assert_declaration_fingerprint
from asunset_core.testing import StaticAuthorizer, grant_feature

from tests.feature_matrix.conftest import gate_status, persona

FEATURE_KEY = "audit.view"
EXPECTED_FINGERPRINT = "17f2c5fc096448d2"


def test_audit_view_declaration_current() -> None:
    assert_declaration_fingerprint("features.yaml", FEATURE_KEY, EXPECTED_FINGERPRINT)


async def test_audit_view_allowed_organization_member() -> None:
    p = persona()
    authz = StaticAuthorizer()
    grant_feature(authz, p.fga_user(), FEATURE_KEY)  # the resolved member grant
    assert await gate_status(FEATURE_KEY, authz, p) == 200


async def test_audit_view_denied_outsider() -> None:
    assert await gate_status(FEATURE_KEY, StaticAuthorizer(), persona()) == 403
