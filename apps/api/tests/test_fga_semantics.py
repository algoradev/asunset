"""FGA semantics suite — the authorization decisions everything leans on.

Runs against a real ephemeral OpenFGA (see conftest.fga_server) with the
real platform+Notes model, through the real `OpenFGAAuthorizer` port —
not a mock of any layer. Verifies the model's derivation rules
(owner/editor/viewer, team usersets, "admin from team", org-wide share),
the port's list/explain/label semantics, and the dual-write retry
contract (`tolerate_existing`).

Personas (seeded once):
    owner_u    — owns every note
    editor_u   — direct editor on n1
    viewer_u   — direct viewer on n1
    team_m     — member of team T (granted editor on n2 via team#member)
    team_adm   — admin of team T (n1 carries team=T → "admin from team")
    org_m      — plain org member (n3 is org-shared)
    outsider   — no org membership, no grants: must see nothing

Notes:
    note:n1 — owner + team=T + direct editor_u + direct viewer_u
    note:n2 — owner + editor granted to team:T#member (userset)
    note:n3 — owner + viewer granted to organization:O#member (org share)
    note:priv — owner only
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest
import pytest_asyncio
from openfga_sdk.exceptions import ApiException

from asunset_core.auth.authorizer import OpenFGAAuthorizer, Tuple, make_openfga_client

from .conftest import FgaServer

ORG = "organization:org-1"
TEAM = "team:team-1"

OWNER = "user:owner-u"
EDITOR = "user:editor-u"
VIEWER = "user:viewer-u"
TEAM_M = "user:team-m"
TEAM_ADM = "user:team-adm"
ORG_M = "user:org-m"
OUTSIDER = "user:outsider"

N1, N2, N3, PRIV = "note:n1", "note:n2", "note:n3", "note:priv"

SEED_TUPLES = [
    # org membership (outsider deliberately absent)
    *[Tuple(user=u, relation="member", object=ORG)
      for u in (OWNER, EDITOR, VIEWER, TEAM_M, TEAM_ADM, ORG_M)],
    # team T in org O
    Tuple(user=ORG, relation="org", object=TEAM),
    Tuple(user=TEAM_M, relation="member", object=TEAM),
    Tuple(user=TEAM_ADM, relation="admin", object=TEAM),
    # n1: fully shared
    Tuple(user=OWNER, relation="owner", object=N1),
    Tuple(user=TEAM, relation="team", object=N1),
    Tuple(user=EDITOR, relation="editor", object=N1),
    Tuple(user=VIEWER, relation="viewer", object=N1),
    # n2: editor granted to the team's members as a userset
    Tuple(user=OWNER, relation="owner", object=N2),
    Tuple(user=f"{TEAM}#member", relation="editor", object=N2),
    # n3: org-wide share
    Tuple(user=OWNER, relation="owner", object=N3),
    Tuple(user=f"{ORG}#member", relation="viewer", object=N3),
    # priv: owner only
    Tuple(user=OWNER, relation="owner", object=PRIV),
]

_seeded = False


@pytest_asyncio.fixture
async def authz(fga_server: FgaServer) -> AsyncIterator[OpenFGAAuthorizer]:
    """Fresh client per test (SDK clients are loop-bound); seeds once."""
    global _seeded
    client = make_openfga_client(
        fga_server.settings(), fga_server.store_id, fga_server.model_id
    )
    a = OpenFGAAuthorizer(client, fga_server.store_id, fga_server.model_id)
    if not _seeded:
        await a.write(writes=SEED_TUPLES)
        _seeded = True
    try:
        yield a
    finally:
        await client.close()


# --- derivation rules ------------------------------------------------------


async def test_owner_has_full_rights_everywhere(authz: OpenFGAAuthorizer) -> None:
    for note in (N1, N2, N3, PRIV):
        assert await authz.check(OWNER, "can_edit", note)
        assert await authz.check(OWNER, "can_view", note)
        assert await authz.check(OWNER, "can_delete", note)


async def test_direct_editor_edits_but_never_deletes(authz: OpenFGAAuthorizer) -> None:
    assert await authz.check(EDITOR, "can_edit", N1)
    assert await authz.check(EDITOR, "can_view", N1)
    assert not await authz.check(EDITOR, "can_delete", N1)
    # …and the grant doesn't bleed onto other notes.
    assert not await authz.check(EDITOR, "can_view", N2)


async def test_direct_viewer_views_only(authz: OpenFGAAuthorizer) -> None:
    assert await authz.check(VIEWER, "can_view", N1)
    assert not await authz.check(VIEWER, "can_edit", N1)
    assert not await authz.check(VIEWER, "can_delete", N1)


async def test_team_userset_grant_reaches_members_only(authz: OpenFGAAuthorizer) -> None:
    # team:T#member editor on n2 → member edits…
    assert await authz.check(TEAM_M, "can_edit", N2)
    assert await authz.check(TEAM_M, "can_view", N2)
    # …but a team ADMIN is not a member: userset doesn't cover them.
    assert not await authz.check(TEAM_ADM, "can_edit", N2)
    # membership of the team grants nothing on n1 (whose team tuple
    # empowers only the team's ADMIN via "admin from team").
    assert not await authz.check(TEAM_M, "can_view", N1)


async def test_admin_from_team_on_attached_note(authz: OpenFGAAuthorizer) -> None:
    # n1 carries team=T → T's admin can edit AND delete via the tupleset.
    assert await authz.check(TEAM_ADM, "can_edit", N1)
    assert await authz.check(TEAM_ADM, "can_delete", N1)
    assert await authz.check(TEAM_ADM, "can_view", N1)


async def test_org_share_reaches_members_not_outsiders(authz: OpenFGAAuthorizer) -> None:
    assert await authz.check(ORG_M, "can_view", N3)
    assert not await authz.check(ORG_M, "can_edit", N3)
    assert not await authz.check(ORG_M, "can_view", N1)
    # outsider holds no org membership: the org-wide share must not reach them.
    assert not await authz.check(OUTSIDER, "can_view", N3)


async def test_outsider_sees_nothing_anywhere(authz: OpenFGAAuthorizer) -> None:
    for note in (N1, N2, N3, PRIV):
        for rel in ("can_view", "can_edit", "can_delete"):
            assert not await authz.check(OUTSIDER, rel, note), f"{rel} leaked on {note}"


# --- list_objects ----------------------------------------------------------


async def test_list_objects_matches_checks(authz: OpenFGAAuthorizer) -> None:
    assert set(await authz.list_objects(OWNER, "can_view", "note")) == {N1, N2, N3, PRIV}
    assert set(await authz.list_objects(ORG_M, "can_view", "note")) == {N3}
    # team_m is ALSO an org member, so the org-shared n3 shows up too —
    # list_objects composes every path, exactly like check does.
    assert set(await authz.list_objects(TEAM_M, "can_view", "note")) == {N2, N3}
    assert set(await authz.list_objects(EDITOR, "can_edit", "note")) == {N1}
    assert await authz.list_objects(OUTSIDER, "can_view", "note") == []


# --- explain / audit path labels ------------------------------------------


async def test_explain_classifies_direct_team_org(authz: OpenFGAAuthorizer) -> None:
    direct = await authz.explain(EDITOR, "can_edit", N1)
    assert direct is not None and direct.kind == "direct" and direct.via_relation == "editor"

    team = await authz.explain(TEAM_M, "can_edit", N2)
    assert team is not None and team.kind == "team" and team.via_object == TEAM

    org = await authz.explain(ORG_M, "can_view", N3)
    assert org is not None and org.kind == "organization" and org.via_object == ORG


async def test_explain_note_access_labels(authz: OpenFGAAuthorizer) -> None:
    assert await authz.explain_note_access(OWNER, N1) == "owner"
    assert await authz.explain_note_access(EDITOR, N1) == "direct_editor"
    assert await authz.explain_note_access(VIEWER, N1) == "direct_viewer"
    assert await authz.explain_note_access(TEAM_M, N2) == "team_editor"
    assert await authz.explain_note_access(ORG_M, N3) == "org_viewer"


# --- write semantics: the dual-write retry contract ------------------------


async def test_duplicate_write_raises_without_tolerate(authz: OpenFGAAuthorizer) -> None:
    dup = Tuple(user=OWNER, relation="owner", object=N1)
    with pytest.raises(ApiException):
        await authz.write(writes=[dup])


async def test_tolerate_existing_replays_partial_batch(authz: OpenFGAAuthorizer) -> None:
    """The invite-retry contract: a batch mixing an already-landed tuple
    with a new one must land the new tuple and swallow only the dup."""
    fresh = Tuple(user="user:retry-u", relation="viewer", object=N1)
    dup = Tuple(user=OWNER, relation="owner", object=N1)
    try:
        await authz.write(writes=[dup, fresh], tolerate_existing=True)
        assert await authz.check("user:retry-u", "can_view", N1)
    finally:
        await authz.write(deletes=[fresh])


async def test_delete_revokes_immediately(authz: OpenFGAAuthorizer) -> None:
    t = Tuple(user="user:transient", relation="viewer", object=PRIV)
    await authz.write(writes=[t])
    assert await authz.check("user:transient", "can_view", PRIV)
    await authz.write(deletes=[t])
    assert not await authz.check("user:transient", "can_view", PRIV)


async def test_read_tuples_paginates_object_grants(authz: OpenFGAAuthorizer) -> None:
    grants = await authz.read_tuples(object=N1)
    assert {(t.user, t.relation) for t in grants} == {
        (OWNER, "owner"), (TEAM, "team"), (EDITOR, "editor"), (VIEWER, "viewer"),
    }


# --- bootstrap idempotency -------------------------------------------------


async def test_bootstrap_is_idempotent_on_store(fga_server: FgaServer) -> None:
    """Second bootstrap must reuse the store (append a model, never fork
    a second store) — the property that makes every api restart safe."""
    from asunset_api.fga.model import AUTHORIZATION_MODEL
    from asunset_core.fga.bootstrap import bootstrap_openfga

    store_id2, model_id2 = await bootstrap_openfga(
        fga_server.settings(), AUTHORIZATION_MODEL
    )
    assert store_id2 == fga_server.store_id
    assert model_id2  # a pinned model id always comes back
