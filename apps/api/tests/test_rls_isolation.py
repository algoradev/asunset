"""RLS tenant-isolation suite — the guarantee client-grade deployments rest on.

Adversarial by construction: every test connects as the APP role (the
non-owner role request handlers actually use) and runs RAW SQL — no ORM,
no asunset dependency chain — to prove the isolation holds at the
database layer even if every application-level guard were bypassed.

What is pinned here:
  1. RLS is enabled on every tenant table and the app role can't shed it.
  2. Cross-tenant reads return nothing — even with explicit predicates
     targeting the other org's rows by id.
  3. Cross-tenant writes are rejected (WITH CHECK) or hit zero rows.
  4. The org_member self-OR-tenant policy supports the pre-bootstrap
     path (user sees own memberships with only user ctx set) without
     leaking anyone else's.
  5. audit_event is append-only for the app role.
  6. Session context is transaction-local — it cannot leak across
     transactions on a pooled connection.
  7. Documented trust boundary: RLS trusts app.current_org_id; setting
     it from a *verified* principal is the application's job (deps.py).

Conventions: helpers wrap statements in an explicit transaction because
`set_config(..., is_local => true)` is transaction-scoped — exactly how
get_db() uses it in production.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
import pytest

from .conftest import APP_DB_USER, SeededDb

TENANT_TABLES = (
    "organization", "team", "org_member", "team_member", "note", "audit_event",
    "agent_session",  # added in migration 0005 (D4 mint)
)


async def _apply_ctx(conn: asyncpg.Connection, uid: UUID | None, oid: UUID | str | None) -> None:
    await conn.execute(
        "SELECT set_config('app.current_user_id', $1, true), "
        "set_config('app.current_org_id', $2, true)",
        str(uid) if uid else "",
        str(oid) if oid else "",
    )


async def fetch_as_app(
    db: SeededDb,
    sql: str,
    *args: object,
    uid: UUID | None = None,
    oid: UUID | str | None = None,
) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(db.app_dsn)
    try:
        async with conn.transaction():
            await _apply_ctx(conn, uid, oid)
            return await conn.fetch(sql, *args)
    finally:
        await conn.close()


async def exec_as_app(
    db: SeededDb,
    sql: str,
    *args: object,
    uid: UUID | None = None,
    oid: UUID | str | None = None,
) -> str:
    conn = await asyncpg.connect(db.app_dsn)
    try:
        async with conn.transaction():
            await _apply_ctx(conn, uid, oid)
            return await conn.execute(sql, *args)
    finally:
        await conn.close()


# --- 1. posture: RLS is on and the app role can't shed it -----------------


async def test_rls_enabled_on_every_tenant_table(rls_db: SeededDb) -> None:
    conn = await asyncpg.connect(rls_db.owner_dsn)
    try:
        rows = await conn.fetch(
            "SELECT relname, relrowsecurity FROM pg_class "
            "WHERE relname = ANY($1::text[])",
            list(TENANT_TABLES),
        )
    finally:
        await conn.close()
    by_name = {r["relname"]: r["relrowsecurity"] for r in rows}
    assert set(by_name) == set(TENANT_TABLES), "a tenant table is missing entirely"
    off = [t for t, on in by_name.items() if not on]
    assert not off, f"RLS not enabled on: {off}"


async def test_app_role_is_not_owner_and_cannot_bypass(rls_db: SeededDb) -> None:
    # Owner-bypass (not FORCE RLS) is the deliberate design — which makes
    # "the app role is not the owner / not superuser / not BYPASSRLS" a
    # load-bearing invariant, so pin all three.
    conn = await asyncpg.connect(rls_db.owner_dsn)
    try:
        owners = await conn.fetch(
            "SELECT tablename, tableowner FROM pg_tables WHERE tablename = ANY($1::text[])",
            list(TENANT_TABLES),
        )
        role = await conn.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = $1", APP_DB_USER
        )
    finally:
        await conn.close()
    owned_by_app = [r["tablename"] for r in owners if r["tableowner"] == APP_DB_USER]
    assert not owned_by_app, f"app role OWNS tenant tables (owner-bypass!): {owned_by_app}"
    assert role is not None and not role["rolsuper"] and not role["rolbypassrls"]


async def test_app_role_cannot_disable_rls_or_escalate(rls_db: SeededDb) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await exec_as_app(rls_db, "ALTER TABLE note DISABLE ROW LEVEL SECURITY")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await exec_as_app(rls_db, "SET ROLE asunset_owner")


# --- 2. cross-tenant reads ------------------------------------------------


async def test_sees_only_own_org_rows_per_table(rls_db: SeededDb) -> None:
    db = rls_db
    ctx = {"uid": db.user_a, "oid": db.org_a}

    orgs = await fetch_as_app(db, "SELECT id FROM organization", **ctx)
    assert [r["id"] for r in orgs] == [db.org_a]

    teams = await fetch_as_app(db, "SELECT id FROM team", **ctx)
    assert [r["id"] for r in teams] == [db.team_a]

    members = await fetch_as_app(db, "SELECT org_id FROM org_member", **ctx)
    assert {r["org_id"] for r in members} == {db.org_a}

    # team_member has no org_id — its policy joins through team.
    tms = await fetch_as_app(db, "SELECT team_id FROM team_member", **ctx)
    assert {r["team_id"] for r in tms} == {db.team_a}

    notes = await fetch_as_app(db, "SELECT id FROM note", **ctx)
    assert [r["id"] for r in notes] == [db.note_a]

    audits = await fetch_as_app(db, "SELECT id FROM audit_event", **ctx)
    assert [r["id"] for r in audits] == [db.audit_a]


async def test_raw_sql_targeting_other_org_returns_nothing(rls_db: SeededDb) -> None:
    """The headline case: app role, raw SQL, explicit predicate aimed
    straight at the other tenant's rows — including by primary key."""
    db = rls_db
    ctx = {"uid": db.user_a, "oid": db.org_a}

    by_org = await fetch_as_app(db, "SELECT * FROM note WHERE org_id = $1", db.org_b, **ctx)
    assert by_org == []

    by_pk = await fetch_as_app(db, "SELECT * FROM note WHERE id = $1", db.note_b, **ctx)
    assert by_pk == []

    other_org = await fetch_as_app(
        db, "SELECT * FROM organization WHERE id = $1", db.org_b, **ctx
    )
    assert other_org == []

    other_audit = await fetch_as_app(
        db, "SELECT * FROM audit_event WHERE id = $1", db.audit_b, **ctx
    )
    assert other_audit == []

    other_tm = await fetch_as_app(
        db, "SELECT * FROM team_member WHERE user_id = $1", db.user_b, **ctx
    )
    assert other_tm == []


