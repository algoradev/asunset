"""Feature manifest + codegen — pure-logic tests (reconcile is covered
against a live OpenFGA in apps/api/tests/test_feature_permissions.py)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from asunset_core.features import ManifestError, parse_manifest
from asunset_core.features.codegen import python_module, ts_module

ORG = uuid4()


def _valid():
    return {
        "features": {
            "reports.export": {"description": "Export", "grants": ["organization#member"]},
            "billing.manage": {"grants": ["organization#admin"]},
            "compliance.review": {"grants": ["role:compliance_reviewer#assignee"]},
        }
    }


def test_parse_and_desired_tuples() -> None:
    m = parse_manifest(_valid())
    assert m.keys == {"reports.export", "billing.manage", "compliance.review"}
    tuples = m.desired_tuples(ORG)
    assert (f"organization:{ORG}#member", "can_use", "feature:reports.export") in tuples
    assert (f"organization:{ORG}#admin", "can_use", "feature:billing.manage") in tuples
    assert (
        "role:compliance_reviewer#assignee", "can_use", "feature:compliance.review"
    ) in tuples
    assert len(tuples) == 3


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["features"].update({"BadKey": {"grants": ["organization#member"]}}),
        lambda r: r["features"].update({"noverb": {"grants": ["organization#member"]}}),
        lambda r: r["features"]["reports.export"].update({"grants": "organization#member"}),
        lambda r: r["features"]["reports.export"].update({"grants": ["user:abc"]}),
        lambda r: r["features"]["reports.export"].update({"grants": ["team#member"]}),
        lambda r: r["features"]["reports.export"].update({"grants": ["role:X#assignee"]}),
    ],
)
def test_invalid_manifests_rejected(mutation) -> None:
    raw = _valid()
    mutation(raw)
    with pytest.raises(ManifestError):
        parse_manifest(raw)


def test_top_level_shape_required() -> None:
    with pytest.raises(ManifestError):
        parse_manifest({"notfeatures": {}})


def test_codegen_python_and_ts() -> None:
    m = parse_manifest(_valid())
    py = python_module(m)
    assert 'REPORTS_EXPORT = "reports.export"' in py
    assert "class Feature(StrEnum):" in py
    ts = ts_module(m)
    assert '"reports.export"' in ts
    assert "export type FeatureKey" in ts


def test_enabled_flag_parsed_and_excluded_from_desired() -> None:
    raw = _valid()
    raw["features"]["reports.export"]["enabled"] = False
    m = parse_manifest(raw)
    assert m.disabled_keys == {"reports.export"}
    tuples = m.desired_tuples(ORG)
    assert not any(o == "feature:reports.export" for (_, _, o) in tuples)
    assert len(tuples) == 2


def test_enabled_must_be_boolean() -> None:
    raw = _valid()
    raw["features"]["reports.export"]["enabled"] = "yes"
    with pytest.raises(ManifestError):
        parse_manifest(raw)


def test_declared_only_feature_has_no_default_tuples() -> None:
    # The runtime-only pattern (Relay): declared, gates validate,
    # zero default grants — every grant is runtime data.
    raw = _valid()
    raw["features"]["mcp.write_project"] = {"grants": []}
    m = parse_manifest(raw)
    assert "mcp.write_project" in m.keys
    assert not any(o == "feature:mcp.write_project" for (_, _, o) in m.desired_tuples(ORG))


def test_codegen_cli_works_with_areas(tmp_path) -> None:
    # Exercise-3 regression: running codegen AS A SCRIPT with an areas:
    # manifest crashed (entrypoint sat above areas_python's def, so
    # script-mode executed main() before the helper existed). Pin the
    # script path, not just the import path.
    import subprocess
    import sys

    manifest = tmp_path / "features.yaml"
    manifest.write_text(
        "areas:\n  a.b:\n    modes: [c]\n"
        "features:\n  a.b.c:\n    grants: [organization#member]\n"
    )
    out_py = tmp_path / "gen.py"
    subprocess.run(
        [sys.executable, "-m", "asunset_core.features.codegen",
         str(manifest), "--py", str(out_py)],
        check=True, capture_output=True,
    )
    assert "FEATURE_AREAS" in out_py.read_text()
