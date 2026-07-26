"""Matrix-row evidence for notes.archive (filled from the generated skeleton)."""

from asunset_core.features.codegen import assert_declaration_fingerprint
from asunset_core.testing import StaticAuthorizer, grant_feature

from tests.feature_matrix.conftest import gate_status, persona

FEATURE_KEY = "notes.archive"
EXPECTED_FINGERPRINT = "e0da899ca8d8642e"


def test_notes_archive_declaration_current() -> None:
    assert_declaration_fingerprint("features.yaml", FEATURE_KEY, EXPECTED_FINGERPRINT)


async def test_notes_archive_allowed_role_archivists_assignee() -> None:
    p = persona()
    authz = StaticAuthorizer()
    grant_feature(authz, p.fga_user(), FEATURE_KEY)  # the resolved assignee grant
    assert await gate_status(FEATURE_KEY, authz, p) == 200


async def test_notes_archive_denied_outsider() -> None:
    assert await gate_status(FEATURE_KEY, StaticAuthorizer(), persona()) == 403
