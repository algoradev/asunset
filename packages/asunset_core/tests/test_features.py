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
        lambda r: r["features"]["reports.export"].update({"grants": []}),
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
    assert "class Feature(str, Enum):" in py
    ts = ts_module(m)
    assert '"reports.export"' in ts
    assert "export type FeatureKey" in ts
