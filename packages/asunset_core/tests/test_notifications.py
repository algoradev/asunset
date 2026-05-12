"""Unit tests for the notifications layer.

Pure unit tests — no DB, no real HTTP. ResendNotifier is exercised
through httpx.MockTransport so we assert the exact request shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from asunset_core.notifications import (
    EmailMessage,
    EmailService,
    EmailTemplate,
    LogNotifier,
    ResendNotifier,
)
from asunset_core.notifications.factory import make_notifier
from asunset_core.notifications.resend import ResendError


# --- EmailTemplate ---------------------------------------------------


def test_renders_bundled_en_welcome() -> None:
    tpl = EmailTemplate()
    out = tpl.render(
        "welcome",
        locale="en",
        context={"display_name": "Alice", "org_name": "Acme", "app_url": "https://app"},
    )
    assert out.subject == "Welcome to Acme"
    assert "Welcome, Alice." in out.html
    assert "Welcome, Alice." in out.text
    assert "https://app" in out.text


def test_renders_bundled_es_welcome() -> None:
    tpl = EmailTemplate()
    out = tpl.render(
        "welcome",
        locale="es",
        context={"display_name": "Ana", "org_name": "Acme", "app_url": "https://app"},
    )
    assert out.subject == "Bienvenido a Acme"
    assert "Bienvenido, Ana." in out.text


def test_falls_back_to_en_for_unknown_locale() -> None:
    tpl = EmailTemplate()
    out = tpl.render(
        "welcome",
        locale="fr",  # not shipped
        context={"display_name": "X", "org_name": "Y", "app_url": "Z"},
    )
    # Should silently fall back to en rather than raising.
    assert out.subject == "Welcome to Y"


def test_locale_with_region_collapses_to_base(tmp_path: Path) -> None:
    tpl = EmailTemplate()
    out = tpl.render(
        "welcome",
        locale="es-MX",
        context={"display_name": "Ana", "org_name": "Acme", "app_url": "https://app"},
    )
    assert out.subject.startswith("Bienvenido")


def test_extra_dir_overrides_bundled(tmp_path: Path) -> None:
    # Drop a single overridden template into an extra dir; renderer
    # should pick it before the bundled version.
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "welcome.subject.txt").write_text("Hi {{ display_name }}\n")
    (tmp_path / "en" / "welcome.html").write_text("<p>Hi {{ display_name }}</p>")
    (tmp_path / "en" / "welcome.txt").write_text("Hi {{ display_name }}")

    tpl = EmailTemplate(extra_dirs=[tmp_path])
    out = tpl.render(
        "welcome",
        locale="en",
        context={"display_name": "Override"},
    )
    assert out.subject == "Hi Override"
    assert out.html == "<p>Hi Override</p>"


def test_html_autoescape_on_html_body_only() -> None:
    tpl = EmailTemplate()
    out = tpl.render(
        "welcome",
        locale="en",
        context={
            "display_name": "<script>",
            "org_name": "Acme",
            "app_url": "https://app",
        },
    )
    # HTML body must autoescape; text body must not.
    assert "<script>" not in out.html
    assert "&lt;script&gt;" in out.html
    assert "<script>" in out.text


# --- LogNotifier -----------------------------------------------------


async def test_log_notifier_does_not_raise() -> None:
    notifier = LogNotifier()
    await notifier.send(
        EmailMessage(
            to=("a@example.com",),
            subject="hi",
            sender="from@example.com",
            text="body",
        )
    )


# --- ResendNotifier --------------------------------------------------


async def test_resend_notifier_posts_expected_payload() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"id": "msg_123"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    notifier = ResendNotifier(api_key="rk_test_xyz", client=client)

    await notifier.send(
        EmailMessage(
            to=("alice@example.com", "bob@example.com"),
            subject="Hello",
            sender="ops@example.com",
            html="<p>hi</p>",
            text="hi",
            reply_to="reply@example.com",
            headers={"X-Tag": "welcome"},
        )
    )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["auth"] == "Bearer rk_test_xyz"
    assert captured["body"] == {
        "from": "ops@example.com",
        "to": ["alice@example.com", "bob@example.com"],
        "subject": "Hello",
        "html": "<p>hi</p>",
        "text": "hi",
        "reply_to": "reply@example.com",
        "headers": {"X-Tag": "welcome"},
    }


async def test_resend_notifier_raises_on_non_2xx() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(422, text="invalid"))
    notifier = ResendNotifier(
        api_key="rk_test_xyz",
        client=httpx.AsyncClient(transport=transport),
    )
    with pytest.raises(ResendError):
        await notifier.send(
            EmailMessage(
                to=("a@example.com",),
                subject="hi",
                sender="from@example.com",
                text="body",
            )
        )


async def test_resend_notifier_requires_html_or_text() -> None:
    notifier = ResendNotifier(
        api_key="rk_test_xyz",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
    )
    with pytest.raises(ValueError):
        await notifier.send(
            EmailMessage(
                to=("a@example.com",),
                subject="empty",
                sender="from@example.com",
            )
        )


def test_resend_notifier_requires_api_key() -> None:
    with pytest.raises(ValueError):
        ResendNotifier(api_key="")


# --- EmailService ----------------------------------------------------


async def test_email_service_renders_then_sends() -> None:
    sent: list[EmailMessage] = []

    class Capture:
        async def send(self, message: EmailMessage) -> None:
            sent.append(message)

    svc = EmailService(
        notifier=Capture(),
        template=EmailTemplate(),
        default_sender="ops@example.com",
    )
    await svc.send(
        template="welcome",
        to="alice@example.com",
        locale="en",
        context={"display_name": "Alice", "org_name": "Acme", "app_url": "https://app"},
    )
    assert len(sent) == 1
    msg = sent[0]
    assert msg.to == ("alice@example.com",)
    assert msg.subject == "Welcome to Acme"
    assert msg.sender == "ops@example.com"
    assert "Welcome, Alice." in msg.text


async def test_email_service_accepts_list_of_recipients() -> None:
    sent: list[EmailMessage] = []

    class Capture:
        async def send(self, message: EmailMessage) -> None:
            sent.append(message)

    svc = EmailService(
        notifier=Capture(),
        template=EmailTemplate(),
        default_sender="ops@example.com",
    )
    await svc.send(
        template="welcome",
        to=["a@example.com", "b@example.com"],
        context={"display_name": "X", "org_name": "Y", "app_url": "Z"},
    )
    assert sent[0].to == ("a@example.com", "b@example.com")


# --- factory ---------------------------------------------------------


def _make_settings(**overrides):
    """Build a CoreSettings stub with just the fields the factory reads."""
    from types import SimpleNamespace

    defaults = dict(
        notifier_backend="log",
        resend_api_key="",
        notifier_default_sender="from@example.com",
        notifier_default_locale="en",
        notifier_template_dir="",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_factory_defaults_to_log() -> None:
    n = make_notifier(_make_settings())
    assert isinstance(n, LogNotifier)


def test_factory_returns_resend_when_configured() -> None:
    n = make_notifier(_make_settings(notifier_backend="resend", resend_api_key="rk_x"))
    assert isinstance(n, ResendNotifier)


def test_factory_resend_without_key_raises() -> None:
    with pytest.raises(ValueError):
        make_notifier(_make_settings(notifier_backend="resend"))


def test_factory_unknown_backend_raises() -> None:
    with pytest.raises(ValueError):
        make_notifier(_make_settings(notifier_backend="sendgrid"))
