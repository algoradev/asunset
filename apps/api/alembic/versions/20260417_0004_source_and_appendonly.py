"""audit: source IP / UA / session id + append-only grants

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-17

Two changes bundled:

* Adds `source_ip`, `user_agent`, `session_id` to `audit_event` so the
  trail answers "from where / on what machine / in which SSO session"
  — critical forensic fields for detecting credential misuse inside a
  trusted network boundary (e.g. inside the org VPN).

* Revokes UPDATE / DELETE on `audit_event` from the non-owner app role.
  The app now has INSERT + SELECT only; the owner role (migrations,
  operator-run retention trims) retains full privileges. Defense in
  depth: even an SQL-injection-capable exploit in the API can't
  rewrite history.
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None

APP_USER = os.environ.get("APP_DB_USER", "asunset")


def upgrade() -> None:
    # INET stores both IPv4 and IPv6 natively + supports subnet queries.
    op.add_column(
        "audit_event",
        sa.Column("source_ip", postgresql.INET, nullable=True),
    )
    op.add_column(
        "audit_event",
        sa.Column("user_agent", sa.String(500), nullable=True),
    )
    op.add_column(
        "audit_event",
        sa.Column("session_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_audit_source_ip", "audit_event", ["source_ip"])
    op.create_index("ix_audit_session_id", "audit_event", ["session_id"])

    op.execute(f"REVOKE UPDATE, DELETE ON TABLE audit_event FROM {APP_USER}")


def downgrade() -> None:
    op.execute(
        f"GRANT UPDATE, DELETE ON TABLE audit_event TO {APP_USER}"
    )
    op.drop_index("ix_audit_session_id", table_name="audit_event")
    op.drop_index("ix_audit_source_ip", table_name="audit_event")
    op.drop_column("audit_event", "session_id")
    op.drop_column("audit_event", "user_agent")
    op.drop_column("audit_event", "source_ip")
