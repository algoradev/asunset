"""Consumer testing kit (DX pass, docs/feature-cycle-story.md item 1).

Two speeds for testing authorization-gated code, both first-class:

FAST (no containers) — `StaticAuthorizer`: a decision-level stub of the
Authorizer port. You declare ALLOWED (user, relation, object) triples;
everything else denies. It stubs *decisions*, deliberately not FGA
model semantics (no userset expansion, no derived relations) — if your
test depends on how `can_edit` derives from `owner or editor`, that is
model behavior and belongs against the real thing (below). Writes are
recorded, not evaluated, so tests can assert the dual-write happened.

REAL (one container) — `ephemeral_openfga()`: boots a disposable
OpenFGA (in-memory datastore, preshared auth matching production),
bootstraps YOUR authorization model through the real
`bootstrap_openfga`, and yields a live `OpenFGAAuthorizer`. This is the
same harness asunset's own security suites use.

Typical pytest wiring:

    # fast path — endpoint logic
    authz = StaticAuthorizer()
    authz.allow("user:alice", "can_use", "feature:reports.export")
    app.state.authorizer = authz

    # real path — model semantics (session-scoped; needs docker)
    @pytest.fixture(scope="session")
    def fga():
        with ephemeral_openfga(MY_AUTHORIZATION_MODEL) as authorizer:
            yield authorizer

Feature helpers: `grant_feature(...)` writes the `can_use` tuple in
either speed; `allow_feature_for_org(...)` mirrors what the manifest
reconciler would have granted.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator

from asunset_core.auth.authorizer import AccessPath, Tuple

__all__ = [
    "StaticAuthorizer",
    "ephemeral_openfga",
    "grant_feature",
    "allow_feature_for_org",
]


@dataclass
class StaticAuthorizer:
    """Decision-level Authorizer stub: allowed triples in, booleans out.

    - `check` consults the allow-set (supports `*` for any relation and
      `type:*` / `*` object patterns, mirroring session-grant patterns).
    - `list_objects` returns allowed objects of the type for that user.
    - `write` RECORDS (never evaluates) so tests assert dual-writes;
      set `fail_writes=True` to exercise the FGA-write-fails rollback
      ordering documented in the authorizer module.
    - `explain` returns the configured `AccessPath` (default: a direct
      path when allowed, None when not).
    Deny-by-default everywhere.
    """

    allowed: set[tuple[str, str, str]] = field(default_factory=set)
    writes: list[Tuple] = field(default_factory=list)
    deletes: list[Tuple] = field(default_factory=list)
    fail_writes: bool = False
    explain_path: AccessPath | None = None

    def allow(self, user: str, relation: str, obj: str) -> "StaticAuthorizer":
        self.allowed.add((user, relation, obj))
        return self

    def _matches(self, user: str, relation: str, obj: str) -> bool:
        for (u, r, o) in self.allowed:
            if u != user:
                continue
            if r not in ("*", relation):
                continue
            if o == "*" or o == obj:
                return True
            if o.endswith(":*") and ":" in obj and obj.split(":", 1)[0] == o[:-2]:
                return True
        return False

    async def check(self, user: str, relation: str, object: str) -> bool:
        return self._matches(user, relation, object)

    async def list_objects(self, user: str, relation: str, object_type: str) -> list[str]:
        out = {
            o for (u, r, o) in self.allowed
            if u == user and r in ("*", relation)
            and ":" in o and o.split(":", 1)[0] == object_type and not o.endswith(":*")
        }
        return sorted(out)

    async def list_users(
        self, object: str, relation: str, user_type: str = "user"
    ) -> list[str]:
        out = {
            u for (u, r, o) in self.allowed
            if o == object and r in ("*", relation)
            and ":" in u and u.split(":", 1)[0] == user_type and "#" not in u
        }
        return sorted(out)

    async def read_tuples(
        self,
        *,
        user: str | None = None,
        relation: str | None = None,
        object: str | None = None,
    ) -> list[Tuple]:
        out = []
        for (u, r, o) in sorted(self.allowed):
            if user is not None and u != user:
                continue
            if relation is not None and r != relation:
                continue
            if object is not None:
                if object.endswith(":") and not o.startswith(object):
                    continue
                if not object.endswith(":") and o != object:
                    continue
            out.append(Tuple(user=u, relation=r, object=o))
        return out

    async def explain(self, user: str, relation: str, object: str) -> AccessPath | None:
        if not self._matches(user, relation, object):
            return None
        return self.explain_path or AccessPath(kind="direct", via_relation=relation)

    async def explain_note_access(self, user: str, note: str) -> str:
        return "direct_viewer" if self._matches(user, "can_view", note) else "unknown"

    async def write(
        self,
        writes: list[Tuple] | None = None,
        deletes: list[Tuple] | None = None,
        *,
        tolerate_existing: bool = False,
    ) -> None:
        if self.fail_writes:
            raise RuntimeError("StaticAuthorizer: writes configured to fail")
        for t in writes or []:
            self.writes.append(t)
            self.allowed.add((t.user, t.relation, t.object))
        for t in deletes or []:
            self.deletes.append(t)
            self.allowed.discard((t.user, t.relation, t.object))


# --- feature helpers -------------------------------------------------------


def grant_feature(authorizer: Any, user: str, key: str) -> None:
    """Grant `can_use feature:<key>` to a user (or userset string).

    Works with StaticAuthorizer synchronously and with a live authorizer
    inside an event loop via asyncio.run when called from sync test code.
    """
    t = Tuple(user=user, relation="can_use", object=f"feature:{key}")
    if isinstance(authorizer, StaticAuthorizer):
        authorizer.allowed.add((t.user, t.relation, t.object))
        return
    coro = authorizer.write(writes=[t], tolerate_existing=True)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
    else:  # already in a loop (async test) — caller should await write();
        loop.create_task(coro)  # best-effort for sync-call-in-async misuse


def allow_feature_for_org(authorizer: Any, org_id: Any, key: str, relation: str = "member") -> None:
    """Mirror what the manifest reconciler would grant: the org userset."""
    grant_feature(authorizer, f"organization:{org_id}#{relation}", key)


# --- ephemeral real OpenFGA ------------------------------------------------


@asynccontextmanager
async def ephemeral_openfga(
    authorization_model: dict[str, Any],
    *,
    image: str = "openfga/openfga:v1.6",
    api_key: str = "test-key",
) -> AsyncIterator[Any]:
    """Boot a disposable OpenFGA, bootstrap the given model, yield a live
    OpenFGAAuthorizer. Loopback-only ephemeral port; container removed on
    exit. Raises RuntimeError if docker is unavailable — wrap in a
    pytest.skip in consumer conftests if docker is optional there.

    ASYNC context manager — drive the whole session under ONE loop::

        async def main():
            async with ephemeral_openfga(MODEL) as authorizer:
                report = await reconcile_features(authorizer, manifest, org,
                                                  dry_run=True)
        asyncio.run(main())

    (It was briefly a sync contextmanager; that shape was structurally
    broken — the openfga-sdk's aiohttp transport must be constructed and
    used under a running loop, while the sync body's own asyncio.run
    calls forbade one. Found by atlas wiring cluster C, 2026-07-30.)"""
    from asunset_core.auth.authorizer import OpenFGAAuthorizer, make_openfga_client
    from asunset_core.config import CoreSettings
    from asunset_core.fga.bootstrap import bootstrap_openfga

    if shutil.which("docker") is None:
        raise RuntimeError("docker not available for ephemeral_openfga")

    name = f"asunset-testkit-fga-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "docker", "run", "-d", "--name", name,
            "-p", "127.0.0.1::8080",
            "-e", "OPENFGA_AUTHN_METHOD=preshared",
            "-e", f"OPENFGA_AUTHN_PRESHARED_KEYS={api_key}",
            image, "run",
        ],
        check=True, capture_output=True,
    )
    try:
        out = subprocess.run(
            ["docker", "port", name, "8080/tcp"], check=True, capture_output=True, text=True
        ).stdout
        port = None
        for line in out.splitlines():
            host, _, p = line.strip().rpartition(":")
            if host.startswith("127.0.0.1"):
                port = int(p)
                break
        if port is None:
            raise RuntimeError(f"could not resolve openfga port from {out!r}")

        settings = CoreSettings(
            app_db_url="postgresql+asyncpg://unused/unused",
            app_admin_db_url="postgresql+asyncpg://unused/unused",
            keycloak_issuer="http://placeholder/realms/test",
            keycloak_internal_issuer="http://placeholder/realms/test",
            keycloak_api_client_id="asunset-api",
            keycloak_api_client_secret="unused",
            openfga_api_url=f"http://127.0.0.1:{port}",
            openfga_store_name="testkit",
            openfga_api_key=api_key,
        )

        # Readiness + bootstrap + client construction + use + close all
        # happen under the CALLER'S loop — the whole point of the async
        # shape: aiohttp binds its transport to the loop it's built in.
        import httpx

        deadline = time.monotonic() + 60
        last: object = None
        async with httpx.AsyncClient(
            base_url=settings.openfga_api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=3.0,
        ) as probe:
            while time.monotonic() < deadline:
                try:
                    if (await probe.get("/stores")).status_code == 200:
                        break
                    last = "non-200"
                except Exception as e:  # noqa: BLE001
                    last = e
                await asyncio.sleep(0.4)
            else:
                raise RuntimeError(f"openfga not ready: {last}")

        store_id, model_id = await bootstrap_openfga(settings, authorization_model)
        client = make_openfga_client(settings, store_id, model_id)
        try:
            yield OpenFGAAuthorizer(client, store_id, model_id)
        finally:
            await client.close()
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)
