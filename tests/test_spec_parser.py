import json
from pathlib import Path

import pytest

from pipeline.errors import SpecValidationError
from pipeline.spec_parser import parse_feature_spec


def test_parse_yaml_example() -> None:
    spec = parse_feature_spec(Path("specs/examples/discount_calculator.yaml"))

    assert spec.feature_id == "discount-calculator"
    assert [criterion.id for criterion in spec.acceptance_criteria] == [
        "AC-001",
        "AC-002",
        "AC-003",
        "AC-004",
    ]


def test_missing_required_section_fails(tmp_path: Path) -> None:
    spec_path = tmp_path / "invalid.yaml"
    spec_path.write_text("feature_objective: Missing important sections\n", encoding="utf-8")

    with pytest.raises(SpecValidationError, match="missing required section"):
        parse_feature_spec(spec_path)


def test_parse_markdown_sections(tmp_path: Path) -> None:
    spec_path = tmp_path / "feature.md"
    spec_path.write_text(
        """# Markdown Feature

## Feature Objective
Ship a markdown-driven feature.

## User Story
As a user, I want markdown specs.

## Business Rules
- Rule one.
- Rule two.

## Acceptance Criteria
- AC-001: First acceptance criterion.
- AC-002: Second acceptance criterion.

## Non-functional Requirements
- Deterministic behavior.

## Out of Scope
- External integrations.
""",
        encoding="utf-8",
    )

    spec = parse_feature_spec(spec_path)

    assert spec.feature_name == "Markdown Feature"
    assert spec.acceptance_criteria[0].id == "AC-001"
    assert spec.acceptance_criteria[1].description == "Second acceptance criterion."


def test_parse_json_string_acceptance_criteria(tmp_path: Path) -> None:
    spec_path = tmp_path / "feature.json"
    spec_path.write_text(
        json.dumps(
            {
                "feature_objective": "Support JSON specs.",
                "user_story": "As an engineer, I want JSON input.",
                "business_rules": ["Rule one."],
                "acceptance_criteria": ["JSON specs validate."],
                "non_functional_requirements": ["Fast validation."],
                "out_of_scope": ["Runtime codegen."],
            }
        ),
        encoding="utf-8",
    )

    spec = parse_feature_spec(spec_path)

    assert spec.acceptance_criteria[0].id == "AC-001"
    assert spec.acceptance_criteria[0].description == "JSON specs validate."

