"""Matrix-row evidence for notes.share.basic."""

from asunset_core.features import resolve_scope
from asunset_core.features.codegen import assert_declaration_fingerprint
from asunset_core.features.manifest import load_manifest
from asunset_core.testing import StaticAuthorizer, grant_feature

from tests.feature_matrix.conftest import gate_status, persona

FEATURE_KEY = "notes.share.basic"
EXPECTED_FINGERPRINT = "db838a5f09a92684"


def test_notes_share_basic_declaration_current() -> None:
    assert_declaration_fingerprint("features.yaml", FEATURE_KEY, EXPECTED_FINGERPRINT)


async def test_notes_share_basic_allowed_organization_member() -> None:
    p = persona()
    authz = StaticAuthorizer()
    grant_feature(authz, p.fga_user(), FEATURE_KEY)  # the resolved member grant
    assert await gate_status(FEATURE_KEY, authz, p) == 200


async def test_notes_share_basic_denied_outsider() -> None:
    assert await gate_status(FEATURE_KEY, StaticAuthorizer(), persona()) == 403


async def test_notes_share_basic_scope_is_shareable_notes() -> None:
    """Declared reach is share authority, not view authority."""
    from asunset_core.features import reset_scope_registry

    import asunset_api.authz_scopes as scopes

    reset_scope_registry()
    scopes.register_scopes()

    p = persona()
    authz = StaticAuthorizer()
    authz.allow(p.fga_user(), "can_delete", "note:can-share")
    authz.allow(p.fga_user(), "can_view", "note:view-only")
    authz.allow("user:someone-else", "can_delete", "note:other")

    manifest = load_manifest("features.yaml")
    ids = await resolve_scope(manifest, FEATURE_KEY, "note", p, authz)
    assert sorted(ids) == ["can-share"]
