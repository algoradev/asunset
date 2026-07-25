"""Startup/bootstrap hook: reconcile features.yaml into FGA tuples.

Grants reference the instance's single org (`organization:<id>#member`),
so reconciliation needs the org row. Pre-bootstrap there isn't one —
the hook logs and skips, and POST /platform/bootstrap calls it again
right after creating the org. Failures never block startup: a missing
or invalid manifest is an operator-visible log line, not an outage
(deployments without feature gates must keep working).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from asunset_core.auth.authorizer import Authorizer
from asunset_core.db.models import Organization
from asunset_core.db.session import get_admin_session_factory
from asunset_core.features import ManifestError, load_manifest, reconcile_features
from asunset_core.logging import get_logger

from asunset_api.config import Settings

log = get_logger("features.boot")


async def reconcile_features_startup(authorizer: Authorizer, settings: Settings) -> None:
    path = settings.features_manifest
    if not path:
        return
    if not Path(path).exists():
        log.warning("features.manifest_missing", path=path)
        return

    try:
        manifest = load_manifest(path)
    except ManifestError as e:
        log.error("features.manifest_invalid", path=path, error=str(e))
        return

    # Admin session: RLS-free read of the single org row (same reasoning
    # as the doctor check — the app role sees nothing without org ctx).
    factory = get_admin_session_factory()
    async with factory() as session:
        result = await session.execute(select(Organization.id).limit(2))
        org_ids = [row[0] for row in result.all()]

    if not org_ids:
        log.info(
            "features.reconcile_deferred",
            detail="no org yet — will run after POST /platform/bootstrap",
        )
        return

    report = await reconcile_features(authorizer, manifest, org_ids[0])
    log.info(
        "features.boot_reconcile",
        added=len(report.added),
        orphans=len(report.orphans),
    )
