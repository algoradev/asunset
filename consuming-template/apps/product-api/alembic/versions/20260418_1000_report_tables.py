"""product: report table

Revision ID: 1000
Revises: 0004
Create Date: 2026-04-18

First product migration. `down_revision = "0004"` chains it after
asunset's last platform migration (source: vendor/asunset/apps/api/
alembic/versions/). Running `alembic upgrade head` materializes both
platform + product tables in order.

Bump `down_revision` when you pull a newer asunset that added migrations
beyond 0004.
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1000"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None

APP_USER = os.environ.get("APP_DB_USER", "asunset")


def upgrade() -> None:
    op.create_table(
        "report",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("spec", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_report_org_team", "report", ["org_id", "team_id"])
    op.create_index("ix_report_owner", "report", ["owner_id"])

    # RLS: every product table that's tenant-scoped gets the same
    # org-isolation pattern asunset uses for notes. The app role can
    # only see rows where org_id matches the current session's org.
    op.execute("ALTER TABLE report ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON report
          USING (org_id::text = current_setting('app.current_org_id', true))
          WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
    """)

    # Grant the non-owner app role CRUD. asunset_core's session uses
    # this role for request-handling; owner (asunset_owner) bypasses RLS.
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE report TO {APP_USER}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON report")
    op.drop_index("ix_report_owner", table_name="report")
    op.drop_index("ix_report_org_team", table_name="report")
    op.drop_table("report")
