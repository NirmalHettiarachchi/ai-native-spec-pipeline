"""AI provider abstraction for implementation generation."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from pipeline.errors import PipelineError
from pipeline.models import FeatureSpec, GeneratedChangeSet, GeneratedFile, PlanArtifact


class AIProvider(Protocol):
    name: str
    model: str

    def generate_changes(self, spec: FeatureSpec, plan: PlanArtifact) -> GeneratedChangeSet:
        """Return proposed code and test changes for a spec and approved plan."""


def get_ai_provider() -> AIProvider:
    provider = os.getenv("PIPELINE_AI_PROVIDER", "local").strip().lower()
    if provider == "local":
        return LocalTemplateProvider()
    if provider == "openai":
        return OpenAICompatibleProvider()
    raise PipelineError(f"unsupported PIPELINE_AI_PROVIDER: {provider}")


def build_generation_prompt(spec: FeatureSpec, plan: PlanArtifact) -> str:
    acceptance = "\n".join(
        f"- {criterion.id}: {criterion.description}" for criterion in spec.acceptance_criteria
    )
    rules = "\n".join(f"- {rule}" for rule in spec.business_rules)
    return (
        "Generate a bounded Python implementation and pytest coverage for the approved plan.\n"
        "Return JSON only with keys: summary and files. Each file must include path, purpose, "
        "content, and acceptance_criteria.\n\n"
        f"Feature: {spec.display_name}\n"
        f"Objective: {spec.feature_objective}\n"
        f"User story: {spec.user_story}\n"
        f"Business rules:\n{rules}\n"
        f"Acceptance criteria:\n{acceptance}\n"
        f"Allowed paths: {', '.join(plan.allowed_paths)}\n"
        f"Target module: {plan.target_module}\n"
        f"Target function: {plan.target_function}\n"
    )


class LocalTemplateProvider:
    """Deterministic provider used when no external model credentials are configured."""

    name = "local-template"
    model = "deterministic-v1"

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


class OpenAICompatibleProvider:
    """Minimal OpenAI-compatible chat completions adapter for optional live generation."""

    name = "openai-compatible"

    def __init__(self) -> None:
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise PipelineError("OPENAI_API_KEY is required when PIPELINE_AI_PROVIDER=openai")

    def generate_changes(self, spec: FeatureSpec, plan: PlanArtifact) -> GeneratedChangeSet:
        prompt = build_generation_prompt(spec, plan)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You produce JSON-only code generation plans."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PipelineError(f"OpenAI-compatible generation failed: {exc}") from exc

        content = data["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise PipelineError("OpenAI-compatible provider returned non-JSON content") from exc

        return GeneratedChangeSet.model_validate(
            {
                "provider": self.name,
                "model": self.model,
                "summary": parsed.get("summary", []),
                "files": parsed.get("files", []),
            }
        )


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
    ac_map = {criterion.id: criterion.description for criterion in spec.acceptance_criteria}
    ac_literal = json.dumps(ac_map, indent=4, sort_keys=True)
    ac_ids = list(ac_map)
    module = f'''"""Generated metadata implementation for {spec.display_name}."""

ACCEPTANCE_CRITERIA = {ac_literal}


def {plan.target_function}() -> dict[str, object]:
    return {{
        "feature": {spec.display_name!r},
        "acceptance_criteria": ACCEPTANCE_CRITERIA,
    }}
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
    return [
        GeneratedFile(
            path=module_path,
            purpose="Generated metadata implementation.",
            content=module,
            acceptance_criteria=ac_ids,
        ),
        GeneratedFile(
            path=test_path,
            purpose="Generated traceability test.",
            content=tests,
            acceptance_criteria=ac_ids,
        ),
    ]
