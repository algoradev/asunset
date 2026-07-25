"""Feature manifest — the versioned source of truth for what features exist.

One `features.yaml` per consumer repo (docs/feature-permissions-spec.md §4):

    features:
      reports.export:
        description: "Export reports to CSV/PDF"
        grants:
          - organization#member
      billing.manage:
        description: "Manage billing settings"
        grants:
          - organization#admin
      compliance.review:
        description: "Review flagged items"
        grants:
          - role:compliance_reviewer#assignee

Rules enforced here:
  - key format `domain.verb(.sub)*`, lowercase — the key IS the FGA
    object id (`feature:<key>`), so typos become load errors, not
    silent 403s.
  - grants are DEFAULTS, expressed as usersets only: `organization#member`,
    `organization#admin`, or `role:<name>#assignee`. Direct user grants
    are runtime data (admin/API), never manifest entries.
  - team usersets are deliberately not manifest-able in v1: a manifest is
    instance-static while teams are runtime data; granting a feature to a
    specific team is a runtime tuple write like any user grant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import yaml

FEATURE_KEY_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$")
ROLE_GRANT_RE = re.compile(r"^role:([a-z0-9][a-z0-9_-]{0,63})#assignee$")
ORG_GRANTS = ("organization#member", "organization#admin")


class ManifestError(ValueError):
    """Manifest failed validation — message names the offending entry."""


@dataclass(frozen=True)
class FeatureDef:
    key: str
    description: str
    grants: tuple[str, ...]
    # Declarative kill switch: `enabled: false` keeps the feature
    # DECLARED (gate-key validation still passes, the intent is visible
    # in the diff) while reconcile removes EVERY grant on it — defaults
    # AND runtime user/team grants. Runtime grants do not come back on
    # re-enable; they were operator data and the operator killed them.
    enabled: bool = True


@dataclass(frozen=True)
class FeatureManifest:
    features: tuple[FeatureDef, ...] = field(default_factory=tuple)

    @property
    def keys(self) -> set[str]:
        return {f.key for f in self.features}

    @property
    def disabled_keys(self) -> set[str]:
        return {f.key for f in self.features if not f.enabled}

    def desired_tuples(self, org_id: UUID | str) -> set[tuple[str, str, str]]:
        """The (user, relation, object) set the manifest declares, with
        org usersets resolved against THE org (one per instance).
        Disabled features contribute nothing."""
        out: set[tuple[str, str, str]] = set()
        for f in self.features:
            if not f.enabled:
                continue
            for grant in f.grants:
                if grant in ORG_GRANTS:
                    relation = grant.split("#", 1)[1]
                    user = f"organization:{org_id}#{relation}"
                else:  # validated as role:<name>#assignee at load time
                    user = grant
                out.add((user, "can_use", f"feature:{f.key}"))
        return out


def parse_manifest(raw: dict) -> FeatureManifest:
    if not isinstance(raw, dict) or not isinstance(raw.get("features"), dict):
        raise ManifestError("manifest must be a mapping with a top-level `features:` map")

    defs: list[FeatureDef] = []
    for key, body in raw["features"].items():
        if not FEATURE_KEY_RE.match(str(key)):
            raise ManifestError(
                f"feature key {key!r} invalid — must match domain.verb "
                f"(lowercase, dot-separated, e.g. reports.export)"
            )
        body = body or {}
        if not isinstance(body, dict):
            raise ManifestError(f"feature {key!r} body must be a mapping")
        # Grants are DEFAULTS and may be empty: a declared-but-no-defaults
        # feature (grants: []) is the runtime-only pattern — it exists,
        # gates validate, and every grant is runtime data (Relay's
        # review: don't force overexposure or dummy roles just to
        # satisfy schema).
        grants = body.get("grants") or []
        if not isinstance(grants, list):
            raise ManifestError(f"feature {key!r} grants must be a list (may be empty)")
        for g in grants:
            if g not in ORG_GRANTS and not ROLE_GRANT_RE.match(str(g)):
                raise ManifestError(
                    f"feature {key!r} grant {g!r} invalid — allowed: "
                    f"{', '.join(ORG_GRANTS)}, or role:<name>#assignee "
                    f"(direct user/team grants are runtime data, not manifest entries)"
                )
        enabled = body.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ManifestError(f"feature {key!r} `enabled` must be a boolean")
        defs.append(
            FeatureDef(
                key=str(key),
                description=str(body.get("description", "")),
                grants=tuple(str(g) for g in grants),
                enabled=enabled,
            )
        )
    return FeatureManifest(features=tuple(defs))


def load_manifest(path: str | Path) -> FeatureManifest:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text())
    except FileNotFoundError:
        raise
    except yaml.YAMLError as e:
        raise ManifestError(f"{p}: not valid YAML: {e}") from e
    return parse_manifest(raw or {})
