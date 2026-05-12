"""Assert PLATFORM_HEAD tracks the actual head of apps/api/alembic/versions/.

The whole point of `platform_head()` is to spare consumers from
chasing a literal revision id. If the constant in asunset_core drifts
from the real chain head, that promise is broken — every fresh
consumer pull would silently chain to the wrong revision.

This test walks the on-disk migration files, computes the head (the
revision nothing else points at as `down_revision`), and asserts it
matches `PLATFORM_HEAD`. Runs only when the monorepo layout is
available (skips if asunset_core was installed standalone).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from asunset_core.alembic_helpers import PLATFORM_HEAD


_REVISION_RE = re.compile(r'^revision\s*:\s*str\s*=\s*["\']([^"\']+)["\']', re.M)
_DOWN_RE = re.compile(
    r'^down_revision\s*:\s*[^=]*=\s*(?:["\']([^"\']+)["\']|None)', re.M
)


def _versions_dir() -> Path | None:
    """Locate apps/api/alembic/versions/ relative to this test file.

    test_alembic_helpers.py lives at
      <repo>/packages/asunset_core/tests/test_alembic_helpers.py
    so the repo root is four parents up.
    """
    candidate = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "apps"
        / "api"
        / "alembic"
        / "versions"
    )
    return candidate if candidate.is_dir() else None


def test_platform_head_matches_actual_chain_head() -> None:
    versions = _versions_dir()
    if versions is None:
        pytest.skip("apps/api/alembic/versions/ not on disk (asunset_core installed standalone)")

    revisions: dict[str, str | None] = {}
    for path in sorted(versions.glob("*.py")):
        text = path.read_text()
        rev_m = _REVISION_RE.search(text)
        if not rev_m:
            continue
        down_m = _DOWN_RE.search(text)
        revisions[rev_m.group(1)] = down_m.group(1) if (down_m and down_m.group(1)) else None

    assert revisions, f"no migration files parsed in {versions}"

    pointed_at = {down for down in revisions.values() if down}
    heads = set(revisions) - pointed_at
    assert len(heads) == 1, (
        f"expected exactly one platform head, got {sorted(heads)!r}. "
        "Branch in the platform migration chain — fix that before bumping PLATFORM_HEAD."
    )
    actual = next(iter(heads))

    assert PLATFORM_HEAD == actual, (
        f"PLATFORM_HEAD = {PLATFORM_HEAD!r} but apps/api/alembic/versions/ head is "
        f"{actual!r}. Bump PLATFORM_HEAD in packages/asunset_core/src/asunset_core/"
        f"alembic_helpers.py whenever a new platform migration lands."
    )
