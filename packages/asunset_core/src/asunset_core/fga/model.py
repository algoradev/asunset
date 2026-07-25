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


# --- feature-registration types (docs/feature-permissions-spec.md) --------
# Optional platform types: spread FEATURE_PLATFORM_TYPES into build_model
# alongside your resource types to enable feature-level permissions.
# DSL equivalent:
#
#     type service_account
#     type role
#       relations
#         define assignee: [user, role#assignee]
#     type feature
#       relations
#         define can_use: [user, organization#member, organization#admin,
#                          team#member, role#assignee, service_account]
#
# Deliberate adaptations from the generic "custom roles" pattern:
# common grants go DIRECTLY to the org/team usersets asunset already
# maintains (no role-object mirror of admin/member — that would be a
# third copy of role truth); `role` exists only for product-defined
# custom roles; `service_account` is for genuine machines (never agents
# — D1). Features are instance-global while one-org-per-instance holds.

SERVICE_ACCOUNT_TYPE: dict[str, Any] = {"type": "service_account"}

ROLE_TYPE: dict[str, Any] = {
    "type": "role",
    "relations": {"assignee": {"this": {}}},
    "metadata": {
        "relations": {
            "assignee": {
                "directly_related_user_types": [
                    {"type": "user"},
                    {"type": "role", "relation": "assignee"},
                ]
            },
        }
    },
}

FEATURE_TYPE: dict[str, Any] = {
    "type": "feature",
    "relations": {"can_use": {"this": {}}},
    "metadata": {
        "relations": {
            "can_use": {
                "directly_related_user_types": [
                    {"type": "user"},
                    {"type": "organization", "relation": "member"},
                    {"type": "organization", "relation": "admin"},
                    {"type": "team", "relation": "member"},
                    {"type": "role", "relation": "assignee"},
                    {"type": "service_account"},
                ]
            },
        }
    },
}

FEATURE_PLATFORM_TYPES: list[dict[str, Any]] = [
    SERVICE_ACCOUNT_TYPE,
    ROLE_TYPE,
    FEATURE_TYPE,
]


def build_model(resource_types: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a complete authorization model by appending the product's
    resource types to the platform's baseline.

    Usage:
        REPORT_TYPE = {"type": "report", ...}
        AUTHORIZATION_MODEL = build_model([REPORT_TYPE])

    To enable feature-level permissions, spread the optional types in:
        AUTHORIZATION_MODEL = build_model([*FEATURE_PLATFORM_TYPES, REPORT_TYPE])
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "type_definitions": PLATFORM_TYPES + list(resource_types),
    }
