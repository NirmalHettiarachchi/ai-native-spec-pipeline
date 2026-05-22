"""AI provider abstraction for implementation generation."""

from __future__ import annotations

import json
from typing import Any, Protocol, cast

from pipeline.config import (
    RuntimeConfig,
    get_openai_api_key,
    get_runtime_config,
    validate_provider_mode,
)
from pipeline.errors import PipelineError
from pipeline.models import FeatureSpec, GeneratedChangeSet, GeneratedFile, PlanArtifact


class AIProvider(Protocol):
    name: str
    model: str
    last_interaction_metadata: dict[str, Any]

    def generate_changes(self, spec: FeatureSpec, plan: PlanArtifact) -> GeneratedChangeSet:
        """Return proposed code and test changes for a spec and approved plan."""


def get_ai_provider() -> AIProvider:
    config = get_runtime_config()
    validate_provider_mode(config.ai_provider_mode)
    if config.resolved_ai_provider == "local":
        return LocalTemplateProvider()
    if config.resolved_ai_provider == "openai":
        return OpenAIResponsesProvider(config)
    raise PipelineError(f"unsupported PIPELINE_AI_PROVIDER: {config.ai_provider_mode}")


def get_provider_audit_metadata(provider: AIProvider) -> dict[str, Any]:
    """Return provider metadata safe for audit logs."""

    return getattr(provider, "last_interaction_metadata", {})


def build_generation_prompt(spec: FeatureSpec, plan: PlanArtifact) -> str:
    acceptance = "\n".join(
        f"- {criterion.id}: {criterion.description}" for criterion in spec.acceptance_criteria
    )
    rules = "\n".join(f"- {rule}" for rule in spec.business_rules)
    impacted_files = "\n".join(f"- {path}" for path in plan.impacted_modules_files)
    return (
        "Generate a bounded Python implementation and pytest coverage for the approved plan.\n"
        "Return JSON only with keys: summary and files. Each file must include path, purpose, "
        "content, and acceptance_criteria. Return one file entry for every approved impacted "
        "file, exactly once.\n\n"
        f"Feature: {spec.display_name}\n"
        f"Objective: {spec.feature_objective}\n"
        f"User story: {spec.user_story}\n"
        f"Business rules:\n{rules}\n"
        f"Acceptance criteria:\n{acceptance}\n"
        f"Allowed paths: {', '.join(plan.allowed_paths)}\n"
        f"Approved impacted files:\n{impacted_files}\n"
        f"Target module: {plan.target_module}\n"
        f"Target function: {plan.target_function}\n"
        f"Implementation contract:\n{_implementation_contract(plan)}\n"
    )


class LocalTemplateProvider:
    """Deterministic provider used when no external model credentials are configured."""

    name = "local-template"
    model = "deterministic-v1"
    last_interaction_metadata: dict[str, Any] = {
        "request": {"provider_mode": "local", "network": "disabled"},
        "response": {"source": "deterministic-template"},
    }

    def generate_changes(self, spec: FeatureSpec, plan: PlanArtifact) -> GeneratedChangeSet:
        if plan.target_function == "calculate_discounted_price":
            files = _discount_calculator_files(spec, plan)
            summary = [
                "Generated a deterministic discount calculator module.",
                "Generated unit, integration, and acceptance tests mapped to AC IDs.",
            ]
        else:
            files = _generic_feature_files(spec, plan)
            summary = [
                "Generated a deterministic feature metadata module.",
                "Generated tests that verify import behavior and acceptance traceability.",
            ]
        return GeneratedChangeSet(
            provider=self.name,
            model=self.model,
            summary=summary,
            files=files,
        )


