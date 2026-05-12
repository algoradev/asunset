"""Notifier port.

A `Notifier` knows how to deliver an `EmailMessage`. That's it. No
templating, no locale resolution, no retry — those are caller
concerns. Keeping the contract this thin means a SendGrid / SES /
plain-SMTP adapter is straightforward to add later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    """Provider-agnostic email shape. Maps cleanly to Resend, SendGrid,
    SES, plain SMTP. Either `html` or `text` (or both) must be set —
    enforced in the Notifier adapters, not here, so a partial message
    can still flow through tests and be inspected.
    """

    to: tuple[str, ...]
    subject: str
    sender: str
    html: str | None = None
    text: str | None = None
    reply_to: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class Notifier(Protocol):
    """Delivery transport. Async because every modern provider is."""

    async def send(self, message: EmailMessage) -> None: ...
