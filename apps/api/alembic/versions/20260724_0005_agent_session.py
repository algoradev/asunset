"""agent_session — the D4 mint's session/revocation state.

Tenant table with RLS. Policy is org_member-style self-OR-tenant: the
authorizer dependency must load the row by sid with only
app.current_user_id set (before org context exists), and the self arm
(user_id match) is what makes that possible without widening tenancy.

App-role grants: SELECT, INSERT, UPDATE — no DELETE. Revocation is
`revoked_at` (an UPDATE); rows are audit-relevant history and the app
role cannot erase them.
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None

APP_USER = os.environ.get("APP_DB_USER", "asunset")


def upgrade() -> None:
    op.create_table(
        "agent_session",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("audiences", JSONB, nullable=False),
        sa.Column("grants", JSONB, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_session_user", "agent_session", ["user_id"])

    op.execute("ALTER TABLE agent_session ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY self_or_tenant_isolation ON agent_session
          USING (
            user_id::text = current_setting('app.current_user_id', true)
            OR org_id::text = current_setting('app.current_org_id', true)
          )
          WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE agent_session TO {APP_USER}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS self_or_tenant_isolation ON agent_session")
    op.drop_index("ix_agent_session_user", table_name="agent_session")
    op.drop_table("agent_session")
