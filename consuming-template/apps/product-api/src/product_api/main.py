"""Product FastAPI app.

The pattern: mount asunset's platform routers for org/team/user
management + audit viewer, then mount your own product routers. One
FastAPI app, one set of middleware, one OpenAPI schema.

Almost every line here is identical to asunset_api's own main.py —
because the foundation eats its own dog food. The only product-specific
bits are (a) the AUTHORIZATION_MODEL passed to bootstrap_openfga and
(b) the `report_router` import. Everything else is boilerplate.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from asunset_core.auth.authorizer import OpenFGAAuthorizer, make_openfga_client
from asunset_core.fga.bootstrap import bootstrap_openfga
from asunset_core.logging import configure_logging, get_logger
from asunset_core.middleware.correlation import CorrelationIdMiddleware
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

# Platform HTTP surface — imported from asunset_api, mounted as-is.
from asunset_api.routers import audit as audit_router
from asunset_api.routers import orgs as orgs_router
from asunset_api.routers import platform as platform_router
from asunset_api.routers import teams as teams_router
from asunset_api.routers import users as users_router

from product_api.config import get_settings
from product_api.fga_model import AUTHORIZATION_MODEL
from product_api.router import router as report_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.api_log_level)
    log.info("product_api.startup", env=settings.product_env)

    store_id, model_id = await bootstrap_openfga(settings, AUTHORIZATION_MODEL)
    fga_client = make_openfga_client(settings, store_id, model_id)
    app.state.authorizer = OpenFGAAuthorizer(fga_client, store_id, model_id)
    app.state.fga_client = fga_client

    yield

    await fga_client.close()
    log.info("product_api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Product API (built on asunset)",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-Id"],
    )

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz(response: Response) -> dict:
        from asunset_core.db.session import get_session_factory

        settings = get_settings()
        checks: dict[str, dict[str, str]] = {}
        ok_all = True

        try:
            async with get_session_factory()() as session:
                await session.execute(text("SELECT 1"))
            checks["db"] = {"status": "ok"}
        except Exception as e:
            checks["db"] = {"status": "fail", "error": str(e)[:200]}
            ok_all = False

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{settings.openfga_api_url}/stores")
                resp.raise_for_status()
            checks["openfga"] = {"status": "ok"}
        except Exception as e:
            checks["openfga"] = {"status": "fail", "error": str(e)[:200]}
            ok_all = False

        if not ok_all:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "ok" if ok_all else "degraded", "checks": checks}

    # Platform routers — same surface as the Notes demo.
    app.include_router(platform_router.router)
    app.include_router(orgs_router.router)
    app.include_router(teams_router.router)
    app.include_router(users_router.router)
    app.include_router(audit_router.router)

    # Your product's routes.
    app.include_router(report_router)

    return app


app = create_app()
