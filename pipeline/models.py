from __future__ import annotations

import re
from typing import Any, Literal

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


class ImplementationTask(BaseModel):
    """Task generated from a validated feature specification."""

    id: str
    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class PlanArtifact(BaseModel):
    """Technical plan derived from the normalized specification."""

    run_id: str
    spec_hash: str
    spec_version: str
    spec_slug: str
    target_module: str
    target_function: str
    technical_design_summary: str
    implementation_tasks: list[ImplementationTask]
    impacted_modules_files: list[str]
    risk_considerations: list[str]
    test_strategy: list[str]
    allowed_paths: list[str]
    created_at: str

    def to_json_data(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ApprovalRecord(BaseModel):
    """Human approval record bound to a specific artefact hash."""

    run_id: str
    stage: Literal["plan", "release"]
    approver: str
    artifact_path: str
    artifact_hash: str
    approved_at: str
    decision: Literal["approved"] = "approved"
    signature: str

    def to_json_data(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class GeneratedFile(BaseModel):
    """Generated file content proposed by an AI provider."""

    path: str
    purpose: str
    content: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class GeneratedChangeSet(BaseModel):
    """Provider output before deterministic policy enforcement writes files."""

    provider: str
    model: str
    summary: list[str]
    files: list[GeneratedFile]

    def to_json_data(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ChangeManifestEntry(BaseModel):
    """Manifest entry for one generated file."""

    path: str
    purpose: str
    content_sha256: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class ChangeManifest(BaseModel):
    """Bounded generated-change manifest written before file mutation."""

    run_id: str
    provider: str
    model: str
    generated_at: str
    plan_hash: str
    spec_hash: str
    allowed_paths: list[str]
    summary: list[str]
    files: list[ChangeManifestEntry]

    def to_json_data(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class GateResult(BaseModel):
    """Result from one deterministic quality gate."""

    name: str
    status: Literal["passed", "failed"]
    command: list[str] = Field(default_factory=list)
    return_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    details: list[str] = Field(default_factory=list)
    started_at: str
    finished_at: str


class ValidationResults(BaseModel):
    """Aggregated validation status for a pipeline run."""

    run_id: str
    overall_status: Literal["passed", "failed"]
    created_at: str
    gates: list[GateResult]

    def to_json_data(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