async def test_empty_context_sees_nothing(rls_db: SeededDb) -> None:
    for table in TENANT_TABLES:
        rows = await fetch_as_app(rls_db, f"SELECT * FROM {table}")  # noqa: S608
        assert rows == [], f"{table} leaked {len(rows)} rows with no session context"


async def test_app_user_is_global_by_design(rls_db: SeededDb) -> None:
    # app_user is deliberately NOT a tenant table (the global identity
    # dimension; the OIDC upsert must work pre-org). Pin that too — if
    # someone adds RLS to it, login breaks in a way this names.
    rows = await fetch_as_app(rls_db, "SELECT id FROM app_user")
    assert {r["id"] for r in rows} == {rls_db.user_a, rls_db.user_b}


# --- 3. cross-tenant writes -----------------------------------------------


async def test_insert_into_other_org_rejected(rls_db: SeededDb) -> None:
    db = rls_db
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await exec_as_app(
            db,
            "INSERT INTO note (org_id, owner_id, title, body) "
            "VALUES ($1, $2, 'smuggled', '')",
            db.org_b, db.user_a,
            uid=db.user_a, oid=db.org_a,
        )


async def test_update_cannot_move_row_to_other_org(rls_db: SeededDb) -> None:
    db = rls_db
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await exec_as_app(
            db,
            "UPDATE note SET org_id = $1 WHERE id = $2",
            db.org_b, db.note_a,
            uid=db.user_a, oid=db.org_a,
        )


