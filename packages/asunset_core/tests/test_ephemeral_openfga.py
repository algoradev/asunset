"""ephemeral_openfga — the helper atlas's cluster-C done-line drives.

Exists because the helper shipped untested and its original sync shape
was structurally uncallable (the aiohttp/loop contradiction, found in
the field 2026-07-30). This is the exact consumer driving pattern:
one asyncio.run, everything under one loop.
"""

import asyncio
import shutil
import subprocess

import pytest

from asunset_core.fga.model import build_model
from asunset_core.auth.authorizer import Tuple
from asunset_core.testing import ephemeral_openfga


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "version"], capture_output=True, timeout=60, check=True
        )
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not docker_available(), reason="docker unavailable"
)


def test_ephemeral_openfga_full_session_under_one_loop() -> None:
    model = build_model([])  # platform baseline is a complete model

    async def main() -> None:
        async with ephemeral_openfga(model) as authorizer:
            # A real write + check round-trip against the live container
            # proves the client was built under this loop and works.
            await authorizer.write(
                [Tuple("user:alice", "member", "organization:acme")],
                tolerate_existing=True,
            )
            assert await authorizer.check(
                "user:alice", "member", "organization:acme"
            )
            assert not await authorizer.check(
                "user:bob", "member", "organization:acme"
            )

    # The consumer shape: ONE asyncio.run drives the whole session.
    asyncio.run(main())


def test_platform_types_are_present_in_bootstrap() -> None:
    async def main() -> None:
        async with ephemeral_openfga(build_model([])) as authorizer:
            # The bootstrapped model must carry the platform types —
            # a write against `team` succeeding proves the model took.
            await authorizer.write(
                [Tuple("user:alice", "member", "team:t1")],
                tolerate_existing=True,
            )
            assert await authorizer.check("user:alice", "member", "team:t1")

    asyncio.run(main())
