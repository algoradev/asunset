"""§11 capability model: manifest v2, scope registry, generators."""

from __future__ import annotations

import pytest

from asunset_core.auth.principal import Principal
from asunset_core.features import (
    AuthorizerReader,
    ManifestError,
    ResolverNotRegistered,
    ScopeResolverRegistry,
    parse_manifest,
    reset_scope_registry,
    resolve_scope,
    scope_registry,
)
from asunset_core.features.matrix import matrix_markdown, skeleton_source, write_skeletons
from uuid import uuid4


def _capability_manifest():
    return parse_manifest(
        {
            "areas": {"notes.export": {"modes": ["basic", "full"]}},
            "features": {
                "notes.export.basic": {
                    "grants": ["organization#member"],
                    "scope": [{"resource_type": "note", "resolver": "visible_notes"}],
                },
                "notes.export.full": {
                    "grants": ["organization#admin"],
                    "scope": [
                        {"resource_type": "note", "resolver": "org_notes"},
                        {"resource_type": "attachment", "resolver": "note_attachments"},
                    ],
                },
                "audit.view": {"grants": ["organization#member"]},
            },
        }
    )


# --- mode vocabulary (the structural key lint) -----------------------------


def test_mode_vocabulary_enforced() -> None:
    m = _capability_manifest()
    assert m.areas["notes.export"] == ("basic", "full")

    with pytest.raises(ManifestError, match="no declared area"):
        parse_manifest({"features": {"a.b.c": {"grants": []}}})
    with pytest.raises(ManifestError, match="not in area"):
        parse_manifest(
            {
                "areas": {"a.b": {"modes": ["c"]}},
                "features": {"a.b.project_demo": {"grants": []}},
            }
        )


def test_flat_keys_grandfathered() -> None:
    # 2-segment keys need no area — degenerate single-capability areas.
    m = parse_manifest({"features": {"audit.view": {"grants": []}}})
    assert "audit.view" in m.keys


# --- scope declarations ----------------------------------------------------


def test_scope_pairs_and_ceilings() -> None:
    m = _capability_manifest()
    f = next(x for x in m.features if x.key == "notes.export.full")
    assert {(sp.resource_type, sp.resolver) for sp in f.scopes} == {
        ("note", "org_notes"), ("attachment", "note_attachments"),
    }
    with pytest.raises(ManifestError, match="twice"):
        parse_manifest(
            {"features": {"a.b": {"grants": [], "scope": [
                {"resource_type": "note", "resolver": "x"},
                {"resource_type": "note", "resolver": "y"},
            ]}}}
        )
    with pytest.raises(ManifestError, match="resolver"):
        parse_manifest(
            {"features": {"a.b": {"grants": [], "scope": [
                {"resource_type": "note", "resolver": "SELECT * FROM notes"},
            ]}}}
        )


def test_fingerprint_tracks_declaration() -> None:
    m1 = _capability_manifest()
    fp1 = m1.fingerprint("notes.export.basic")
    assert m1.fingerprint("notes.export.basic") == fp1  # stable
    m2 = parse_manifest(
        {
            "areas": {"notes.export": {"modes": ["basic", "full"]}},
            "features": {
                "notes.export.basic": {
                    "grants": ["organization#admin"],  # changed
                    "scope": [{"resource_type": "note", "resolver": "visible_notes"}],
                },
            },
        }
    )
    assert m2.fingerprint("notes.export.basic") != fp1


# --- registry + narrow-only facade -----------------------------------------


async def test_registry_and_resolution() -> None:
    reg = ScopeResolverRegistry()

    async def r(principal, reader):  # noqa: ANN001, ANN202
        return ["1"]

    reg.register("note", "visible_notes", r)
    with pytest.raises(ValueError, match="already registered"):
        reg.register("note", "visible_notes", r)
    with pytest.raises(ResolverNotRegistered):
        reg.get("note", "phantom")
    reg.validate_manifest({("note", "visible_notes")})
    with pytest.raises(ResolverNotRegistered, match="phantom"):
        reg.validate_manifest({("note", "phantom")})


async def test_reader_facade_is_read_only() -> None:
    # The narrow-only rule by construction: the facade simply has no
    # write surface — nothing to misuse, lifecycle-blind by signature.
    from asunset_core.testing import StaticAuthorizer

    reader = AuthorizerReader(StaticAuthorizer())
    assert not hasattr(reader, "write")
    assert not hasattr(reader, "explain")
    assert await reader.check("user:u", "can_view", "note:1") is False


async def test_resolve_scope_end_to_end() -> None:
    from asunset_core.testing import StaticAuthorizer

    reset_scope_registry()

    async def visible_notes(principal, reader):  # noqa: ANN001, ANN202
        objs = await reader.list_objects(principal.fga_user(), "can_view", "note")
        return [o.removeprefix("note:") for o in objs]

    scope_registry().register("note", "visible_notes", visible_notes)
    m = _capability_manifest()
    p = Principal(user_id=uuid4(), email="u@t", display_name="U")
    a = StaticAuthorizer().allow(p.fga_user(), "can_view", "note:42")
    assert await resolve_scope(m, "notes.export.basic", "note", p, a) == ["42"]
    # undeclared resource_type on a capability = design gap, not empty list
    with pytest.raises(ResolverNotRegistered, match="no scope"):
        await resolve_scope(m, "audit.view", "note", p, a)
    reset_scope_registry()


# --- generators ------------------------------------------------------------


def test_matrix_markdown_projection() -> None:
    md = matrix_markdown(_capability_manifest())
    assert "| `notes.export.full` | enabled | organization#admin | note → org_notes; attachment → note_attachments |" in md
    assert "*undeclared (grandfathered)*" in md  # audit.view row
    assert "notes.export`: basic, full" in md


def test_skeletons_fail_until_filled_and_never_overwrite(tmp_path) -> None:  # noqa: ANN001
    m = _capability_manifest()
    src = skeleton_source(m, "notes.export.basic")
    assert "pytest.fail" in src and "EXPECTED_FINGERPRINT" in src
    assert m.fingerprint("notes.export.basic") in src

    created, skipped = write_skeletons(m, tmp_path)
    assert len(created) == 3 and skipped == []
    # fill one, regenerate — the filled file survives
    filled = tmp_path / created[0]
    filled.write_text("# filled by a human\n")
    created2, skipped2 = write_skeletons(m, tmp_path)
    assert created2 == [] and len(skipped2) == 3
    assert filled.read_text() == "# filled by a human\n"
