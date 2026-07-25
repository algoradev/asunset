"""Reconcile the feature manifest into FGA tuples.

Posture (docs/feature-permissions-spec.md §5): add-missing with
`tolerate_existing`, FLAG orphans, prune only on explicit request —
the same fail-toward-orphan-tuples discipline as the dual-write model.

Scope: this owns ONLY manifest-declared userset grants
(`organization#member/admin`, `role:*#assignee`). Runtime grants —
direct `user:*` tuples, per-team grants — are never touched, in either
direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from asunset_core.auth.authorizer import Authorizer, Tuple
from asunset_core.features.manifest import FeatureManifest
from asunset_core.logging import get_logger

log = get_logger("features.reconcile")

_MANAGED_USER_PREFIXES = ("organization:", "role:")


def _is_managed(user: str) -> bool:
    """Manifest-managed grant shapes only — runtime user/team grants are
    invisible to reconcile by construction."""
    return user.startswith(_MANAGED_USER_PREFIXES) and "#" in user


@dataclass
class FeatureReconcileReport:
    added: list[tuple[str, str, str]] = field(default_factory=list)
    orphans: list[tuple[str, str, str]] = field(default_factory=list)
    pruned: list[tuple[str, str, str]] = field(default_factory=list)
    # Grants removed because their feature is explicitly `enabled: false`
    # — always removed (declared intent), unlike orphans (flag-first).
    disabled: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.orphans


async def reconcile_features(
    authorizer: Authorizer,
    manifest: FeatureManifest,
    org_id: UUID | str,
    *,
    prune: bool = False,
    dry_run: bool = False,
) -> FeatureReconcileReport:
    """dry_run computes the full report (would-add / orphans /
    would-sweep / would-prune) WITHOUT writing — the read-only drift
    assessment consumer doctors consume instead of reimplementing the
    manifest-vs-FGA diff (Kestrel's single-door rule: doctor verifies,
    only the audited endpoint mutates)."""
    desired = manifest.desired_tuples(org_id)

    # Current managed grants, discovered two ways (OpenFGA's Read API
    # forbids a type-only object filter with no user):
    #   1. Full-object reads per MANIFEST feature — sees every grant
    #      shape on surviving features, so stale role/org grants there
    #      are always caught.
    #   2. Org-userset reads across the feature type — finds org-granted
    #      tuples on features REMOVED from the manifest.
    # Known limitation (documented): a role-granted tuple on a fully
    # removed feature is invisible here — flag it manually if a feature
    # with role grants is ever deleted from the manifest.
    report = FeatureReconcileReport()

    # Explicitly disabled features (enabled: false) FIRST: remove EVERY
    # grant on them — defaults AND runtime user/team grants. This is the
    # declarative kill switch; the operator wrote the intent into the
    # manifest, so unlike orphans there is no flag-first stage. Runs
    # before discovery so killed grants can't double-report as orphans.
    for key in sorted(manifest.disabled_keys):
        killed = await authorizer.read_tuples(object=f"feature:{key}")
        if not killed:
            continue
        if not dry_run:
            await authorizer.write(
                deletes=[Tuple(user=t.user, relation=t.relation, object=t.object) for t in killed]
            )
        for t in killed:
            report.disabled.append((t.user, t.relation, t.object))
            log.warning(
                "features.disabled_grant_removed",
                user=t.user, relation=t.relation, object=t.object,
                detail="feature is enabled:false in the manifest",
            )

    disabled_objects = {f"feature:{k}" for k in manifest.disabled_keys}
    current: set[tuple[str, str, str]] = set()
    for f in manifest.features:
        if not f.enabled:
            continue
        for t in await authorizer.read_tuples(object=f"feature:{f.key}"):
            current.add((t.user, t.relation, t.object))
    for userset in (f"organization:{org_id}#member", f"organization:{org_id}#admin"):
        for t in await authorizer.read_tuples(user=userset, object="feature:"):
            if t.object not in disabled_objects:
                current.add((t.user, t.relation, t.object))
    current_managed = {c for c in current if _is_managed(c[0])}

    missing = desired - current_managed
    if missing:
        if not dry_run:
            await authorizer.write(
                writes=[Tuple(user=u, relation=r, object=o) for (u, r, o) in sorted(missing)],
                tolerate_existing=True,
            )
        report.added = sorted(missing)
        for u, r, o in report.added:
            log.info("features.grant_added", user=u, relation=r, object=o)

    # Orphans: managed tuples the manifest no longer declares — a removed
    # feature OR a removed default grant on a surviving feature.
    orphans = current_managed - desired
    report.orphans = sorted(orphans)
    for u, r, o in report.orphans:
        log.warning(
            "features.orphan_grant",
            user=u, relation=r, object=o,
            detail="not in manifest — flag only; pass prune=True to remove",
        )

    if prune and orphans:
        if not dry_run:
            await authorizer.write(
                deletes=[Tuple(user=u, relation=r, object=o) for (u, r, o) in sorted(orphans)]
            )
        report.pruned = sorted(orphans)
        report.orphans = []
        for u, r, o in report.pruned:
            log.info("features.orphan_pruned", user=u, relation=r, object=o)

    log.info(
        "features.reconcile_done",
        declared=len(manifest.keys),
        added=len(report.added),
        orphans=len(report.orphans),
        pruned=len(report.pruned),
        disabled=len(report.disabled),
        dry_run=dry_run,
    )
    return report
