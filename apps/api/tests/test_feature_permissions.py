"""Feature-registration suite — reconcile + enforcement against real OpenFGA.

Uses the same fga_server fixture as the semantics suite; the demo model
now includes FEATURE_PLATFORM_TYPES, so this also proves the composed
model bootstraps. Personas reuse the platform usersets seeded by
test_fga_semantics where convenient, but this file seeds its own org to
stay independent of that module's tuples.
"""

from __future__ import annotations

from typing import AsyncIterator
from uuid import uuid4

import pytest_asyncio

from asunset_core.auth.authorizer import OpenFGAAuthorizer, Tuple, make_openfga_client
from asunset_core.features import parse_manifest, reconcile_features

from .conftest import FgaServer

ORG_ID = uuid4()
ORG = f"organization:{ORG_ID}"
MEMBER = "user:feat-member"
ADMIN = "user:feat-admin"
REVIEWER = "user:feat-reviewer"
OUTSIDER = "user:feat-outsider"

MANIFEST = parse_manifest(
    {
        "features": {
            "audit.view": {"grants": ["organization#member"]},
            "billing.manage": {"grants": ["organization#admin"]},
            "compliance.review": {"grants": ["role:compliance_reviewer#assignee"]},
        }
    }
)

_seeded = False


@pytest_asyncio.fixture
async def authz(fga_server: FgaServer) -> AsyncIterator[OpenFGAAuthorizer]:
    global _seeded
    client = make_openfga_client(
        fga_server.settings(), fga_server.store_id, fga_server.model_id
    )
    a = OpenFGAAuthorizer(client, fga_server.store_id, fga_server.model_id)
    if not _seeded:
        await a.write(
            writes=[
                Tuple(user=MEMBER, relation="member", object=ORG),
                Tuple(user=ADMIN, relation="member", object=ORG),
                Tuple(user=ADMIN, relation="admin", object=ORG),
                Tuple(user=REVIEWER, relation="assignee", object="role:compliance_reviewer"),
            ]
        )
        _seeded = True
    try:
        yield a
    finally:
        await client.close()


async def test_reconcile_grants_and_enforcement(authz: OpenFGAAuthorizer) -> None:
    report = await reconcile_features(authz, MANIFEST, ORG_ID)
    assert len(report.added) == 3 and not report.orphans

    # org member: has member-granted feature, not the admin one
    assert await authz.check(MEMBER, "can_use", "feature:audit.view")
    assert not await authz.check(MEMBER, "can_use", "feature:billing.manage")
    # org admin: has the admin feature; admin is ALSO a member here → both
    assert await authz.check(ADMIN, "can_use", "feature:billing.manage")
    assert await authz.check(ADMIN, "can_use", "feature:audit.view")
    # role assignee path
    assert await authz.check(REVIEWER, "can_use", "feature:compliance.review")
    assert not await authz.check(REVIEWER, "can_use", "feature:audit.view")
    # outsider: nothing
    for key in ("audit.view", "billing.manage", "compliance.review"):
        assert not await authz.check(OUTSIDER, "can_use", f"feature:{key}")


async def test_reconcile_is_idempotent(authz: OpenFGAAuthorizer) -> None:
    report = await reconcile_features(authz, MANIFEST, ORG_ID)
    assert report.added == [] and report.orphans == [] and report.pruned == []


async def test_list_objects_backs_me_features(authz: OpenFGAAuthorizer) -> None:
    feats = await authz.list_objects(MEMBER, "can_use", "feature")
    assert "feature:audit.view" in feats
    assert "feature:billing.manage" not in feats


