"""Generated artifacts of the capability model (spec §11): the access
matrix (design-time projection) and per-row test skeletons.

The matrix is a PROJECTION — never a second source of truth. Skeletons
are fail-until-filled and embed the declaration fingerprint they
evidence: change the declaration and the filled skeleton fails stale
instead of passing against a dead claim.

    python -m asunset_core.features.matrix features.yaml --md docs/access-matrix.md
    python -m asunset_core.features.matrix features.yaml --skeletons tests/feature_matrix/
"""

from __future__ import annotations

import argparse
from pathlib import Path

from asunset_core.features.manifest import FeatureManifest, load_manifest

_HEADER = "GENERATED from features.yaml — do not edit; re-run asunset_core.features.matrix"


def matrix_markdown(manifest: FeatureManifest) -> str:
    lines = [
        f"<!-- {_HEADER} -->",
        "# Access matrix (design-time projection)",
        "",
        "Runtime grants legitimately diverge from this (per-user/team grants,",
        "freezes) — the runtime truth is GET /platform/features; the diff",
        "between the two is a compliance REPORT, never a gate.",
        "",
        "| Capability | State | Default personas | Declared reach | UI state |",
        "|---|---|---|---|---|",
    ]
    for f in manifest.features:
        personas = ", ".join(f.grants) if f.grants else "*runtime-only*"
        reach = (
            "; ".join(f"{sp.resource_type} → {sp.resolver}" for sp in f.scopes)
            if f.scopes
            else "*undeclared (grandfathered)*"
        )
        state = "enabled" if f.enabled else "**disabled**"
        lines.append(f"| `{f.key}` | {state} | {personas} | {reach} | _(design column)_ |")
    if manifest.areas:
        lines += ["", "## Areas (declared mode vocabularies)", ""]
        for prefix, modes in sorted(manifest.areas.items()):
            lines.append(f"- `{prefix}`: {', '.join(modes)}")
    return "\n".join(lines) + "\n"


def skeleton_source(manifest: FeatureManifest, key: str) -> str:
    """One capability's test skeleton: a live fingerprint assert (fails
    the moment the declaration changes) + one fail-until-filled test per
    matrix row. Never auto-passing."""
    f = next(x for x in manifest.features if x.key == key)
    fp = manifest.fingerprint(key)
    mod = key.replace(".", "_")
    lines = [
        f'"""Matrix-row evidence for {key} — {_HEADER}.',
        "",
        "Generated FAIL-UNTIL-FILLED: replace each pytest.fail with real",
        "evidence (use asunset_core.testing). The fingerprint assert stays —",
        "it is what makes this file fail STALE when the declaration changes.",
        '"""',
        "",
        "import pytest",
        "",
        "from asunset_core.features.codegen import assert_declaration_fingerprint",
        "",
        f'FEATURE_KEY = "{key}"',
        f'EXPECTED_FINGERPRINT = "{fp}"',
        "",
        "",
        f"def test_{mod}_declaration_current() -> None:",
        '    assert_declaration_fingerprint("features.yaml", FEATURE_KEY, EXPECTED_FINGERPRINT)',
    ]
    rows = list(f.grants) if f.grants else ["runtime_grantee"]
    for grant in rows:
        gid = grant.replace("#", "_").replace(":", "_").replace("-", "_")
        lines += [
            "",
            "",
            f"async def test_{mod}_allowed_{gid}() -> None:",
            f'    pytest.fail("FILL ME: evidence that {grant} may use {key}'
            f'{" within declared scope " + ", ".join(sp.resolver for sp in f.scopes) if f.scopes else ""}")',
        ]
    lines += [
        "",
        "",
        f"async def test_{mod}_denied_outsider() -> None:",
        f'    pytest.fail("FILL ME: evidence that an unrelated principal is denied {key}")',
    ]
    return "\n".join(lines) + "\n"


def write_skeletons(manifest: FeatureManifest, out_dir: Path) -> tuple[list[str], list[str]]:
    """Create MISSING skeletons only — a filled file is never
    overwritten (its staleness is the fingerprint assert's job).
    Returns (created, skipped)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    created, skipped = [], []
    for f in manifest.features:
        path = out_dir / f"test_matrix_{f.key.replace('.', '_')}.py"
        if path.exists():
            skipped.append(path.name)
            continue
        path.write_text(skeleton_source(manifest, f.key))
        created.append(path.name)
    return created, skipped


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest")
    ap.add_argument("--md", help="write the access matrix markdown here")
    ap.add_argument("--skeletons", help="directory for per-capability test skeletons")
    args = ap.parse_args(argv)

    manifest = load_manifest(args.manifest)
    if args.md:
        Path(args.md).write_text(matrix_markdown(manifest))
        print(f"matrix → {args.md}")
    if args.skeletons:
        created, skipped = write_skeletons(manifest, Path(args.skeletons))
        print(f"skeletons: {len(created)} created {created}, {len(skipped)} existing kept")
    if not (args.md or args.skeletons):
        ap.error("nothing to do — pass --md and/or --skeletons")


if __name__ == "__main__":
    main()
