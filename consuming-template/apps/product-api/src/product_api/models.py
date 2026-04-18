"""Product models.

Inherits from `asunset_core.db.Base` so the Report table joins the same
metadata graph as Organization / Team / AppUser / AuditEvent. FKs to
those tables resolve at migration time.

Every product-side table that references the platform should FK onto
app_user / organization / team — that way RLS + audit stay coherent.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from asunset_core.db.models import Base


class Report(Base):
    """Example product resource.

    Swap this out for whatever your product actually tracks —
    analytics_dashboard, financial_statement, patient_case, etc.
    """

    __tablename__ = "report"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("team.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Product-specific: an analytics query spec, a dashboard config, etc.
    spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
