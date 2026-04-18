"""Helpers for composing OpenFGA authorization models.

Consumer products spread `PLATFORM_TYPES` into their own model and
append their resource types. Keeps the org/team/user plumbing
consistent across every product built on asunset.

The DSL-equivalent of PLATFORM_TYPES is:

    model
      schema 1.1
    type user
    type organization
      relations
        define admin: [user]
        define member: [user]
    type team
      relations
        define org: [organization]
        define admin: [user]
        define member: [user]
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.1"

PLATFORM_TYPES: list[dict[str, Any]] = [
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
]


def build_model(resource_types: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a complete authorization model by appending the product's
    resource types to the platform's baseline.

    Usage:
        REPORT_TYPE = {"type": "report", ...}
        AUTHORIZATION_MODEL = build_model([REPORT_TYPE])
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "type_definitions": PLATFORM_TYPES + list(resource_types),
    }
