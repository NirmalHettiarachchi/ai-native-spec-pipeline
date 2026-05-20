from pathlib import Path

import pytest

from pipeline.errors import PipelineError
from pipeline_web.spec_catalog import (
    list_spec_files,
    resolve_spec_path,
    save_uploaded_spec,
)

VALID_SPEC = b"""
feature_name: Uploaded Discount Feature
feature_objective: Calculate a discount for eligible orders.
user_story: As a shopper, I want to see a discount total.
business_rules:
  - Discounts must never make totals negative.
acceptance_criteria:
  - id: AC-001
    description: Calculates the discounted total.
non_functional_requirements:
  - Must be deterministic.
out_of_scope:
  - Payment processing.
"""


def test_spec_catalog_lists_supported_specs(tmp_path: Path) -> None:
    spec_root = tmp_path / "specs"
    (spec_root / "examples").mkdir(parents=True)
    (spec_root / "examples" / "feature.yaml").write_text("feature: ok", encoding="utf-8")
    (spec_root / "examples" / "feature.txt").write_text("ignore", encoding="utf-8")
    (spec_root / ".hidden").mkdir()
    (spec_root / ".hidden" / "hidden.yaml").write_text("ignore", encoding="utf-8")

    assert list_spec_files(spec_root) == ["specs/examples/feature.yaml"]


def test_spec_catalog_rejects_unsafe_paths(tmp_path: Path) -> None:
    spec_root = tmp_path / "specs"
    spec_root.mkdir()

    with pytest.raises(PipelineError, match="inside specs"):
        resolve_spec_path("../outside.yaml", spec_root)


def test_spec_catalog_stores_valid_upload(tmp_path: Path) -> None:
    spec_root = tmp_path / "specs"

    saved = save_uploaded_spec("uploaded.yaml", VALID_SPEC, spec_root)

    assert saved.parent == spec_root / "uploads"
    assert saved.suffix == ".yaml"
    assert saved.exists()


def test_spec_catalog_rejects_unsupported_upload_extension(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="Uploaded spec must"):
        save_uploaded_spec("uploaded.txt", b"nope", tmp_path / "specs")
