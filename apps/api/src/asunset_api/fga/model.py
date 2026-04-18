"""OpenFGA authorization model for the Notes demo.

Composes the platform types from asunset_core with the Notes resource
type. Consumer products follow the same pattern: import PLATFORM_TYPES
via build_model(), append their resource(s).

Keep `model.fga` (the DSL-readable equivalent) next to this file in sync
for humans; the JSON form is what gets pinned at bootstrap.
"""

from __future__ import annotations

from asunset_core.fga.model import build_model

NOTE_TYPE: dict = {
    "type": "note",
    "relations": {
        "owner": {"this": {}},
        "team": {"this": {}},
        "editor": {"this": {}},
        "viewer": {"this": {}},
        "can_edit": {
            "union": {
                "child": [
                    {"computedUserset": {"relation": "owner"}},
                    {"computedUserset": {"relation": "editor"}},
                    {
                        "tupleToUserset": {
                            "tupleset": {"relation": "team"},
                            "computedUserset": {"relation": "admin"},
                        }
                    },
                ]
            }
        },
        "can_view": {
            "union": {
                "child": [
                    {"computedUserset": {"relation": "can_edit"}},
                    {"computedUserset": {"relation": "viewer"}},
                ]
            }
        },
        "can_delete": {
            "union": {
                "child": [
                    {"computedUserset": {"relation": "owner"}},
                    {
                        "tupleToUserset": {
                            "tupleset": {"relation": "team"},
                            "computedUserset": {"relation": "admin"},
                        }
                    },
                ]
            }
        },
    },
    "metadata": {
        "relations": {
            "owner": {"directly_related_user_types": [{"type": "user"}]},
            "team": {"directly_related_user_types": [{"type": "team"}]},
            "editor": {
                "directly_related_user_types": [
                    {"type": "user"},
                    {"type": "team", "relation": "member"},
                ]
            },
            "viewer": {
                "directly_related_user_types": [
                    {"type": "user"},
                    {"type": "team", "relation": "member"},
                    {"type": "organization", "relation": "member"},
                ]
            },
        }
    },
}

AUTHORIZATION_MODEL = build_model([NOTE_TYPE])
