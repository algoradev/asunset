"""Async SQLAlchemy session management with per-request RLS context.

Every request sets `app.current_user_id` and `app.current_org_id` session
vars before any query runs. Postgres RLS policies (see Alembic migration)
reference these vars to enforce tenant isolation at the DB layer — defense
in depth behind the OpenFGA authorization layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from asunset_core.config import get_core_settings as get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_admin_engine: AsyncEngine | None = None
_admin_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.app_db_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            future=True,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


def get_admin_session_factory() -> async_sessionmaker[AsyncSession]:
    """Connection factory for platform ops (bootstrap, reconcile).

    Uses the schema-owner role, which bypasses RLS as the table owner. Use
    sparingly — only from platform_admin-scoped endpoints and the CLI.
    Every caller is audit-logged.
    """
    global _admin_engine, _admin_session_factory
    if _admin_session_factory is None:
        settings = get_settings()
        _admin_engine = create_async_engine(
            settings.app_admin_db_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=4,
            future=True,
        )
        _admin_session_factory = async_sessionmaker(_admin_engine, expire_on_commit=False)
    return _admin_session_factory


@asynccontextmanager
async def session_scope(
    user_id: UUID | None = None,
    org_id: UUID | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open a session with RLS session vars set for the acting principal.

    Passing None for either var sets it to the empty string, which RLS
    policies interpret as "no principal" (blocks tenant-scoped rows).
    Use this shape for unauthenticated probes (health, readyz).
    """
    factory = get_session_factory()
    async with factory() as session:
        # Use SET LOCAL so the vars scope to the current transaction.
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true), "
                 "set_config('app.current_org_id', :oid, true)"),
            {
                "uid": str(user_id) if user_id else "",
                "oid": str(org_id) if org_id else "",
            },
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — overridden by the auth layer to inject
    the authenticated principal's IDs into session_scope.
    """
    async with session_scope() as session:
        yield session
