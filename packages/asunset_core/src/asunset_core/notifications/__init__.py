"""App-side email notifier.

Two layers:

  - `Notifier` is the transport port. `LogNotifier` (default in dev)
    logs every send to stdout; `ResendNotifier` posts to Resend's HTTP
    API for prod. Adding SendGrid/SES/SMTP is a new adapter, not a
    surgery on the call sites.

  - `EmailTemplate` resolves Jinja2 templates from a locale-aware
    directory. `EmailService` wires the two together: `await
    email.send(template="welcome", locale="es", to=..., context=...)`.

Keycloak's own emails (verify, reset password, magic-link invite) go
through Keycloak's SMTP — *not* this module. Sender identities are
deliberately split: Keycloak is `noreply-auth@<domain>`, the app is
`noreply@<domain>` (or product-specific). See README of the consuming
template for the env-var contract.
"""

from asunset_core.notifications.factory import make_email_service, make_notifier
from asunset_core.notifications.log import LogNotifier
from asunset_core.notifications.port import EmailMessage, Notifier
from asunset_core.notifications.renderer import EmailTemplate, RenderedEmail
from asunset_core.notifications.resend import ResendNotifier
from asunset_core.notifications.service import EmailService

__all__ = [
    "EmailMessage",
    "EmailService",
    "EmailTemplate",
    "LogNotifier",
    "Notifier",
    "RenderedEmail",
    "ResendNotifier",
    "make_email_service",
    "make_notifier",
]
