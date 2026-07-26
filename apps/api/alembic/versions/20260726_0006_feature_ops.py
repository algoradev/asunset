"""feature_grant / role_assignment / feature_freeze — the v1.1 surface.

Tenant tables (org RLS). App-role grants: SELECT, INSERT, UPDATE — no
DELETE: revocation/unfreeze are UPDATEs (revoked_at/unfrozen_at), rows
are provenance history the app role cannot erase.
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None

APP_USER = os.environ.get("APP_DB_USER", "asunset")

TABLES = ("feature_grant", "role_assignment", "feature_freeze")


def upgrade() -> None:
    op.create_table(
        "feature_grant",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(255), nullable=False),
        sa.Column("grantee_type", sa.String(10), nullable=False),
        sa.Column("grantee_id", UUID(as_uuid=True), nullable=False),
        sa.Column("granted_by", UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_feature_grant_key", "feature_grant", ["feature_key"])

    op.create_table(
        "role_assignment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_name", sa.String(64), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by", UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_role_assignment_role", "role_assignment", ["role_name"])

    op.create_table(
        "feature_freeze",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("frozen_by", UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("unfrozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unfrozen_by", UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_feature_freeze_key", "feature_freeze", ["feature_key"])

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
              USING (org_id::text = current_setting('app.current_org_id', true))
              WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE {table} TO {APP_USER}")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.drop_table(table)
