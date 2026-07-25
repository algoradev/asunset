"""Feat-ops 1: declared require_feature keys must exist in the manifest."""

from __future__ import annotations

import pytest

from asunset_core.features import parse_manifest

from asunset_api.features_boot import FeatureGateMismatch, validate_declared_gates
from asunset_api.routers.deps import DECLARED_FEATURE_GATES, require_feature


def test_audit_gate_is_registered() -> None:
    # Importing the audit router registered its gate.
    import asunset_api.routers.audit  # noqa: F401

    assert "audit.view" in DECLARED_FEATURE_GATES


def test_known_gates_validate() -> None:
    m = parse_manifest({"features": {k: {"grants": ["organization#member"]}
                                     for k in DECLARED_FEATURE_GATES}})
    validate_declared_gates(m)  # no raise


def test_unknown_gate_fails_loud() -> None:
    require_feature("totally.unknown_gate")
    try:
        m = parse_manifest(
            {"features": {"audit.view": {"grants": ["organization#member"]}}}
        )
        with pytest.raises(FeatureGateMismatch, match="totally.unknown_gate"):
            validate_declared_gates(m)
    finally:
        DECLARED_FEATURE_GATES.discard("totally.unknown_gate")


def test_no_manifest_with_gates_warns_not_raises() -> None:
    validate_declared_gates(None)  # warn path — must not raise
