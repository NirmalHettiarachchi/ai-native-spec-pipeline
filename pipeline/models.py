"""Typed artefact models for the spec-driven pipeline."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def _strip_required(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        msg = "value must not be empty"
        raise ValueError(msg)
    return stripped


def _non_empty_list(values: list[str]) -> list[str]:
    cleaned = [_strip_required(value) for value in values]
    if not cleaned:
        msg = "list must contain at least one item"
        raise ValueError(msg)
    return cleaned


class AcceptanceCriterion(BaseModel):
    """A single acceptance condition with a stable traceability ID."""

    id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)

    @field_validator("id", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip_required(value)


class FeatureSpec(BaseModel):
    """Normalized feature specification accepted by the pipeline."""

    schema_version: str = "1.0"
    feature_id: str | None = None
    feature_name: str | None = None
    feature_objective: str = Field(..., min_length=1)
    user_story: str = Field(..., min_length=1)
    business_rules: list[str] = Field(..., min_length=1)
    acceptance_criteria: list[AcceptanceCriterion] = Field(..., min_length=1)
    non_functional_requirements: list[str] = Field(..., min_length=1)
    out_of_scope: list[str] = Field(..., min_length=1)

    @field_validator("feature_objective", "user_story")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return _strip_required(value)

    @field_validator("feature_id", "feature_name")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("business_rules", "non_functional_requirements", "out_of_scope")
    @classmethod
    def strip_required_list(cls, value: list[str]) -> list[str]:
        return _non_empty_list(value)

    @model_validator(mode="after")
    def require_unique_acceptance_ids(self) -> FeatureSpec:
        ids = [criterion.id for criterion in self.acceptance_criteria]
        duplicates = sorted({criterion_id for criterion_id in ids if ids.count(criterion_id) > 1})
        if duplicates:
            msg = f"acceptance criterion IDs must be unique: {', '.join(duplicates)}"
            raise ValueError(msg)
        return self

    @property
    def display_name(self) -> str:
        return self.feature_name or self.feature_id or self.feature_objective

    @property
    def slug(self) -> str:
        raw = self.feature_id or self.feature_name or self.feature_objective
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").lower()
        return slug[:60] or "feature"

    def to_json_data(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

