"""Feature-level permissions (docs/feature-permissions-spec.md).

Features are FGA objects; grants are tuples to the platform usersets
asunset already maintains; the manifest (features.yaml) is the versioned
source of truth, reconciled into tuples on deploy.
"""

from asunset_core.features.scopes import (
    AuthorizerReader,
    ResolverNotRegistered,
    ScopeResolverRegistry,
    resolve_scope,
    reset_scope_registry,
    scope_registry,
)
from asunset_core.features.manifest import (
    FeatureDef,
    FeatureManifest,
    ManifestError,
    load_manifest,
    parse_manifest,
)
from asunset_core.features.reconcile import (
    FeatureReconcileReport,
    ReconcileRefused,
    reconcile_features,
)

__all__ = [
    "FeatureDef",
    "FeatureManifest",
    "FeatureReconcileReport",
    "ReconcileRefused",
    "ManifestError",
    "load_manifest",
    "parse_manifest",
    "reconcile_features",
    "AuthorizerReader",
    "ResolverNotRegistered",
    "ScopeResolverRegistry",
    "resolve_scope",
    "reset_scope_registry",
    "scope_registry",
]
