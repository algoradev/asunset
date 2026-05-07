"""Product audit event types.

Define your product's events here as a `StrEnum` (or `(str, enum.Enum)`).
`AuditSink.emit()` accepts any value with a `.value: str` — the platform's
own `asunset_core.audit.events.EventType` and a per-product enum like the
one below both satisfy that contract.

Don't add to `asunset_core.audit.events.EventType` — that enum is owned
by the platform and reserved for cross-product events (notes, org/team
membership, FGA reconcile, access denied). Per-product events live here.

Naming: `<resource>.<verb_past_tense>`, lowercase, terse, machine-readable.
"""

from __future__ import annotations

import enum


class ProductEventType(str, enum.Enum):
    REPORT_CREATED = "report.created"
    REPORT_VIEWED = "report.viewed"
