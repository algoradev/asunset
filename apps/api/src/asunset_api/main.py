from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from asunset_core.auth.authorizer import OpenFGAAuthorizer, make_openfga_client
from asunset_api.config import get_settings
from asunset_api.features_boot import reconcile_features_startup
from asunset_api.fga.model import AUTHORIZATION_MODEL
from asunset_core.fga.bootstrap import bootstrap_openfga
from asunset_core.logging import configure_logging, get_logger
from asunset_core.middleware.correlation import CorrelationIdMiddleware
from asunset_core.notifications import make_email_service
from asunset_api.routers import audit as audit_router
from asunset_api.routers import notes as notes_router
from asunset_api.routers import orgs as orgs_router
from asunset_api.routers import platform as platform_router
from asunset_api.routers import teams as teams_router
from asunset_api.routers import users as users_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.api_log_level)
    log.info("api.startup", env=settings.asunset_env)

    store_id, model_id = await bootstrap_openfga(settings, AUTHORIZATION_MODEL)
    fga_client = make_openfga_client(settings, store_id, model_id)
    app.state.authorizer = OpenFGAAuthorizer(fga_client, store_id, model_id)
    app.state.fga_client = fga_client  # kept so lifespan shutdown can close it

    # Email service is app-scoped — one Notifier + Jinja2 env reused for
    # the lifetime of the process. CoreSettings drives backend selection
    # (NOTIFIER=log|resend) and the sender + template overrides.
    app.state.email_service = make_email_service(settings)

    # Feature manifest → FGA tuples (feature spec §5). Best-effort at
    # startup: needs the org to exist, so a pre-bootstrap instance skips
    # with a log and /platform/bootstrap re-runs it after org creation.
    await reconcile_features_startup(app.state.authorizer, settings)

    yield

    await fga_client.close()
    log.info("api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Asunset API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Order matters: CORS outermost so its headers land on every response;
    # CorrelationId runs inside CORS so preflights don't pollute context.
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-Id"],
    )

    # Agent-session denials on administrative surfaces
    # (SessionScopedAuthorizer.write/read_tuples) raise PermissionError —
    # a clean 403, not an unhandled 500. Any consumer main.py mounting
    # platform routers should carry the same handler.
    @app.exception_handler(PermissionError)
    async def _permission_error_403(request: Request, exc: PermissionError) -> Response:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        """Liveness — the process is up and serving. No external deps."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz(response: Response) -> dict:
        """Readiness — probes every dep the API can't function without.

        Returns 200 only when DB, FGA, and JWKS are all reachable. The
        per-check breakdown is always in the body so operators can see
        *which* dep is flaking without reading logs.
        """
        from asunset_core.db.session import get_session_factory

        settings = get_settings()
        checks: dict[str, dict[str, str]] = {}
        all_ok = True

        try:
            factory = get_session_factory()
            async with factory() as session:
                await session.execute(text("SELECT 1"))
            checks["db"] = {"status": "ok"}
        except Exception as e:
            checks["db"] = {"status": "fail", "error": str(e)[:200]}
            all_ok = False

        try:
            # OpenFGA runs with preshared-key auth — an unauthenticated
            # probe 401s and reports a healthy server as failed.
            async with httpx.AsyncClient(
                timeout=3.0,
                headers={"Authorization": f"Bearer {settings.openfga_api_key}"},
            ) as client:
                resp = await client.get(f"{settings.openfga_api_url}/stores")
                resp.raise_for_status()
            checks["openfga"] = {"status": "ok"}
        except Exception as e:
            checks["openfga"] = {"status": "fail", "error": str(e)[:200]}
            all_ok = False

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.head(
                    f"{settings.keycloak_internal_issuer}/protocol/openid-connect/certs"
                )
                # 200 or 405 (if HEAD unsupported) both mean the endpoint exists.
                if resp.status_code not in (200, 405):
                    resp.raise_for_status()
            checks["keycloak_jwks"] = {"status": "ok"}
        except Exception as e:
            checks["keycloak_jwks"] = {"status": "fail", "error": str(e)[:200]}
            all_ok = False

        if not all_ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "ok" if all_ok else "degraded", "checks": checks}

    app.include_router(platform_router.router)
    app.include_router(orgs_router.router)
    app.include_router(teams_router.router)
    app.include_router(notes_router.router)
    app.include_router(users_router.router)
    app.include_router(audit_router.router)

    return app


app = create_app()
