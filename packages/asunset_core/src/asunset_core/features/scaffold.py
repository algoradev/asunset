"""Feature scaffold — the ceremony generator (DX list item 5).

    python -m asunset_core.features.scaffold notes.share \
        --grants organization#member --scope note:visible_notes

Prints everything the recipe (docs/adding-a-feature.md) would have you
write: the manifest block, the codegen command, the backend gate, the
frontend guard, and the test skeleton pointers. Print-only by design —
you paste with your eyes open; nothing is edited behind your back.
"""

from __future__ import annotations

import argparse

from asunset_core.features.manifest import FEATURE_KEY_RE


def scaffold_text(key: str, grants: list[str], scopes: list[tuple[str, str]]) -> str:
    if not FEATURE_KEY_RE.match(key):
        raise SystemExit(f"invalid key {key!r} — domain.verb, lowercase, dot-separated")
    const = key.replace(".", "_").upper()
    segs = key.split(".")
    area_note = ""
    if len(segs) >= 3:
        prefix, mode = ".".join(segs[:-1]), segs[-1]
        area_note = (
            f"\n# ≥3 segments: declare the area's mode vocabulary too:\n"
            f"areas:\n  {prefix}:\n    modes: [{mode}]\n"
        )
    grant_lines = "".join(f"\n      - {g}" for g in grants) if grants else " []"
    scope_block = ""
    if scopes:
        scope_block = "\n    scope:" + "".join(
            f"\n      - resource_type: {rt}\n        resolver: {rv}" for rt, rv in scopes
        )
    return f"""── 1. features.yaml ─────────────────────────────────────────────{area_note}
features:
  {key}:
    description: "TODO — operator-facing description"
    grants:{grant_lines}{scope_block}

── 2. regenerate constants ──────────────────────────────────────
python -m asunset_core.features.codegen features.yaml \\
  --py src/<your_pkg>/features_gen.py --ts ../web/src/config/features.gen.ts

── 3. backend gate ──────────────────────────────────────────────
from <your_pkg>.features_gen import Feature
@router.get("/…", dependencies=[Depends(require_feature(Feature.{const}))])
{"# scope: consume the resolver as the sole data door:" if scopes else ""}
{f'# ids = await resolve_scope(manifest, "{key}", "{scopes[0][0]}", principal, authorizer)' if scopes else ""}

── 4. frontend guard ────────────────────────────────────────────
{{has("{key}") && <YourButton />}}

── 5. matrix + tests ────────────────────────────────────────────
python -m asunset_core.features.matrix features.yaml \\
  --md docs/access-matrix.md --skeletons tests/feature_matrix/
# then FILL the generated skeleton — it fails until you do.

── 6. before shipping ───────────────────────────────────────────
Decision record first (docs/feature-decision-template.md): who gets it,
rollout, agents, composition — the access matrix is a designed artifact.
"""


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("key")
    ap.add_argument("--grants", nargs="*", default=[])
    ap.add_argument("--scope", nargs="*", default=[],
                    help="resource_type:resolver pairs")
    args = ap.parse_args(argv)
    scopes = []
    for s in args.scope:
        rt, _, rv = s.partition(":")
        scopes.append((rt, rv))
    print(scaffold_text(args.key, args.grants, scopes))


if __name__ == "__main__":
    main()
