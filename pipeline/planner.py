"""Planning layer for turning validated specs into technical artefacts."""

from __future__ import annotations

from pathlib import Path

from pipeline.audit import utc_now
from pipeline.models import FeatureSpec, ImplementationTask, PlanArtifact


def create_plan(spec: FeatureSpec, run_id: str, spec_hash: str) -> PlanArtifact:
    module_name = spec.slug.replace("-", "_")
    target_function = _target_function(spec)
    acceptance_ids = [criterion.id for criterion in spec.acceptance_criteria]
    impacted_files = [
        f"demo_app/src/demo_app/{module_name}.py",
        "demo_app/src/demo_app/__init__.py",
        f"demo_app/tests/test_{module_name}.py",
        f"demo_app/tests/test_{module_name}_acceptance.py",
    ]

    tasks = [
        ImplementationTask(
            id="TASK-001",
            title="Implement bounded demo application feature",
            description=(
                f"Add `{target_function}` in `{module_name}` with behavior derived from "
                "business rules and acceptance criteria."
            ),
            acceptance_criteria=acceptance_ids,
        ),
        ImplementationTask(
            id="TASK-002",
            title="Generate unit and integration tests",
            description="Cover core behavior, invalid inputs, and module import boundaries.",
            acceptance_criteria=acceptance_ids,
        ),
        ImplementationTask(
            id="TASK-003",
            title="Generate acceptance traceability tests",
            description="Add acceptance coverage metadata and tests mapped to every AC ID.",
            acceptance_criteria=acceptance_ids,
        ),
        ImplementationTask(
            id="TASK-004",
            title="Run deterministic quality gates",
            description="Execute lint, type, test, security, allowed-path, and AC coverage checks.",
            acceptance_criteria=[],
        ),
    ]

    return PlanArtifact(
        run_id=run_id,
        spec_hash=spec_hash,
        spec_version=spec.schema_version,
        spec_slug=spec.slug,
        target_module=module_name,
        target_function=target_function,
        technical_design_summary=(
            f"Create a small, reviewable Python module for `{spec.display_name}`. "
            "The implementation is deterministic, side-effect free, and constrained to "
            "the demo application package. Generated tests provide unit, integration, "
            "and acceptance-level coverage."
        ),
        implementation_tasks=tasks,
        impacted_modules_files=impacted_files,
        risk_considerations=[
            "AI-generated code could drift from accepted business rules without traceable tests.",
            "Generated changes must remain inside approved demo app paths.",
            "Validation should fail closed when approvals, tests, or policy evidence are missing.",
            *[f"NFR: {requirement}" for requirement in spec.non_functional_requirements],
        ],
        test_strategy=[
            "Unit tests cover business-rule branches and validation errors.",
            "Integration tests import the generated module through the demo package boundary.",
            "Acceptance tests include explicit markers for every acceptance criterion ID.",
            "Policy checks verify generated files and AC coverage against the approved plan.",
        ],
        allowed_paths=[
            "demo_app/src/demo_app/",
            "demo_app/tests/",
        ],
        created_at=utc_now(),
    )


def render_plan_markdown(plan: PlanArtifact, spec: FeatureSpec) -> str:
    lines = [
        f"# Implementation Plan: {spec.display_name}",
        "",
        f"- Run ID: `{plan.run_id}`",
        f"- Spec hash: `{plan.spec_hash}`",
        f"- Target module: `{plan.target_module}`",
        f"- Target function: `{plan.target_function}`",
        "",
        "## Technical Design Summary",
        "",
        plan.technical_design_summary,
        "",
        "## Implementation Tasks",
        "",
    ]
    for task in plan.implementation_tasks:
        ac = ", ".join(task.acceptance_criteria) if task.acceptance_criteria else "N/A"
        lines.append(f"- **{task.id} {task.title}**: {task.description} Acceptance criteria: {ac}.")

    lines.extend(["", "## Impacted Modules / Files", ""])
    lines.extend(f"- `{path}`" for path in plan.impacted_modules_files)
    lines.extend(["", "## Risk Considerations", ""])
    lines.extend(f"- {risk}" for risk in plan.risk_considerations)
    lines.extend(["", "## Test Strategy", ""])
    lines.extend(f"- {strategy}" for strategy in plan.test_strategy)
    lines.extend(["", "## Allowed Paths", ""])
    lines.extend(f"- `{path}`" for path in plan.allowed_paths)
    lines.append("")
    return "\n".join(lines)


def write_plan(run_dir: Path, plan: PlanArtifact, spec: FeatureSpec) -> None:
    from pipeline.audit import write_json

    write_json(run_dir / "plan.json", plan.to_json_data())
    (run_dir / "plan.md").write_text(render_plan_markdown(plan, spec), encoding="utf-8")


def _target_function(spec: FeatureSpec) -> str:
    searchable = " ".join(
        [
            spec.feature_objective,
            spec.user_story,
            " ".join(rule for rule in spec.business_rules),
        ]
    ).lower()
    if "discount" in searchable:
        return "calculate_discounted_price"
    return f"run_{spec.slug.replace('-', '_')}"

