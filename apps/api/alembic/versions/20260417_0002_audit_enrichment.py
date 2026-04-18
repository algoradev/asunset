"""audit enrichment — snapshot actor identity + resource label + permission

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-17

Adds denormalized identity/permission columns to audit_event so events
remain informative after users are deleted and so auditors can answer
"who did what, when, with what permission" without replaying membership
history.

All columns are nullable — pre-existing rows retain their current shape.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_event",
        sa.Column("actor_email", sa.String(320), nullable=True),
    )
    op.add_column(
        "audit_event",
        sa.Column("actor_display_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "audit_event",
        sa.Column("actor_org_role", sa.String(20), nullable=True),
    )
    op.add_column(
        "audit_event",
        sa.Column(
            "actor_realm_roles",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "audit_event",
        sa.Column("resource_label", sa.String(500), nullable=True),
    )
    op.add_column(
        "audit_event",
        sa.Column("permission", sa.String(64), nullable=True),
    )

    op.create_index("ix_audit_actor_email", "audit_event", ["actor_email"])


def downgrade() -> None:
    op.drop_index("ix_audit_actor_email", table_name="audit_event")
    op.drop_column("audit_event", "permission")
    op.drop_column("audit_event", "resource_label")
    op.drop_column("audit_event", "actor_realm_roles")
    op.drop_column("audit_event", "actor_org_role")
    op.drop_column("audit_event", "actor_display_name")
    op.drop_column("audit_event", "actor_email")
