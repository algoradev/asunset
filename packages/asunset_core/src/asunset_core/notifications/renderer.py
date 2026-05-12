"""Locale-aware Jinja2 email template renderer.

A template `X` is three files in the locale directory:
  - `X.subject.txt`  → the email subject (single line, whitespace
                       trimmed).
  - `X.html`         → the HTML body (HTML-autoescape on).
  - `X.txt`          → the plain-text body (no autoescape — it's text).

Lookup walks the requested locale first, then falls back to `en`. So a
consumer can ship only the locales they care about and asunset's
defaults cover the rest. Add new locales by dropping files into
`templates/<locale>/` and registering an extra dir if they live outside
the bundled package.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    select_autoescape,
)

DEFAULT_LOCALE = "en"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def _bundled_templates_dir() -> Path:
    """Path to the templates shipped inside this package."""
    return Path(str(resources.files("asunset_core.notifications") / "templates"))


class EmailTemplate:
    """Renders an email template trio (subject + html + text) for a locale.

    `extra_dirs` are searched *before* the bundled asunset defaults, so
    a consumer can override a single template (e.g. `welcome.html`)
    without copying the whole set.
    """

    def __init__(
        self,
        *,
        extra_dirs: list[Path] | None = None,
        default_locale: str = DEFAULT_LOCALE,
    ) -> None:
        search_dirs: list[Path] = []
        if extra_dirs:
            search_dirs.extend(extra_dirs)
        search_dirs.append(_bundled_templates_dir())

        # Two envs because HTML autoescape on subject/.txt would corrupt
        # entity-bearing text. ChoiceLoader gives us locale → en fallback
        # via the path prefix in each template name.
        loader = ChoiceLoader([FileSystemLoader(str(d)) for d in search_dirs])
        self._html_env = Environment(
            loader=loader,
            autoescape=select_autoescape(["html", "htm"]),
            keep_trailing_newline=False,
        )
        self._text_env = Environment(
            loader=loader,
            autoescape=False,
            keep_trailing_newline=False,
        )
        self._default_locale = default_locale

    def render(
        self,
        name: str,
        *,
        locale: str | None = None,
        context: dict | None = None,
    ) -> RenderedEmail:
        ctx = context or {}
        locales = self._locale_chain(locale)
        subject = self._render_first(
            self._text_env,
            [f"{lc}/{name}.subject.txt" for lc in locales],
            ctx,
        ).strip()
        html = self._render_first(
            self._html_env,
            [f"{lc}/{name}.html" for lc in locales],
            ctx,
        )
        text = self._render_first(
            self._text_env,
            [f"{lc}/{name}.txt" for lc in locales],
            ctx,
        )
        return RenderedEmail(subject=subject, html=html, text=text)

    def _locale_chain(self, locale: str | None) -> list[str]:
        chosen = (locale or self._default_locale).split("-", 1)[0].lower()
        if chosen == self._default_locale:
            return [chosen]
        return [chosen, self._default_locale]

    @staticmethod
    def _render_first(env: Environment, candidates: list[str], ctx: dict) -> str:
        # Jinja2's select_template tries each name in order and falls
        # back to the next on TemplateNotFound. Raises if none exist.
        tmpl = env.select_template(candidates)
        return tmpl.render(**ctx)
