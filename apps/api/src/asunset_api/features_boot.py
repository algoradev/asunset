"""Feature manifest plumbing: startup validation + reconcile entrypoints.

Grants reference the instance's single org (`organization:<id>#member`),
so reconciliation needs the org row. Pre-bootstrap there isn't one —
the startup hook logs and skips, and POST /platform/bootstrap calls it
again right after creating the org. A missing/invalid manifest never
blocks startup (deployments without feature gates must keep working) —
but a DECLARED GATE whose key the manifest doesn't know is a hard boot
failure: that endpoint would 403 for everyone forever, and the only
cheap moment to catch the typo is now.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from asunset_core.auth.authorizer import Authorizer
from asunset_core.db.models import Organization
from asunset_core.db.session import get_admin_session_factory
from asunset_core.features import (
    FeatureManifest,
    FeatureReconcileReport,
    ManifestError,
    load_manifest,
    reconcile_features,
)
from asunset_core.logging import get_logger

from asunset_api.config import Settings
from asunset_api.routers.deps import DECLARED_FEATURE_GATES

log = get_logger("features.boot")


class FeatureGateMismatch(RuntimeError):
    """A require_feature() key is absent from the manifest — fail loud."""


def validate_declared_gates(manifest: FeatureManifest | None) -> None:
    """Every require_feature key must exist in the manifest (feat-ops 1).

    No manifest configured but gates declared → warn (every gate 403s;
    legal for a consumer that disabled features wholesale, but worth a
    line in the log). Manifest present + unknown key → raise.
    """
    if not DECLARED_FEATURE_GATES:
        return
    if manifest is None:
        log.warning(
            "features.gates_without_manifest",
            gates=sorted(DECLARED_FEATURE_GATES),
            detail="require_feature gates declared but no manifest configured — every gate will 403",
        )
        return
    unknown = DECLARED_FEATURE_GATES - manifest.keys
    if unknown:
        raise FeatureGateMismatch(
            f"require_feature keys not in the manifest: {sorted(unknown)} — "
            f"fix the key or add the feature to features.yaml"
        )


def _load(settings: Settings) -> FeatureManifest | None:
    path = settings.features_manifest
    if not path:
        return None
    if not Path(path).exists():
        log.warning("features.manifest_missing", path=path)
        return None
    return load_manifest(path)  # ManifestError propagates to callers


async def _org_id():  # noqa: ANN202 — UUID | None
    # Admin session: RLS-free read of the single org row (same reasoning
    # as the doctor check — the app role sees nothing without org ctx).
    factory = get_admin_session_factory()
    async with factory() as session:
        result = await session.execute(select(Organization.id).limit(1))
        row = result.first()
    return row[0] if row else None


async def run_feature_reconcile(
    authorizer: Authorizer, settings: Settings, *, prune: bool = False, dry_run: bool = False
) -> FeatureReconcileReport | None:
    """Load manifest + resolve org + reconcile. Raises ManifestError /
    RuntimeError for callers that want loud failures (the admin
    endpoint); returns None when there is nothing to do (no manifest) or
    no org yet."""
    manifest = _load(settings)
    validate_declared_gates(manifest)
    if manifest is None:
        return None

    org_id = await _org_id()
    if org_id is None:
        log.info(
            "features.reconcile_deferred",
            detail="no org yet — will run after POST /platform/bootstrap",
        )
        return None

    # Bookkeeping index (v1.1): every feature key that ever carried a
    # runtime grant — closes the orphan hole for keys removed from the
    # manifest (admin/RLS-free read, same rationale as the org lookup).
    from asunset_core.db.models import FeatureGrant

    factory = get_admin_session_factory()
    async with factory() as session:
        result = await session.execute(select(FeatureGrant.feature_key).distinct())
        known = {row[0] for row in result.all()}

    return await reconcile_features(
        authorizer, manifest, org_id, prune=prune, dry_run=dry_run, known_extra_keys=known
    )


async def reconcile_features_startup(authorizer: Authorizer, settings: Settings) -> None:
    """Best-effort startup wrapper: manifest problems are logged, not
    fatal — EXCEPT a declared-gate mismatch, which is a config bug that
    would 403 an endpoint forever and must stop the boot."""
    try:
        report = await run_feature_reconcile(authorizer, settings)
    except FeatureGateMismatch:
        raise
    except ManifestError as e:
        log.error("features.manifest_invalid", error=str(e))
        return
    except Exception as e:  # noqa: BLE001 — startup must not die on FGA hiccups
        log.error("features.boot_reconcile_failed", error=str(e))
        return
    if report is not None:
        log.info(
            "features.boot_reconcile",
            added=len(report.added),
            orphans=len(report.orphans),
            disabled=len(report.disabled),
        )
