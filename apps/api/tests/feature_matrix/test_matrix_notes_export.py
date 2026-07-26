"""Matrix-row evidence for notes.export — the DECLARED-SCOPE reference:
gate per persona AND the resolver as the sole reach authority."""

from asunset_core.features import resolve_scope
from asunset_core.features.codegen import assert_declaration_fingerprint
from asunset_core.features.manifest import load_manifest
from asunset_core.testing import StaticAuthorizer, grant_feature

from tests.feature_matrix.conftest import gate_status, persona

FEATURE_KEY = "notes.export"
EXPECTED_FINGERPRINT = "bd5f4db4512a5a84"


def test_notes_export_declaration_current() -> None:
    assert_declaration_fingerprint("features.yaml", FEATURE_KEY, EXPECTED_FINGERPRINT)


async def test_notes_export_allowed_organization_member() -> None:
    p = persona()
    authz = StaticAuthorizer()
    grant_feature(authz, p.fga_user(), FEATURE_KEY)
    assert await gate_status(FEATURE_KEY, authz, p) == 200


async def test_notes_export_denied_outsider() -> None:
    assert await gate_status(FEATURE_KEY, StaticAuthorizer(), persona()) == 403


async def test_notes_export_scope_is_resolver_derived() -> None:
    """Declared reach: resolve_scope returns exactly what the read-only
    authorizer facade admits — including owned notes (ownership derives
    can_view; no owner-union needed, ever)."""
    import asunset_api.authz_scopes as scopes

    from asunset_core.features import reset_scope_registry

    reset_scope_registry()
    scopes.register_scopes()

    p = persona()
    authz = StaticAuthorizer()
    authz.allow(p.fga_user(), "can_view", "note:abc")
    authz.allow(p.fga_user(), "can_view", "note:def")
    authz.allow("user:someone-else", "can_view", "note:zzz")

    manifest = load_manifest("features.yaml")
    ids = await resolve_scope(manifest, FEATURE_KEY, "note", p, authz)
    assert sorted(ids) == ["abc", "def"]