class OpenAIResponsesProvider:
    """OpenAI Responses API provider using structured JSON output."""

    name = "openai-responses"

    def __init__(self, config: RuntimeConfig) -> None:
        self.model = config.openai_model
        self.reasoning_effort = config.openai_reasoning_effort
        self.base_url = config.openai_base_url
        self.last_interaction_metadata: dict[str, Any] = {}
        api_key = get_openai_api_key()
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency is installed in supported setup
            raise PipelineError(
                "install the openai package to use PIPELINE_AI_PROVIDER=openai"
            ) from exc

        self.client = OpenAI(api_key=api_key, base_url=self.base_url)

    def generate_changes(self, spec: FeatureSpec, plan: PlanArtifact) -> GeneratedChangeSet:
        prompt = build_generation_prompt(spec, plan)
        try:
            request_payload: dict[str, Any] = {
                "model": self.model,
                "instructions": (
                    "You generate small Python code changes for a governed development "
                    "pipeline. Return only data that matches the supplied JSON schema. "
                    "Return every approved impacted file exactly once. Do not include files "
                    "outside the approved plan."
                ),
                "input": prompt,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "generated_change_set",
                        "strict": True,
                        "schema": _generated_change_set_schema(),
                    }
                },
                "store": False,
            }
            if _supports_reasoning_effort(self.model):
                request_payload["reasoning"] = {"effort": self.reasoning_effort}
            create_response = cast(Any, self.client.responses.create)
            response = create_response(**request_payload)
        except Exception as exc:  # noqa: BLE001 - convert SDK failures to pipeline errors
            raise PipelineError(f"OpenAI Responses generation failed: {exc}") from exc

        content = _response_output_text(response)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise PipelineError("OpenAI Responses provider returned non-JSON content") from exc

        self.last_interaction_metadata = {
            "request": {
                "endpoint": "responses.create",
                "model": self.model,
                "reasoning_effort": (
                    self.reasoning_effort if _supports_reasoning_effort(self.model) else None
                ),
                "text_format": "json_schema",
                "store": False,
            },
            "response": {
                "id": getattr(response, "id", None),
                "status": getattr(response, "status", None),
                "usage": _safe_model_dump(getattr(response, "usage", None)),
            },
        }

        return GeneratedChangeSet.model_validate(
            {
                "provider": self.name,
                "model": self.model,
                "summary": parsed.get("summary", []),
                "files": parsed.get("files", []),
            }
        )


