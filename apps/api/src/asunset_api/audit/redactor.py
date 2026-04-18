"""Pluggable PHI redaction for audit payloads + resource labels.

Every audit emission passes through a Redactor before hitting the DB
and stdout. The default is a no-op — the template trusts its own code
not to log PHI — but operators deploying against real patient data
must swap in a real implementation that knows their data shape.

The port lives here (not in sink.py) so operators only need to touch
one file when wiring their own redactor. The AuditSink consults
`get_redactor()` at emit time; override by monkey-patching, DI swap,
or editing this file.
"""

from __future__ import annotations

from typing import Any, Protocol


class Redactor(Protocol):
    def redact_payload(
        self, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]: ...

    def redact_resource_label(
        self, resource_type: str | None, label: str | None
    ) -> str | None: ...


class PassThroughRedactor:
    """Default: returns inputs unchanged.

    Safe for the demo because the Notes app only emits non-PHI fields
    (team_id, role, permission). When forking for real PHI workloads,
    replace this with an operator-provided implementation — do NOT
    add PHI-aware logic to the default.
    """

    def redact_payload(
        self, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return payload

    def redact_resource_label(
        self, resource_type: str | None, label: str | None
    ) -> str | None:
        return label


_redactor: Redactor = PassThroughRedactor()


def get_redactor() -> Redactor:
    return _redactor


def set_redactor(redactor: Redactor) -> None:
    """Wire in a production redactor — call once on app startup."""
    global _redactor
    _redactor = redactor
