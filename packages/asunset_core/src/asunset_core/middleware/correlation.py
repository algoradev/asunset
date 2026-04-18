"""Correlation ID middleware.

Reads X-Correlation-Id from the incoming request (or mints a fresh UUID),
binds it to structlog's contextvar so every downstream log line includes
it, and echoes it on the response. Downstream callers to OpenFGA / DB /
outbound HTTP propagate the same ID so the SIEM can reconstruct a request.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

HEADER_NAME = "X-Correlation-Id"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(HEADER_NAME)
        trace_id = incoming if incoming and _is_safe(incoming) else uuid.uuid4().hex

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
        )
        # Make the trace_id addressable from anywhere via request.state
        # (routers, dependencies, audit sinks).
        request.state.trace_id = trace_id

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers[HEADER_NAME] = trace_id
        return response


def _is_safe(value: str) -> bool:
    """Reject trace IDs that could be used to inject log noise or headers.

    Clients shouldn't send wild strings here — keep it strict.
    """
    return 1 <= len(value) <= 128 and all(c.isalnum() or c in "-_" for c in value)
