"""Product authorization model.

Composes platform types (user, organization, team) from asunset_core
with this product's resource types. `bootstrap_openfga(settings, model)`
at startup pins whatever this file exports.

Edit `REPORT_TYPE` below to reshape permissions on your resource, or
add more type-defs to `PRODUCT_TYPES` as your model grows.

A human-readable DSL version lives at `infra/fga-extension.fga`; keep
the two in sync when editing.
"""

from __future__ import annotations

from typing import Any

from asunset_core.fga.model import build_model

REPORT_TYPE: dict[str, Any] = {
    "type": "report",
    "relations": {
        "owner": {"this": {}},
        "team": {"this": {}},
        "viewer": {"this": {}},
        "can_view": {
            "union": {
                "child": [
                    {"computedUserset": {"relation": "owner"}},
                    {"computedUserset": {"relation": "viewer"}},
                ]
            }
        },
        "can_delete": {
            "computedUserset": {"relation": "owner"},
        },
    },
    "metadata": {
        "relations": {
            "owner": {"directly_related_user_types": [{"type": "user"}]},
            "team": {"directly_related_user_types": [{"type": "team"}]},
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

PRODUCT_TYPES = [REPORT_TYPE]

AUTHORIZATION_MODEL = build_model(PRODUCT_TYPES)
