from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReportOut(_ORMBase):
    id: UUID
    title: str
    description: str
    spec: dict
    owner_id: UUID
    team_id: UUID | None
    created_at: datetime
    updated_at: datetime
    # Populated per-request by the router, same pattern as asunset's NoteOut.
    access_path: str | None = None


class ReportCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    spec: dict = Field(default_factory=dict)
    team_id: UUID | None = None
