"""The demo dogfoods the codegen loop: generated files must never lag
features.yaml (consumers copy this exact test)."""

from pathlib import Path

from asunset_core.features.codegen import assert_generated_current

API_DIR = Path(__file__).parents[1]


def test_feature_codegen_current() -> None:
    assert_generated_current(
        str(API_DIR / "features.yaml"),
        py_path=str(API_DIR / "src/asunset_api/features_gen.py"),
        ts_path=str(API_DIR.parent / "web/src/config/features.gen.ts"),
    )
