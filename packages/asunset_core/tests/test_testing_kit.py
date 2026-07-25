"""The testing kit must itself be trustworthy — StaticAuthorizer's
decision semantics mirror the patterns real code relies on."""

from __future__ import annotations

import pytest

from asunset_core.auth.authorizer import Tuple
from asunset_core.testing import StaticAuthorizer, allow_feature_for_org, grant_feature


async def test_deny_by_default_and_exact_allow() -> None:
    a = StaticAuthorizer()
    assert not await a.check("user:u", "can_view", "note:1")
    a.allow("user:u", "can_view", "note:1")
    assert await a.check("user:u", "can_view", "note:1")
    assert not await a.check("user:u", "can_edit", "note:1")
    assert not await a.check("user:other", "can_view", "note:1")


async def test_wildcard_patterns_match_session_grant_shapes() -> None:
    a = StaticAuthorizer()
    a.allow("user:u", "can_view", "note:*")
    a.allow("user:u", "*", "report:7")
    assert await a.check("user:u", "can_view", "note:42")
    assert not await a.check("user:u", "can_view", "report:42")
    assert await a.check("user:u", "can_delete", "report:7")


async def test_list_objects_excludes_wildcards() -> None:
    a = StaticAuthorizer()
    a.allow("user:u", "can_view", "note:1").allow("user:u", "can_view", "note:2")
    a.allow("user:u", "can_view", "report:*")
    assert await a.list_objects("user:u", "can_view", "note") == ["note:1", "note:2"]
    assert await a.list_objects("user:u", "can_view", "report") == []


async def test_write_records_and_mutates_allow_set() -> None:
    a = StaticAuthorizer()
    t = Tuple(user="user:u", relation="viewer", object="note:1")
    await a.write(writes=[t])
    assert a.writes == [t]
    assert await a.check("user:u", "viewer", "note:1")
    await a.write(deletes=[t])
    assert not await a.check("user:u", "viewer", "note:1")


async def test_fail_writes_exercises_rollback_ordering() -> None:
    a = StaticAuthorizer(fail_writes=True)
    with pytest.raises(RuntimeError):
        await a.write(writes=[Tuple(user="u", relation="r", object="o:1")])


def test_feature_helpers() -> None:
    a = StaticAuthorizer()
    grant_feature(a, "user:u", "reports.export")
    allow_feature_for_org(a, "org-1", "audit.view")
    assert ("user:u", "can_use", "feature:reports.export") in a.allowed
    assert ("organization:org-1#member", "can_use", "feature:audit.view") in a.allowed


async def test_read_tuples_type_prefix_filter() -> None:
    a = StaticAuthorizer()
    grant_feature(a, "user:u", "a.b")
    a.allow("user:u", "can_view", "note:1")
    feats = await a.read_tuples(object="feature:")
    assert [t.object for t in feats] == ["feature:a.b"]