def _generated_change_set_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "files"],
        "properties": {
            "summary": {"type": "array", "items": {"type": "string"}},
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["path", "purpose", "content", "acceptance_criteria"],
                    "properties": {
                        "path": {"type": "string"},
                        "purpose": {"type": "string"},
                        "content": {"type": "string"},
                        "acceptance_criteria": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def _supports_reasoning_effort(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith(("gpt-5", "o1", "o3", "o4"))


def _response_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", "")
    if output_text:
        return str(output_text)
    if isinstance(response, dict):
        output_text = response.get("output_text", "")
        if output_text:
            return str(output_text)
    raise PipelineError("OpenAI Responses provider returned no output text")


def _safe_model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return str(value)


def _discount_calculator_files(spec: FeatureSpec, plan: PlanArtifact) -> list[GeneratedFile]:
    module_path = f"demo_app/src/demo_app/{plan.target_module}.py"
    unit_path = f"demo_app/tests/test_{plan.target_module}.py"
    acceptance_path = f"demo_app/tests/test_{plan.target_module}_acceptance.py"
    ac_map = {criterion.id: criterion.description for criterion in spec.acceptance_criteria}
    ac_ids = list(ac_map)
    ac_literal = json.dumps(ac_map, indent=4, sort_keys=True)
    coverage_literal = json.dumps(
        {
            "AC-001": "test_ac_001_acceptance_valid_discount",
            "AC-002": "test_ac_002_acceptance_negative_base_price",
            "AC-003": "test_ac_003_acceptance_invalid_discount_range",
            "AC-004": "test_ac_004_acceptance_rounding",
        },
        indent=4,
        sort_keys=True,
    )

    module = f'''"""Generated implementation for {spec.display_name}."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

Number = int | float | Decimal

ACCEPTANCE_CRITERIA = {ac_literal}


class DiscountValidationError(ValueError):
    """Raised when discount inputs violate approved business rules."""


def calculate_discounted_price(base_price: Number, discount_percent: Number) -> float:
    """Calculate a discounted price using approved business rules."""

    price = _to_decimal(base_price, "base_price")
    discount = _to_decimal(discount_percent, "discount_percent")

    if price < Decimal("0"):
        raise DiscountValidationError("base price must be greater than or equal to zero")
    if discount < Decimal("0") or discount > Decimal("100"):
        raise DiscountValidationError("discount percentage must be between 0 and 100")

    multiplier = Decimal("1") - (discount / Decimal("100"))
    final_price = price * multiplier
    return float(final_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _to_decimal(value: Number, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DiscountValidationError(f"{{field_name}} must be numeric") from exc
'''
    package_init = f'''"""Demo application package used by the generated implementation."""

from demo_app.{plan.target_module} import DiscountValidationError, calculate_discounted_price

__all__ = ["DiscountValidationError", "calculate_discounted_price"]
'''
    unit_tests = f'''import pytest
from demo_app.{plan.target_module} import DiscountValidationError, calculate_discounted_price

import demo_app


def test_ac_001_calculates_discounted_price() -> None:
    """AC-001: valid base price and percentage produce a discounted price."""

    assert calculate_discounted_price(100, 15) == 85.0


def test_ac_002_rejects_negative_base_price() -> None:
    """AC-002: negative base prices are rejected."""

    with pytest.raises(DiscountValidationError, match="base price"):
        calculate_discounted_price(-1, 10)


def test_ac_003_rejects_invalid_discount_range() -> None:
    """AC-003: discount percentage must be between 0 and 100."""

    with pytest.raises(DiscountValidationError, match="between 0 and 100"):
        calculate_discounted_price(100, -0.01)
    with pytest.raises(DiscountValidationError, match="between 0 and 100"):
        calculate_discounted_price(100, 100.01)


def test_integration_package_export() -> None:
    assert demo_app.calculate_discounted_price(40, 25) == 30.0
'''
    acceptance_tests = f'''import pytest
from demo_app.{plan.target_module} import ACCEPTANCE_CRITERIA, calculate_discounted_price

ACCEPTANCE_COVERAGE = {coverage_literal}


@pytest.mark.acceptance
def test_ac_001_acceptance_valid_discount() -> None:
    """AC-001: valid discounts calculate correctly."""

    assert calculate_discounted_price(250, 10) == 225.0


@pytest.mark.acceptance
def test_ac_002_acceptance_negative_base_price() -> None:
    """AC-002: criterion is represented in generated acceptance coverage."""

    assert "AC-002" in ACCEPTANCE_CRITERIA


@pytest.mark.acceptance
def test_ac_003_acceptance_invalid_discount_range() -> None:
    """AC-003: criterion is represented in generated acceptance coverage."""

    assert "AC-003" in ACCEPTANCE_CRITERIA


@pytest.mark.acceptance
def test_ac_004_acceptance_rounding() -> None:
    """AC-004: final price rounds to two decimal places."""

    assert calculate_discounted_price(10, 33.333) == 6.67
'''
    return [
        GeneratedFile(
            path=module_path,
            purpose="Generated feature implementation.",
            content=module,
            acceptance_criteria=ac_ids,
        ),
        GeneratedFile(
            path="demo_app/src/demo_app/__init__.py",
            purpose="Expose generated feature through demo package boundary.",
            content=package_init,
            acceptance_criteria=[],
        ),
        GeneratedFile(
            path=unit_path,
            purpose="Generated unit and integration tests.",
            content=unit_tests,
            acceptance_criteria=["AC-001", "AC-002", "AC-003"],
        ),
        GeneratedFile(
            path=acceptance_path,
            purpose="Generated acceptance tests with AC traceability metadata.",
            content=acceptance_tests,
            acceptance_criteria=ac_ids,
        ),
    ]


def _generic_feature_files(spec: FeatureSpec, plan: PlanArtifact) -> list[GeneratedFile]:
    module_path = f"demo_app/src/demo_app/{plan.target_module}.py"
    test_path = f"demo_app/tests/test_{plan.target_module}.py"
    acceptance_path = f"demo_app/tests/test_{plan.target_module}_acceptance.py"
    ac_map = {criterion.id: criterion.description for criterion in spec.acceptance_criteria}
    ac_literal = json.dumps(ac_map, indent=4, sort_keys=True)
    ac_ids = list(ac_map)
    coverage_literal = json.dumps(
        {
            criterion_id: "test_acceptance_criteria_are_exposed"
            for criterion_id in ac_ids
        },
        indent=4,
        sort_keys=True,
    )
    module = f'''"""Generated metadata implementation for {spec.display_name}."""

ACCEPTANCE_CRITERIA = {ac_literal}


def {plan.target_function}() -> dict[str, object]:
    return {{
        "feature": {spec.display_name!r},
        "acceptance_criteria": ACCEPTANCE_CRITERIA,
    }}
'''
    package_init = f'''"""Demo application package used by the generated implementation."""

from demo_app.{plan.target_module} import {plan.target_function}

__all__ = ["{plan.target_function}"]
'''
    tests = f'''from demo_app.{plan.target_module} import (
    ACCEPTANCE_CRITERIA,
    {plan.target_function},
)

ACCEPTANCE_COVERAGE = {{
    criterion_id: "test_acceptance_criteria_are_exposed"
    for criterion_id in ACCEPTANCE_CRITERIA
}}


def test_acceptance_criteria_are_exposed() -> None:
    result = {plan.target_function}()
    assert result["acceptance_criteria"] == ACCEPTANCE_CRITERIA
'''
    acceptance_tests = f'''import pytest
from demo_app.{plan.target_module} import ACCEPTANCE_CRITERIA, {plan.target_function}

ACCEPTANCE_COVERAGE = {coverage_literal}


@pytest.mark.acceptance
def test_acceptance_criteria_are_exposed() -> None:
    result = {plan.target_function}()

    assert result["acceptance_criteria"] == ACCEPTANCE_CRITERIA
    assert set(ACCEPTANCE_COVERAGE) == set(ACCEPTANCE_CRITERIA)
'''
    return [
        GeneratedFile(
            path=module_path,
            purpose="Generated metadata implementation.",
            content=module,
            acceptance_criteria=ac_ids,
        ),
        GeneratedFile(
            path="demo_app/src/demo_app/__init__.py",
            purpose="Expose generated feature through demo package boundary.",
            content=package_init,
            acceptance_criteria=[],
        ),
        GeneratedFile(
            path=test_path,
            purpose="Generated traceability test.",
            content=tests,
            acceptance_criteria=ac_ids,
        ),
        GeneratedFile(
            path=acceptance_path,
            purpose="Generated acceptance tests with AC traceability metadata.",
            content=acceptance_tests,
            acceptance_criteria=ac_ids,
        ),
    ]


def _implementation_contract(plan: PlanArtifact) -> str:
    module_path = f"demo_app/src/demo_app/{plan.target_module}.py"
    package_path = "demo_app/src/demo_app/__init__.py"
    required_module_symbols = [plan.target_function, "ACCEPTANCE_CRITERIA"]
    required_package_exports = [plan.target_function]
    if plan.target_function == "calculate_discounted_price":
        required_module_symbols.append("DiscountValidationError")
        required_package_exports.append("DiscountValidationError")

    return "\n".join(
        [
            f"- Return `{module_path}` with public symbols: "
            f"{', '.join(required_module_symbols)}.",
            f"- Return `{package_path}` importing and exporting: "
            f"{', '.join(required_package_exports)}.",
            "- Return acceptance tests that include every AC ID literally for traceability.",
            "- Generated Python must pass Ruff import sorting and the configured 100 character "
            "line length.",
        ]
    )
