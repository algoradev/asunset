"""Generate typed feature constants from the manifest.

Both sides consume the SAME features.yaml, so `feature:reports.exprot`
is a compile-time error instead of a silent 403:

    python -m asunset_core.features.codegen features.yaml \
        --py src/product_api/features_gen.py \
        --ts apps/web/src/config/features.gen.ts

Emitted files are fully regenerated (marked as such) — never hand-edit.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from asunset_core.features.manifest import FeatureManifest, load_manifest

_HEADER = "GENERATED from features.yaml — do not edit; re-run asunset_core.features.codegen"


def python_module(manifest: FeatureManifest) -> str:
    lines = [
        f'"""{_HEADER}"""',
        "",
        "from enum import StrEnum",
        "",
        "",
        "class Feature(StrEnum):",
    ]
    if not manifest.features:
        lines.append("    pass")
    for f in manifest.features:
        const = f.key.replace(".", "_").upper()
        lines.append(f'    {const} = "{f.key}"  # {f.description}'.rstrip())
    out = "\n".join(lines) + "\n"
    if manifest.areas:
        out += areas_python(manifest)
    return out


def ts_module(manifest: FeatureManifest) -> str:
    lines = [f"// {_HEADER}", ""]
    keys = ", ".join(f'"{f.key}"' for f in manifest.features)
    lines.append(f"export const FEATURES = [{keys}] as const;")
    lines.append("export type FeatureKey = (typeof FEATURES)[number];")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest")
    ap.add_argument("--py", help="output path for the Python enum module")
    ap.add_argument("--ts", help="output path for the TypeScript union module")
    args = ap.parse_args(argv)

    manifest = load_manifest(args.manifest)
    if args.py:
        Path(args.py).write_text(python_module(manifest))
    if args.ts:
        Path(args.ts).write_text(ts_module(manifest))
    if not (args.py or args.ts):
        ap.error("nothing to do — pass --py and/or --ts")


if __name__ == "__main__":
    main()


def assert_generated_current(
    manifest_path: str, *, py_path: str | None = None, ts_path: str | None = None
) -> None:
    """Raise AssertionError if generated files lag the manifest — drop
    into any consumer test:

        def test_feature_codegen_current():
            assert_generated_current("features.yaml",
                                     py_path="src/product_api/features_gen.py",
                                     ts_path="apps/web/src/config/features.gen.ts")
    """
    manifest = load_manifest(manifest_path)
    regen_cmd = "python -m asunset_core.features.codegen"
    if py_path is not None:
        expected = python_module(manifest)
        actual = Path(py_path).read_text() if Path(py_path).exists() else "<missing>"
        assert actual == expected, (
            f"{py_path} is stale vs {manifest_path} — regenerate with: "
            f"{regen_cmd} {manifest_path} --py {py_path}"
        )
    if ts_path is not None:
        expected = ts_module(manifest)
        actual = Path(ts_path).read_text() if Path(ts_path).exists() else "<missing>"
        assert actual == expected, (
            f"{ts_path} is stale vs {manifest_path} — regenerate with: "
            f"{regen_cmd} {manifest_path} --ts {ts_path}"
        )


def assert_declaration_fingerprint(
    manifest_path: str, key: str, expected: str
) -> None:
    """The stale-failing guard filled skeletons embed (spec §11): fails
    the moment the capability's declaration (grants/scope/enabled)
    changes, so evidence never silently outlives its claim."""
    actual = load_manifest(manifest_path).fingerprint(key)
    assert actual == expected, (
        f"declaration of {key!r} changed (fingerprint {actual} != evidenced {expected}) — "
        f"re-verify the matrix-row tests against the new declaration, then update "
        f"EXPECTED_FINGERPRINT"
    )


def areas_python(manifest) -> str:  # noqa: ANN001
    """Grouped ergonomics (review #2, relay §5): canonical enum stays
    flat; these groupings serve docs/UI, resolving to canonical keys."""
    lines = ["", "", "FEATURE_AREAS = {"]
    for prefix, modes in sorted(manifest.areas.items()):
        lines.append(f'    "{prefix}": {sorted(modes)!r},')
    lines.append("}")
    lines.append("")
    lines.append("CAPABILITIES_BY_AREA = {")
    for prefix in sorted(manifest.areas):
        caps = sorted(f.key for f in manifest.features if f.key.startswith(prefix + "."))
        lines.append(f'    "{prefix}": {caps!r},')
    lines.append("}")
    return "\n".join(lines) + "\n"
