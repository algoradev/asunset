"""Feature scaffold — the ceremony generator (DX list item 5).

    # single capability / flat key:
    python -m asunset_core.features.scaffold notes.share \
        --grants organization#member --scope note:visible_notes
    # a whole AREA in one run (E3 friction: no manual mode-merging):
    python -m asunset_core.features.scaffold notes.share \
        --modes basic=organization#member org_wide=role:sharers#assignee \
        --scope note:visible_notes

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


def area_scaffold_text(
    area: str, modes: dict[str, list[str]], scopes: list[tuple[str, str]]
) -> str:
    """One composed block for a whole area: the modes vocabulary plus
    every capability, no manual merging (caliper's E3 friction #2)."""
    if not FEATURE_KEY_RE.match(area):
        raise SystemExit(f"invalid area {area!r}")
    out = [
        "── 1. features.yaml (whole area, one paste) ─────────────────────",
        "areas:",
        f"  {area}:",
        f"    modes: [{', '.join(modes)}]",
        "features:",
    ]
    for mode, grants in modes.items():
        out.append(f"  {area}.{mode}:")
        out.append('    description: "TODO"')
        if grants:
            out.append("    grants:")
            out += [f"      - {g}" for g in grants]
        else:
            out.append("    grants: []")
        if scopes:
            out.append("    scope:")
            for rt, rv in scopes:
                out.append(f"      - resource_type: {rt}")
                out.append(f"        resolver: {rv}")
    out += [
        "",
        "── then per capability: codegen → gate → guard → matrix/skeletons",
        "(run the single-key scaffold for each capability's snippets, or",
        "follow docs/adding-a-feature.md; decision record first.)",
    ]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("key", help="feature key, or area prefix with --modes")
    ap.add_argument("--grants", nargs="*", default=[])
    ap.add_argument("--modes", nargs="*", default=[],
                    help="mode=grant1,grant2 pairs — scaffolds the whole area")
    ap.add_argument("--scope", nargs="*", default=[],
                    help="resource_type:resolver pairs")
    args = ap.parse_args(argv)
    scopes = []
    for s in args.scope:
        rt, _, rv = s.partition(":")
        scopes.append((rt, rv))
    if args.modes:
        modes: dict[str, list[str]] = {}
        for m in args.modes:
            name, _, grants = m.partition("=")
            modes[name] = [g for g in grants.split(",") if g]
        print(area_scaffold_text(args.key, modes, scopes))
    else:
        print(scaffold_text(args.key, args.grants, scopes))


if __name__ == "__main__":
    main()
