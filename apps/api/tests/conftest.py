"""Shared fixtures for the security-path test suite.

The RLS tests need a real Postgres: RLS policies, role splits, and
GRANT/REVOKE semantics don't exist in SQLite and can't be faked. The
`rls_db` fixture stands up an ephemeral postgres:16-alpine container
that mounts the repo's REAL init script (infra/postgres/init/) — so the
owner/app-user role split under test is exactly the production one, not
a test-local imitation — then applies the real Alembic migration chain.

Requires a working `docker` on the host; the whole module skips
otherwise. Container binds 127.0.0.1 on an ephemeral port and is
removed on teardown.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
API_DIR = Path(__file__).resolve().parents[1]

# Mirrors the compose defaults; APP_DB_USER must match what migration
# 0001 GRANTs to (it reads the APP_DB_USER env var, default "asunset").
PG_SUPER = "super"
PG_SUPER_PW = "superpw"
APP_DB_OWNER = "asunset_owner"
APP_DB_OWNER_PW = "ownerpw"
APP_DB_USER = "asunset"
APP_DB_USER_PW = "apppw"
APP_DB_NAME = "asunset"


@dataclass
class SeededDb:
    """Connection DSNs + the fixed IDs the isolation tests assert against."""

    owner_dsn: str
    app_dsn: str

    org_a: UUID = field(default_factory=uuid4)
    org_b: UUID = field(default_factory=uuid4)
    user_a: UUID = field(default_factory=uuid4)   # member of org A
    user_b: UUID = field(default_factory=uuid4)   # member of org B
    team_a: UUID = field(default_factory=uuid4)   # in org A
    team_b: UUID = field(default_factory=uuid4)   # in org B
    note_a: UUID = field(default_factory=uuid4)   # in org A, owned by user_a
    note_b: UUID = field(default_factory=uuid4)   # in org B, owned by user_b
    audit_a: UUID = field(default_factory=uuid4)
    audit_b: UUID = field(default_factory=uuid4)


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        # `version` is much lighter than `info`, and the generous timeout
        # matters: a busy daemon (e.g. another container crash-looping on
        # the host) can stall simple queries for tens of seconds, and a
        # false negative here silently skips the whole isolation suite.
        subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, timeout=60, check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return True


def _start_container() -> tuple[str, int]:
    name = f"asunset-rls-test-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "docker", "run", "-d", "--name", name,
            # Loopback-only, ephemeral host port — never collides.
            "-p", "127.0.0.1::5432",
            "-e", f"POSTGRES_USER={PG_SUPER}",
            "-e", f"POSTGRES_PASSWORD={PG_SUPER_PW}",
            "-e", f"APP_DB_OWNER={APP_DB_OWNER}",
            "-e", f"APP_DB_OWNER_PASSWORD={APP_DB_OWNER_PW}",
            "-e", f"APP_DB_USER={APP_DB_USER}",
            "-e", f"APP_DB_PASSWORD={APP_DB_USER_PW}",
            "-e", f"APP_DB_NAME={APP_DB_NAME}",
            "-e", "KC_DB_USER=kc", "-e", "KC_DB_PASSWORD=kcpw",
            "-e", "KC_DB_NAME=keycloak",
            "-e", "FGA_DB_USER=fga", "-e", "FGA_DB_PASSWORD=fgapw",
            "-e", "FGA_DB_NAME=openfga",
            "-v", f"{REPO_ROOT}/infra/postgres/init:/docker-entrypoint-initdb.d:ro",
            "postgres:16-alpine",
        ],
        check=True,
        capture_output=True,
    )
    out = subprocess.run(
        ["docker", "port", name, "5432/tcp"], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        host, _, port = line.strip().rpartition(":")
        if host.startswith("127.0.0.1"):
            return name, int(port)
    raise RuntimeError(f"could not resolve published port from: {out!r}")


async def _wait_ready(dsn: str, timeout: float = 90.0) -> None:
    # The official image's entrypoint runs init scripts against a
    # socket-only temp server, then restarts listening on TCP — so a
    # successful TCP connect from the host means init fully completed.
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = await asyncpg.connect(dsn, timeout=5)
            await conn.close()
            return
        except Exception as e:  # noqa: BLE001 — retry anything until deadline
            last = e
            await asyncio.sleep(0.5)
    raise RuntimeError(f"postgres container not ready after {timeout}s: {last}")


def _run_migrations(port: int) -> None:
    env = os.environ.copy()
    env.update(
        {
            "APP_DB_URL": (
                f"postgresql+asyncpg://{APP_DB_USER}:{APP_DB_USER_PW}"
                f"@127.0.0.1:{port}/{APP_DB_NAME}"
            ),
            "APP_ADMIN_DB_URL": (
                f"postgresql+asyncpg://{APP_DB_OWNER}:{APP_DB_OWNER_PW}"
                f"@127.0.0.1:{port}/{APP_DB_NAME}"
            ),
            "APP_DB_USER": APP_DB_USER,
            # Settings requires the identity/FGA fields even though
            # migrations never touch them — inert placeholders.
            "KEYCLOAK_ISSUER": "http://placeholder/realms/asunset",
            "KEYCLOAK_INTERNAL_ISSUER": "http://placeholder/realms/asunset",
            "KEYCLOAK_API_CLIENT_ID": "asunset-api",
            "KEYCLOAK_API_CLIENT_SECRET": "placeholder",
            "OPENFGA_API_URL": "http://placeholder:8080",
            "OPENFGA_API_KEY": "placeholder",
        }
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


async def _seed(db: SeededDb) -> None:
    # Seeding runs as the schema OWNER: the owner bypasses RLS (no FORCE
    # ROW LEVEL SECURITY, by design), which is also what the tests must
    # NOT rely on for the app role — that asymmetry is the thing under test.
    conn = await asyncpg.connect(db.owner_dsn)
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO organization (id, name) VALUES ($1, 'Org A'), ($2, 'Org B')",
                db.org_a, db.org_b,
            )
            await conn.execute(
                "INSERT INTO app_user (id, email, display_name) VALUES "
                "($1, 'a@example.test', 'User A'), ($2, 'b@example.test', 'User B')",
                db.user_a, db.user_b,
            )
            await conn.execute(
                "INSERT INTO org_member (org_id, user_id, role) VALUES "
                "($1, $2, 'admin'), ($3, $4, 'member')",
                db.org_a, db.user_a, db.org_b, db.user_b,
            )
            await conn.execute(
                "INSERT INTO team (id, org_id, name) VALUES "
                "($1, $2, 'Team A'), ($3, $4, 'Team B')",
                db.team_a, db.org_a, db.team_b, db.org_b,
            )
            await conn.execute(
                "INSERT INTO team_member (team_id, user_id, role) VALUES "
                "($1, $2, 'member'), ($3, $4, 'member')",
                db.team_a, db.user_a, db.team_b, db.user_b,
            )
            await conn.execute(
                "INSERT INTO note (id, org_id, owner_id, title, body) VALUES "
                "($1, $2, $3, 'Note A', 'body a'), ($4, $5, $6, 'Note B', 'body b')",
                db.note_a, db.org_a, db.user_a, db.note_b, db.org_b, db.user_b,
            )
            await conn.execute(
                "INSERT INTO audit_event "
                "(id, org_id, actor_id, actor_realm_roles, event_type, action, success, payload) "
                "VALUES ($1, $2, $3, '[]', 'test.seed', 'seed', true, '{}'), "
                "       ($4, $5, $6, '[]', 'test.seed', 'seed', true, '{}')",
                db.audit_a, db.org_a, db.user_a, db.audit_b, db.org_b, db.user_b,
            )
    finally:
        await conn.close()


@dataclass
class FgaServer:
    """Connection facts for the ephemeral OpenFGA under test."""

    api_url: str
    api_key: str
    store_id: str = ""
    model_id: str = ""

    def settings(self):  # noqa: ANN201 — CoreSettings, imported lazily
        from asunset_core.config import CoreSettings

        return CoreSettings(
            app_db_url="postgresql+asyncpg://unused/unused",
            app_admin_db_url="postgresql+asyncpg://unused/unused",
            keycloak_issuer="http://placeholder/realms/asunset",
            keycloak_internal_issuer="http://placeholder/realms/asunset",
            keycloak_api_client_id="asunset-api",
            keycloak_api_client_secret="unused",
            openfga_api_url=self.api_url,
            openfga_store_name="asunset-fga-test",
            openfga_api_key=self.api_key,
        )


def _start_fga_container() -> tuple[str, int]:
    name = f"asunset-fga-test-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "docker", "run", "-d", "--name", name,
            "-p", "127.0.0.1::8080",
            # Preshared auth, matching the production compose config —
            # the client-side Credentials path is part of what's under test.
            "-e", "OPENFGA_AUTHN_METHOD=preshared",
            "-e", "OPENFGA_AUTHN_PRESHARED_KEYS=test-key",
            "openfga/openfga:v1.6", "run",
        ],
        check=True,
        capture_output=True,
    )
    out = subprocess.run(
        ["docker", "port", name, "8080/tcp"], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        host, _, port = line.strip().rpartition(":")
        if host.startswith("127.0.0.1"):
            return name, int(port)
    raise RuntimeError(f"could not resolve published port from: {out!r}")


async def _wait_fga_ready(server: FgaServer, timeout: float = 60.0) -> None:
    import httpx

    deadline = time.monotonic() + timeout
    last: object = None
    async with httpx.AsyncClient(
        base_url=server.api_url,
        headers={"Authorization": f"Bearer {server.api_key}"},
        timeout=3.0,
    ) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get("/stores")
                if resp.status_code == 200:
                    return
                last = resp.status_code
            except Exception as e:  # noqa: BLE001 — retry until deadline
                last = e
            await asyncio.sleep(0.4)
    raise RuntimeError(f"openfga container not ready after {timeout}s: {last}")


@pytest.fixture(scope="session")
def fga_server() -> FgaServer:
    """Ephemeral OpenFGA (in-memory datastore, preshared auth) with the
    real platform+Notes model bootstrapped via `bootstrap_openfga` —
    so bootstrap/pinning is itself under test, not just checks."""
    if not _docker_available():
        pytest.skip("docker not available — FGA suite needs a real OpenFGA")

    name, port = _start_fga_container()
    server = FgaServer(api_url=f"http://127.0.0.1:{port}", api_key="test-key")
    try:
        asyncio.run(_wait_fga_ready(server))

        from asunset_api.fga.model import AUTHORIZATION_MODEL
        from asunset_core.fga.bootstrap import bootstrap_openfga

        server.store_id, server.model_id = asyncio.run(
            bootstrap_openfga(server.settings(), AUTHORIZATION_MODEL)
        )
        yield server
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)


@pytest.fixture(scope="session")
def rls_db() -> SeededDb:
    if not _docker_available():
        pytest.skip("docker not available — RLS suite needs a real Postgres")

    name, port = _start_container()
    try:
        db = SeededDb(
            owner_dsn=(
                f"postgresql://{APP_DB_OWNER}:{APP_DB_OWNER_PW}"
                f"@127.0.0.1:{port}/{APP_DB_NAME}"
            ),
            app_dsn=(
                f"postgresql://{APP_DB_USER}:{APP_DB_USER_PW}"
                f"@127.0.0.1:{port}/{APP_DB_NAME}"
            ),
        )
        asyncio.run(_wait_ready(db.app_dsn))
        _run_migrations(port)
        asyncio.run(_seed(db))
        yield db
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)
