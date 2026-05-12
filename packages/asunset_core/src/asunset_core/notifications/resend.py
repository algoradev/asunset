"""ResendNotifier — production adapter.

Posts to Resend's HTTP API (https://resend.com/docs/api-reference/emails/send-email).
Raw httpx, no SDK — `httpx` is already in asunset_core's deps and the
Resend payload shape is small enough that the SDK is overhead.

Failure mode: a non-2xx response raises `ResendError`. Callers decide
whether to retry; the notifier itself doesn't. Network failures
propagate as the usual httpx exceptions.
"""

from __future__ import annotations

from typing import Any

import httpx

from asunset_core.logging import get_logger
from asunset_core.notifications.port import EmailMessage

log = get_logger("notifier")

RESEND_API_URL = "https://api.resend.com/emails"


class ResendError(RuntimeError):
    """Raised when Resend returns a non-2xx response."""


class ResendNotifier:
    def __init__(
        self,
        *,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not api_key:
            raise ValueError("ResendNotifier requires a non-empty api_key")
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def send(self, message: EmailMessage) -> None:
        if message.html is None and message.text is None:
            raise ValueError("EmailMessage needs at least html or text")

        payload: dict[str, Any] = {
            "from": message.sender,
            "to": list(message.to),
            "subject": message.subject,
        }
        if message.html is not None:
            payload["html"] = message.html
        if message.text is not None:
            payload["text"] = message.text
        if message.reply_to is not None:
            payload["reply_to"] = message.reply_to
        if message.headers:
            payload["headers"] = message.headers

        resp = await self._client.post(
            RESEND_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            log.error(
                "notifier.resend_error",
                status=resp.status_code,
                body=resp.text[:500],
                to=list(message.to),
                subject=message.subject,
            )
            raise ResendError(
                f"Resend returned {resp.status_code}: {resp.text[:200]}"
            )

        log.info(
            "notifier.email_sent",
            notifier="resend",
            to=list(message.to),
            sender=message.sender,
            subject=message.subject,
            resend_id=(resp.json() or {}).get("id") if resp.text else None,
        )
