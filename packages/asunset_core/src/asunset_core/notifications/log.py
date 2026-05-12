"""LogNotifier — default backend for local dev and tests.

Emits a structured log line per send instead of touching the network.
That keeps `docker compose up` working on a flight, and gives tests a
trivial way to assert "the app *would have* sent this email" via the
captured log records.

Don't ship this as the prod backend — silent log-only delivery in
production would be a HIPAA-flavored incident.
"""

from __future__ import annotations

from asunset_core.logging import get_logger
from asunset_core.notifications.port import EmailMessage

log = get_logger("notifier")


class LogNotifier:
    async def send(self, message: EmailMessage) -> None:
        log.info(
            "notifier.email_sent",
            notifier="log",
            to=list(message.to),
            sender=message.sender,
            subject=message.subject,
            has_html=message.html is not None,
            has_text=message.text is not None,
            reply_to=message.reply_to,
            headers=message.headers or None,
        )
