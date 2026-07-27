"""Security headers for FastAPI/Starlette-served SPAs.

The asunset browser posture (A7) keeps tokens in memory only — which is
only as strong as the XSS controls around it. asunset's own demo web is
served by nginx, whose template carries the CSP; a foreign-UI consumer
serving its SPA from FastAPI (the OpsRoom shape) has no nginx, so this
middleware is the one implementation of the same posture for that plane
(frontend-sdk-decision.md, ratified rule 5).

Contract: NOT silently optional. A consumer wiring @asunset/web-sdk
serves its SPA behind this middleware in the same slice; opting out
requires a recorded reason (``disabled_reason=``), which is logged
loudly on every boot so review and doctor can see it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

CSP_HEADER = "Content-Security-Policy"


def build_csp(extra_origins: str = "") -> str:
    """The asunset baseline CSP — mirrors apps/web/nginx.conf.template.

    ``extra_origins`` is the space-separated cross-origin allowance for
    connect/frame (the CSP_EXTRA_ORIGINS mechanism: auth + api hosts in
    TLS mode, empty in single-origin modes).
    """
    extra = f" {extra_origins.strip()}" if extra_origins.strip() else ""
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        f"connect-src 'self'{extra}; "
        f"frame-src 'self'{extra}; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'"
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Stamp the asunset security-header posture on every response.

    Per-route override: a response that already carries its own
    Content-Security-Policy is left untouched (the route knows better);
    the non-CSP headers are still applied unless present.
    """

    def __init__(
        self,
        app,  # type: ignore[no-untyped-def] — Starlette's ASGIApp
        *,
        csp_extra_origins: str = "",
        disabled_reason: str | None = None,
    ) -> None:
        super().__init__(app)
        self._csp = build_csp(csp_extra_origins)
        self._disabled_reason = disabled_reason
        if disabled_reason is not None:
            # Opt-out is legitimate only with a recorded reason — and it
            # stays loud, not a one-time whisper buried in scrollback.
            logger.warning(
                "security_headers_disabled",
                reason=disabled_reason,
                consequence=(
                    "SPA responses carry NO CSP from this process — the "
                    "in-memory token posture is unprotected unless another "
                    "layer (nginx/caddy) sets these headers"
                ),
            )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if self._disabled_reason is not None:
            return response
        if CSP_HEADER not in response.headers:
            response.headers[CSP_HEADER] = self._csp
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response
