"""Helpers for consumer products' Alembic migrations.

Why this exists: a consumer's first migration needs to chain after
asunset's last platform migration. Doing that with a literal revision
id — `down_revision = "0004"` — goes stale every time asunset adds a
platform migration, and the failure mode is brutal: Alembic finds two
heads (the platform's real head and the consumer's stuck chain),
refuses to upgrade with a "Multiple head revisions are present"
error, and the operator stares at it. centum-dashboard hit this once
already (B-MIGRATIONS, separate root cause but same symptom class).

Use in your consumer's first migration:

    from asunset_core.alembic_helpers import platform_head

    revision: str = "1000"
    down_revision: str | None = platform_head()

Now your chain anchors to whatever platform head was current when
`vendor/asunset/` was last pulled — `git subtree pull` updates the
constant, no manual bump needed.

When asunset's contributors add a new platform migration, they bump
`PLATFORM_HEAD` below. A test in this repo asserts the constant
matches the actual head of `apps/api/alembic/versions/`, so the bump
can't be silently forgotten.
"""

from __future__ import annotations

# The current head of asunset's platform migrations
# (apps/api/alembic/versions/). Bumped by hand whenever a new platform
# migration lands. `tests/test_alembic_helpers.py` enforces the match.
PLATFORM_HEAD = "0005"


def platform_head() -> str:
    """Return the head revision id of asunset's platform migrations.

    Designed to be called at module-import time in a consumer's
    Alembic migration:

        revision: str = "<your id>"
        down_revision: str | None = platform_head()

    Returns the value of `PLATFORM_HEAD` — a function rather than
    direct constant access so future versions can change the
    resolution strategy (e.g. read the actual versions/ directory
    at import time) without breaking call sites.
    """
    return PLATFORM_HEAD
