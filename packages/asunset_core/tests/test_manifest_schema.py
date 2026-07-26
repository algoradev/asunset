"""The shipped JSON Schema must agree with the Python validator —
editors and the loader may never disagree about what's legal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

jsonschema = pytest.importorskip("jsonschema")

SCHEMA = json.loads(
    (Path(__file__).parents[1] / "src/asunset_core/features/features.schema.json").read_text()
)


def _ok(doc: dict) -> None:
    jsonschema.validate(doc, SCHEMA)


def _bad(doc: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, SCHEMA)


def test_valid_shapes_pass() -> None:
    _ok({"features": {"reports.export": {"description": "x",
                                         "grants": ["organization#member"]}}})
    _ok({"features": {"a.b": {"grants": []}}})                     # runtime-only
    _ok({"features": {"a.b": {"grants": ["role:x_1#assignee"], "enabled": False}}})
    _ok({"features": {"opsroom.tables.create": {"grants": ["organization#admin"]}}})


def test_invalid_shapes_fail() -> None:
    _bad({"features": {"BadKey": {"grants": []}}})
    _bad({"features": {"noverb": {"grants": []}}})
    _bad({"features": {"a.b": {"grants": ["user:abc"]}}})
    _bad({"features": {"a.b": {"grants": ["team#member"]}}})
    _bad({"features": {"a.b": {"enabled": "yes", "grants": []}}})
    _bad({"features": {"a.b": {"grants": [], "unknown_field": 1}}})
    _bad({"notfeatures": {}})


def test_shipped_manifests_validate() -> None:
    repo = Path(__file__).parents[3]
    for rel in ("apps/api/features.yaml", "consuming-template/features.yaml"):
        doc = yaml.safe_load((repo / rel).read_text())
        jsonschema.validate(doc, SCHEMA)


def test_scope_and_areas_shapes() -> None:
    _ok({"areas": {"notes.export": {"modes": ["basic", "full"]}},
         "features": {"notes.export.basic": {
             "grants": ["organization#member"],
             "scope": [{"resource_type": "note", "resolver": "visible_notes"}]}}})
    _bad({"features": {"a.b": {"grants": [], "scope": [{"resource_type": "note"}]}}})
    _bad({"features": {"a.b": {"grants": [], "scope": [
        {"resource_type": "note", "resolver": "no spaces allowed"}]}}})
    _bad({"areas": {"a.b": {"modes": []}}, "features": {"a.b": {"grants": []}}})
    _bad({"areas": {"a.b": {"modes": ["c"], "extra": 1}}, "features": {"a.b": {"grants": []}}})