async def test_update_delete_of_other_org_rows_hit_nothing(rls_db: SeededDb) -> None:
    db = rls_db
    ctx = {"uid": db.user_a, "oid": db.org_a}

    status = await exec_as_app(
        db, "UPDATE note SET title = 'defaced' WHERE id = $1", db.note_b, **ctx
    )
    assert status == "UPDATE 0"

    status = await exec_as_app(db, "DELETE FROM note WHERE id = $1", db.note_b, **ctx)
    assert status == "DELETE 0"

    # Verify from org B's own view that nothing changed.
    row = await fetch_as_app(
        db, "SELECT title FROM note WHERE id = $1", db.note_b,
        uid=db.user_b, oid=db.org_b,
    )
    assert row and row[0]["title"] == "Note B"


# --- 4. the pre-bootstrap self-visibility path ----------------------------


async def test_org_member_self_visible_with_user_ctx_only(rls_db: SeededDb) -> None:
    """get_current_org() runs with ONLY app.current_user_id set (org set
    to '') and must see the caller's own memberships — and nobody else's."""
    db = rls_db
    rows = await fetch_as_app(
        db, "SELECT org_id, user_id FROM org_member", uid=db.user_a, oid=""
    )
    assert [(r["org_id"], r["user_id"]) for r in rows] == [(db.org_a, db.user_a)]

    others = await fetch_as_app(
        db, "SELECT * FROM org_member WHERE user_id = $1", db.user_b,
        uid=db.user_a, oid="",
    )
    assert others == []


# --- 5. audit append-only -------------------------------------------------


async def test_audit_event_is_append_only_for_app_role(rls_db: SeededDb) -> None:
    db = rls_db
    ctx = {"uid": db.user_a, "oid": db.org_a}

    await exec_as_app(
        db,
        "INSERT INTO audit_event (org_id, actor_id, actor_realm_roles, "
        "event_type, action, success, payload) "
        "VALUES ($1, $2, '[]', 'test.rls', 'insert_ok', true, '{}')",
        db.org_a, db.user_a,
        **ctx,
    )

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await exec_as_app(
            db, "UPDATE audit_event SET action = 'tampered' WHERE id = $1",
            db.audit_a, **ctx,
        )
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await exec_as_app(
            db, "DELETE FROM audit_event WHERE id = $1", db.audit_a, **ctx
        )


# --- 6. context is transaction-local --------------------------------------


async def test_context_does_not_leak_across_transactions(rls_db: SeededDb) -> None:
    """set_config(..., is_local => true) must die with its transaction —
    the property that makes pooled-connection reuse safe in get_db()."""
    db = rls_db
    conn = await asyncpg.connect(db.app_dsn)
    try:
        async with conn.transaction():
            await _apply_ctx(conn, db.user_a, db.org_a)
            visible = await conn.fetchval("SELECT count(*) FROM note")
            assert visible == 1

        # Same physical connection, new transaction, NO ctx applied:
        # a leaked setting would show org A's rows here.
        async with conn.transaction():
            leaked = await conn.fetchval("SELECT count(*) FROM note")
            assert leaked == 0
    finally:
        await conn.close()


# --- 7. the documented trust boundary -------------------------------------


async def test_context_is_the_trust_boundary(rls_db: SeededDb) -> None:
    """DOCUMENTATION, not a vulnerability: RLS trusts app.current_org_id.
    A connection that sets org B's id sees org B's rows. Deriving the
    setting from a *verified* principal is the application layer's job
    (routers/deps.py get_db) — RLS defends against forgotten WHERE
    clauses and app-layer bugs, not against the app lying about who it
    serves. If this test ever fails, the semantics changed and both the
    identity contract (§7.3) and deps.py need re-review."""
    db = rls_db
    rows = await fetch_as_app(
        db, "SELECT id FROM note", uid=db.user_a, oid=db.org_b
    )
    assert [r["id"] for r in rows] == [db.note_b]
