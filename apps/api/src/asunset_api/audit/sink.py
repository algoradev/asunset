"""Audit sink — writes events to both the DB and stdout.

Every emit() call:
  1. Passes payload + resource_label through the Redactor port.
  2. Inserts an enriched row into `audit_event` (identity snapshot,
     permission, labels) for the in-app viewer (short retention).
  3. Emits the same structured record to stdout for Vector to forward
     to the SIEM (long-retention source of truth).

Identity is snapshotted at AuditSink construction — once per request —
so the resulting rows are immune to user deletion / role changes that
happen after the fact.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from asunset_api.audit.events import EventType
from asunset_api.audit.redactor import get_redactor
from asunset_api.db.models import AuditEvent, MemberRole
from asunset_api.logging import get_logger

log = get_logger("audit")


class AuditSink:
    def __init__(
        self,
        session: AsyncSession,
        *,
        org_id: UUID | None,
        actor_id: UUID | None,
        trace_id: str | None,
        actor_email: str | None = None,
        actor_display_name: str | None = None,
        actor_org_role: MemberRole | None = None,
        actor_realm_roles: list[str] | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._session = session
        self._org_id = org_id
        self._actor_id = actor_id
        self._actor_email = actor_email
        self._actor_display_name = actor_display_name
        self._actor_org_role = actor_org_role.value if actor_org_role else None
        self._actor_realm_roles = sorted(actor_realm_roles or [])
        self._trace_id = trace_id
        self._source_ip = source_ip
        self._user_agent = (user_agent or "")[:500] or None
        self._session_id = session_id

    async def emit(
        self,
        event_type: EventType,
        *,
        action: str,
        resource_type: str | None = None,
        resource_id: str | UUID | None = None,
        resource_label: str | None = None,
        permission: str | None = None,
        permission_path: str | None = None,
        success: bool = True,
        payload: dict[str, Any] | None = None,
    ) -> None:
        redactor = get_redactor()
        safe_payload = redactor.redact_payload(event_type.value, payload or {})
        safe_label = redactor.redact_resource_label(resource_type, resource_label)

        row = AuditEvent(
            org_id=self._org_id,
            actor_id=self._actor_id,
            actor_email=self._actor_email,
            actor_display_name=self._actor_display_name,
            actor_org_role=self._actor_org_role,
            actor_realm_roles=self._actor_realm_roles,
            trace_id=self._trace_id,
            source_ip=self._source_ip,
            user_agent=self._user_agent,
            session_id=self._session_id,
            event_type=event_type.value,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            resource_label=safe_label,
            action=action,
            permission=permission,
            permission_path=permission_path,
            success=success,
            payload=safe_payload,
        )
        self._session.add(row)
        await self._session.flush([row])

        log.info(
            "audit",
            audit=True,
            event_type=event_type.value,
            action=action,
            permission=permission,
            permission_path=permission_path,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            resource_label=safe_label,
            success=success,
            org_id=str(self._org_id) if self._org_id else None,
            actor_id=str(self._actor_id) if self._actor_id else None,
            actor_email=self._actor_email,
            actor_display_name=self._actor_display_name,
            actor_org_role=self._actor_org_role,
            actor_realm_roles=self._actor_realm_roles,
            source_ip=self._source_ip,
            user_agent=self._user_agent,
            session_id=self._session_id,
            payload=safe_payload,
        )
