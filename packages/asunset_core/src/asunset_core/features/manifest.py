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

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import yaml

FEATURE_KEY_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$")
ROLE_GRANT_RE = re.compile(r"^role:([a-z0-9][a-z0-9_-]{0,63})#assignee$")
ORG_GRANTS = ("organization#member", "organization#admin")
SEGMENT_RE = re.compile(r"^[a-z0-9_]+$")
RESOLVER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
RESOURCE_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ManifestError(ValueError):
    """Manifest failed validation — message names the offending entry."""


@dataclass(frozen=True)
class ScopePair:
    """Declared reach for one resource type (§11): a REFERENCE to a
    registered resolver, never inline logic (relay's non-DSL ceiling).
    Scope is per (capability, resource_type) — a set of pairs, single-
    type as the common degenerate case (juniper's amendment)."""

    resource_type: str
    resolver: str


@dataclass(frozen=True)
class FeatureDef:
    key: str
    description: str
    grants: tuple[str, ...]
    # Declared scopes (§11). Empty = undeclared (grandfathered v1 key —
    # reach lives in handler code, invisible to the matrix).
    scopes: tuple[ScopePair, ...] = ()
    # Declarative kill switch: `enabled: false` keeps the feature
    # DECLARED (gate-key validation still passes, the intent is visible
    # in the diff) while reconcile removes EVERY grant on it — defaults
    # AND runtime user/team grants. Runtime grants do not come back on
    # re-enable; they were operator data and the operator killed them.
    enabled: bool = True


@dataclass(frozen=True)
class FeatureManifest:
    features: tuple[FeatureDef, ...] = field(default_factory=tuple)
    # Per-area declared mode vocabulary (§11, juniper's structural key
    # lint): area prefix → closed set of legal final segments. A key
    # with ≥3 segments MUST have its prefix declared as an area and its
    # final segment in the area's modes — an object instance can't
    # sneak in as a segment because every legal segment was pre-declared.
    # 2-segment keys are grandfathered flat (degenerate areas).
    areas: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def keys(self) -> set[str]:
        return {f.key for f in self.features}

    def declared_resolvers(self) -> set[tuple[str, str]]:
        """(resource_type, resolver) pairs the manifest references —
        startup validates each against the registry, fail-loud."""
        return {
            (sp.resource_type, sp.resolver)
            for f in self.features
            for sp in f.scopes
        }

    def fingerprint(self, key: str) -> str:
        """Declaration fingerprint for a capability (§11, juniper #4):
        hash over key + grants + scope pairs. Filled test skeletons
        embed it; when the declaration changes, the skeleton's assert
        fails stale instead of passing against a dead claim."""
        f = next((x for x in self.features if x.key == key), None)
        if f is None:
            raise ManifestError(f"fingerprint requested for unknown key {key!r}")
        blob = "|".join(
            [f.key, ",".join(sorted(f.grants)), str(f.enabled)]
            + sorted(f"{sp.resource_type}:{sp.resolver}" for sp in f.scopes)
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

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

    areas: dict[str, tuple[str, ...]] = {}
    raw_areas = raw.get("areas") or {}
    if not isinstance(raw_areas, dict):
        raise ManifestError("`areas:` must be a mapping of area-prefix → {modes: [...]}")
    for prefix, body in raw_areas.items():
        if not FEATURE_KEY_RE.match(str(prefix)):
            raise ManifestError(f"area prefix {prefix!r} invalid — same format as feature keys")
        modes = (body or {}).get("modes") or []
        if not isinstance(modes, list) or not modes:
            raise ManifestError(f"area {prefix!r} must declare a non-empty modes list")
        for m in modes:
            if not SEGMENT_RE.match(str(m)):
                raise ManifestError(f"area {prefix!r} mode {m!r} invalid segment")
        areas[str(prefix)] = tuple(str(m) for m in modes)

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

        # §11 mode-vocabulary lint: ≥3-segment keys need a declared area
        # whose closed mode set contains the final segment.
        segments = str(key).split(".")
        if len(segments) >= 3:
            prefix, mode = ".".join(segments[:-1]), segments[-1]
            if prefix not in areas:
                raise ManifestError(
                    f"feature {key!r} has ≥3 segments but no declared area {prefix!r} — "
                    f"declare `areas: {{{prefix}: {{modes: [...]}}}}` (verb modes are "
                    f"legitimate; object instances are not, which is why the vocabulary "
                    f"is closed)"
                )
            if mode not in areas[prefix]:
                raise ManifestError(
                    f"feature {key!r}: segment {mode!r} not in area {prefix!r} modes "
                    f"{sorted(areas[prefix])} — add the mode to the area or fix the key"
                )

        # §11 declared scopes: references to registered resolvers only.
        scope_pairs: list[ScopePair] = []
        raw_scope = body.get("scope") or []
        if not isinstance(raw_scope, list):
            raise ManifestError(f"feature {key!r} `scope` must be a list of pairs")
        for sp in raw_scope:
            if not isinstance(sp, dict):
                raise ManifestError(f"feature {key!r} scope entries must be mappings")
            rt, rv = str(sp.get("resource_type", "")), str(sp.get("resolver", ""))
            if not RESOURCE_TYPE_RE.match(rt):
                raise ManifestError(f"feature {key!r} scope resource_type {rt!r} invalid")
            if not RESOLVER_NAME_RE.match(rv):
                raise ManifestError(
                    f"feature {key!r} scope resolver {rv!r} invalid — a registered "
                    f"resolver NAME, never inline logic"
                )
            if any(x.resource_type == rt for x in scope_pairs):
                raise ManifestError(
                    f"feature {key!r} declares resource_type {rt!r} twice"
                )
            scope_pairs.append(ScopePair(resource_type=rt, resolver=rv))

        defs.append(
            FeatureDef(
                key=str(key),
                description=str(body.get("description", "")),
                grants=tuple(str(g) for g in grants),
                enabled=enabled,
                scopes=tuple(scope_pairs),
            )
        )
    return FeatureManifest(features=tuple(defs), areas=areas)


def load_manifest(path: str | Path) -> FeatureManifest:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text())
    except FileNotFoundError:
        raise
    except yaml.YAMLError as e:
        raise ManifestError(f"{p}: not valid YAML: {e}") from e
    return parse_manifest(raw or {})
