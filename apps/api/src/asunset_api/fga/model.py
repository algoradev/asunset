"""OpenFGA authorization model, encoded as the JSON shape the API expects.

The source of truth for humans is `model.fga` in this directory — keep the
two in sync when editing. The JSON form is what gets applied on bootstrap
(transforming .fga → JSON at runtime would require pulling the openfga
language parser; the JSON is small enough to maintain by hand).
"""

from __future__ import annotations

AUTHORIZATION_MODEL: dict = {
    "schema_version": "1.1",
    "type_definitions": [
        {"type": "user"},
        {
            "type": "organization",
            "relations": {
                "admin": {"this": {}},
                "member": {"this": {}},
            },
            "metadata": {
                "relations": {
                    "admin": {"directly_related_user_types": [{"type": "user"}]},
                    "member": {"directly_related_user_types": [{"type": "user"}]},
                }
            },
        },
        {
            "type": "team",
            "relations": {
                "org": {"this": {}},
                "admin": {"this": {}},
                "member": {"this": {}},
            },
            "metadata": {
                "relations": {
                    "org": {"directly_related_user_types": [{"type": "organization"}]},
                    "admin": {"directly_related_user_types": [{"type": "user"}]},
                    "member": {"directly_related_user_types": [{"type": "user"}]},
                }
            },
        },
        {
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
        },
    ],
}