async def test_orphan_flagged_then_pruned_and_runtime_grants_untouched(
    authz: OpenFGAAuthorizer,
) -> None:
    # Order-independent: establish the full manifest state first.
    await reconcile_features(authz, MANIFEST, ORG_ID)
    # A direct user grant (runtime data) that reconcile must never own.
    await authz.write(
        writes=[Tuple(user=OUTSIDER, relation="can_use", object="feature:audit.view")],
        tolerate_existing=True,
    )
    shrunk = parse_manifest(
        {"features": {"audit.view": {"grants": ["organization#member"]}}}
    )

    flagged = await reconcile_features(authz, shrunk, ORG_ID)
    # billing.manage's org#admin grant is discoverable (org-userset read)
    # → flagged, NOT removed. compliance.review's role grant sits on a
    # feature REMOVED from the manifest — the documented v1 limitation:
    # invisible to reconcile, so it neither flags nor prunes.
    assert flagged.orphans == [
        (f"organization:{ORG_ID}#admin", "can_use", "feature:billing.manage")
    ]
    assert flagged.pruned == []
    assert await authz.check(ADMIN, "can_use", "feature:billing.manage")

    pruned = await reconcile_features(authz, shrunk, ORG_ID, prune=True)
    assert len(pruned.pruned) == 1 and pruned.orphans == []
    assert not await authz.check(ADMIN, "can_use", "feature:billing.manage")
    # The limitation, pinned so it stays a documented fact not a surprise:
    # the removed-feature role grant survives prune.
    assert await authz.check(REVIEWER, "can_use", "feature:compliance.review")

    # The runtime user grant survived both passes — reconcile never owns it.
    assert await authz.check(OUTSIDER, "can_use", "feature:audit.view")

    # cleanup: manual deletes (exactly what an operator would do), then
    # restore the full-manifest state for any later assertions.
    await authz.write(
        deletes=[
            Tuple(user=OUTSIDER, relation="can_use", object="feature:audit.view"),
            Tuple(
                user="role:compliance_reviewer#assignee",
                relation="can_use",
                object="feature:compliance.review",
            ),
        ]
    )
    await reconcile_features(authz, MANIFEST, ORG_ID)


async def test_enabled_false_is_a_kill_switch(authz: OpenFGAAuthorizer) -> None:
    """enabled:false sweeps EVERY grant — defaults AND runtime user
    grants — without prune, and they stay gone until re-granted."""
    await reconcile_features(authz, MANIFEST, ORG_ID)
    await authz.write(
        writes=[Tuple(user=OUTSIDER, relation="can_use", object="feature:audit.view")],
        tolerate_existing=True,
    )
    assert await authz.check(MEMBER, "can_use", "feature:audit.view")

    killed = parse_manifest(
        {
            "features": {
                "audit.view": {"grants": ["organization#member"], "enabled": False},
                "billing.manage": {"grants": ["organization#admin"]},
                "compliance.review": {"grants": ["role:compliance_reviewer#assignee"]},
            }
        }
    )
    report = await reconcile_features(authz, killed, ORG_ID)
    # Both the default grant and the runtime user grant were swept; the
    # sweep is not double-reported as an orphan.
    assert len(report.disabled) == 2 and report.orphans == []
    assert not await authz.check(MEMBER, "can_use", "feature:audit.view")
    assert not await authz.check(OUTSIDER, "can_use", "feature:audit.view")
    # Other features untouched.
    assert await authz.check(ADMIN, "can_use", "feature:billing.manage")

    # Re-enable: default grant returns; the runtime grant does NOT
    # (documented — it was operator data and the operator killed it).
    report = await reconcile_features(authz, MANIFEST, ORG_ID)
    assert (
        f"organization:{ORG_ID}#member", "can_use", "feature:audit.view"
    ) in report.added
    assert await authz.check(MEMBER, "can_use", "feature:audit.view")
    assert not await authz.check(OUTSIDER, "can_use", "feature:audit.view")


async def test_kill_switch_is_idempotent(authz: OpenFGAAuthorizer) -> None:
    killed = parse_manifest(
        {"features": {"audit.view": {"grants": ["organization#member"], "enabled": False}}}
    )
    first = await reconcile_features(authz, killed, ORG_ID)
    second = await reconcile_features(authz, killed, ORG_ID)
    assert second.disabled == [] and second.added == []
    # restore
    await reconcile_features(authz, MANIFEST, ORG_ID)
