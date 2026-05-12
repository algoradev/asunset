"""Notifier + EmailService factories driven by CoreSettings.

The `NOTIFIER` env var picks a backend; everything else (sender, locale,
template overrides) flows from CoreSettings fields. Keeping the
selection here means routes inject `EmailService` directly and don't
care which provider is wired underneath.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from asunset_core.config import CoreSettings
from asunset_core.notifications.log import LogNotifier
from asunset_core.notifications.port import Notifier
from asunset_core.notifications.renderer import EmailTemplate
from asunset_core.notifications.resend import ResendNotifier
from asunset_core.notifications.service import EmailService

Backend = Literal["log", "resend"]


def make_notifier(settings: CoreSettings) -> Notifier:
    backend = settings.notifier_backend.lower()
    if backend == "resend":
        if not settings.resend_api_key:
            raise ValueError(
                "NOTIFIER=resend but RESEND_API_KEY is empty. Set the key "
                "or switch NOTIFIER=log for local dev."
            )
        return ResendNotifier(api_key=settings.resend_api_key)
    if backend == "log":
        return LogNotifier()
    raise ValueError(
        f"Unknown NOTIFIER backend: {settings.notifier_backend!r}. "
        "Expected 'log' or 'resend'."
    )


def make_email_service(settings: CoreSettings) -> EmailService:
    extra_dirs: list[Path] = []
    if settings.notifier_template_dir:
        extra_dirs.append(Path(settings.notifier_template_dir))
    return EmailService(
        notifier=make_notifier(settings),
        template=EmailTemplate(
            extra_dirs=extra_dirs,
            default_locale=settings.notifier_default_locale,
        ),
        default_sender=settings.notifier_default_sender,
        default_locale=settings.notifier_default_locale,
    )
