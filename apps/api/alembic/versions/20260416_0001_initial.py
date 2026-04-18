"""initial schema + RLS policies

Revision ID: 0001
Revises:
Create Date: 2026-04-16
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None

# The app role reads APP_DB_USER from env so migrations can grant it access
# at the end. If this value drifts from the init script, RLS still protects
# tables — the grant call just needs the name to match.
APP_USER = os.environ.get("APP_DB_USER", "asunset")


# Tables that enforce tenant isolation via RLS. Notes: `app_user` is
# intentionally NOT in this list — users are a global (per-realm) dimension
# and per-user privacy is handled at the app layer, not RLS.
TENANT_TABLES = ("organization", "team", "org_member", "team_member", "note", "audit_event")


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # Create the enum once explicitly; every column reference below uses
    # create_type=False so the type isn't re-emitted with each table.
    member_role = postgresql.ENUM("admin", "member", name="member_role", create_type=False)
    op.execute("CREATE TYPE member_role AS ENUM ('admin', 'member')")

    op.create_table(
        "organization",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "team",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "name", name="uq_team_org_name"),
    )

    op.create_table(
        "app_user",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "org_member",
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", postgresql.ENUM("admin", "member", name="member_role", create_type=False), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "team_member",
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("team.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", postgresql.ENUM("admin", "member", name="member_role", create_type=False), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "note",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_note_org_team", "note", ["org_id", "team_id"])
    op.create_index("ix_note_owner", "note", ["owner_id"])

    op.create_table(
        "audit_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organization.id", ondelete="SET NULL"), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_audit_timestamp", "audit_event", ["timestamp"])
    op.create_index("ix_audit_trace_id", "audit_event", ["trace_id"])
    op.create_index("ix_audit_event_type", "audit_event", ["event_type"])

    # --- Row-level security ---
    #
    # One policy per tenant-scoped table: rows are visible only when the
    # session's `app.current_org_id` matches the row's org_id. OpenFGA
    # remains the authoritative authorization check — this is defense in
    # depth to contain the blast radius of any app-layer bypass.
    #
    # The session var is set per transaction in db/session.py.

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    # NOT using FORCE ROW LEVEL SECURITY: the schema-owner role bypasses
    # RLS as expected for admin ops (bootstrap, reconcile), while the
    # non-owner app role is fully subject to policies for normal requests.
    # Setting FORCE would require a BYPASSRLS privilege path, which is
    # harder to reason about than the owner-bypass split.

    # `organization` keys off its own id; membership tables key off org_id;
    # `team` / `note` / `audit_event` likewise.
    op.execute("""
        CREATE POLICY org_isolation ON organization
          USING (id::text = current_setting('app.current_org_id', true))
          WITH CHECK (id::text = current_setting('app.current_org_id', true))
    """)
    for table in ("team", "note", "audit_event"):
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
              USING (org_id::text = current_setting('app.current_org_id', true))
              WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
        """)

    # org_member needs a self-OR-tenant policy so an authenticated user can
    # always read their own membership rows even when the session's
    # current_org_id isn't set yet (bootstrap path: resolve which org I
    # belong to before I know which org I'm in).
    op.execute("""
        CREATE POLICY self_or_tenant_isolation ON org_member
          USING (
            user_id::text = current_setting('app.current_user_id', true)
            OR org_id::text = current_setting('app.current_org_id', true)
          )
          WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
    """)

    # Grant the non-owner app role CRUD on every table. Default privileges
    # (set in the init script) already cover future tables, so operators
    # don't need to remember this for future migrations — but do this
    # explicitly here so a fresh install works without manual GRANTs.
    for table in (
        "organization", "team", "app_user",
        "org_member", "team_member", "note", "audit_event",
    ):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {APP_USER}")
    # team_member doesn't have org_id directly; key off its team's org.
    op.execute("""
        CREATE POLICY tenant_isolation ON team_member
          USING (EXISTS (
            SELECT 1 FROM team
            WHERE team.id = team_member.team_id
              AND team.org_id::text = current_setting('app.current_org_id', true)
          ))
          WITH CHECK (EXISTS (
            SELECT 1 FROM team
            WHERE team.id = team_member.team_id
              AND team.org_id::text = current_setting('app.current_org_id', true)
          ))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON team_member")
    op.execute("DROP POLICY IF EXISTS self_or_tenant_isolation ON org_member")
    for table in ("audit_event", "note", "team"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute("DROP POLICY IF EXISTS org_isolation ON organization")

    op.drop_index("ix_audit_event_type", table_name="audit_event")
    op.drop_index("ix_audit_trace_id", table_name="audit_event")
    op.drop_index("ix_audit_timestamp", table_name="audit_event")
    op.drop_table("audit_event")

    op.drop_index("ix_note_owner", table_name="note")
    op.drop_index("ix_note_org_team", table_name="note")
    op.drop_table("note")

    op.drop_table("team_member")
    op.drop_table("org_member")
    op.drop_table("app_user")
    op.drop_table("team")
    op.drop_table("organization")

    postgresql.ENUM(name="member_role").drop(op.get_bind(), checkfirst=True)
