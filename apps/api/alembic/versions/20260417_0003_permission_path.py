"""audit: permission_path — how the grant resolved (direct/team/org)

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_event",
        sa.Column("permission_path", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_event", "permission_path")
