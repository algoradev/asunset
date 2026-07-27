"""SecurityHeadersMiddleware — the FastAPI-served-SPA half of the A7
CSP posture (frontend-sdk-decision.md rule 5)."""

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from asunset_core.middleware import SecurityHeadersMiddleware, build_csp


def make_app(**mw_kwargs) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, **mw_kwargs)

    @app.get("/")
    def index() -> PlainTextResponse:
        return PlainTextResponse("spa shell")

    @app.get("/custom-csp")
    def custom() -> PlainTextResponse:
        return PlainTextResponse(
            "special", headers={"Content-Security-Policy": "default-src 'none'"}
        )

    return app


def test_baseline_posture_on_every_response() -> None:
    client = TestClient(make_app())
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_extra_origins_flow_into_connect_and_frame() -> None:
    client = TestClient(
        make_app(csp_extra_origins="https://auth.example https://api.example")
    )
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "connect-src 'self' https://auth.example https://api.example;" in csp
    assert "frame-src 'self' https://auth.example https://api.example;" in csp


def test_route_level_csp_wins() -> None:
    client = TestClient(make_app())
    r = client.get("/custom-csp")
    assert r.headers["Content-Security-Policy"] == "default-src 'none'"
    # non-CSP posture still applied
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_opt_out_requires_a_reason_and_stamps_nothing() -> None:
    client = TestClient(
        make_app(disabled_reason="caddy sets these headers at the edge (mode tls-acme)")
    )
    r = client.get("/")
    assert "Content-Security-Policy" not in r.headers
    assert "X-Frame-Options" not in r.headers


def test_build_csp_mirrors_the_nginx_template_shape() -> None:
    # The one-implementation-per-plane rule: this string and the nginx
    # template express the SAME posture. If you change one, change both
    # (a7_hardening_test.go pins the nginx side).
    csp = build_csp()
    for directive in [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "frame-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'self'",
    ]:
        assert directive in csp
