"""EmailService — the convenience layer call sites actually use.

Wraps a Notifier + an EmailTemplate so a route can write
`await email.send(template="welcome", locale=user.locale, to=...)`
without juggling rendering and delivery separately. Renderer concerns
(subject extraction, locale fallback, HTML autoescape) and transport
concerns (provider auth, HTTP status handling) stay isolated in their
own modules; this is just the glue.
"""

from __future__ import annotations

from asunset_core.notifications.port import EmailMessage, Notifier
from asunset_core.notifications.renderer import EmailTemplate


class EmailService:
    def __init__(
        self,
        *,
        notifier: Notifier,
        template: EmailTemplate,
        default_sender: str,
        default_locale: str = "en",
    ) -> None:
        if not default_sender:
            raise ValueError("EmailService requires a default_sender")
        self._notifier = notifier
        self._template = template
        self._default_sender = default_sender
        self._default_locale = default_locale

    async def send(
        self,
        *,
        template: str,
        to: str | list[str],
        context: dict | None = None,
        locale: str | None = None,
        sender: str | None = None,
        reply_to: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        rendered = self._template.render(
            template,
            locale=locale or self._default_locale,
            context=context,
        )
        recipients = (to,) if isinstance(to, str) else tuple(to)
        message = EmailMessage(
            to=recipients,
            subject=rendered.subject,
            sender=sender or self._default_sender,
            html=rendered.html,
            text=rendered.text,
            reply_to=reply_to,
            headers=headers or {},
        )
        await self._notifier.send(message)
