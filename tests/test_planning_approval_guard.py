from pathlib import Path

import pytest

from pipeline.approval import create_approval, require_approval
from pipeline.audit import initialize_run
from pipeline.change_guard import validate_generated_paths
from pipeline.errors import PipelineError
from pipeline.models import GeneratedFile, PlanArtifact
from pipeline.planner import create_plan, write_plan
from pipeline.spec_parser import parse_feature_spec


def test_plan_contains_required_assessment_fields(tmp_path: Path) -> None:
    spec = parse_feature_spec(Path("specs/examples/discount_calculator.yaml"))
    run_id, _, spec_hash = initialize_run(
        spec,
        Path("specs/examples/discount_calculator.yaml"),
        tmp_path,
    )
    plan = create_plan(spec, run_id, spec_hash)

    assert plan.technical_design_summary
    assert plan.implementation_tasks
    assert plan.impacted_modules_files
    assert plan.risk_considerations
    assert plan.test_strategy


def test_plan_approval_blocks_then_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    spec = parse_feature_spec(Path("specs/examples/discount_calculator.yaml"))
    run_id, run_dir, spec_hash = initialize_run(
        spec,
        Path("specs/examples/discount_calculator.yaml"),
    )
    plan = create_plan(spec, run_id, spec_hash)
    write_plan(run_dir, plan, spec)

    with pytest.raises(PipelineError, match="approval is required"):
        require_approval(run_id, "plan")

    approval = create_approval(run_id, "plan", "Reviewer")

    assert approval.stage == "plan"
    assert require_approval(run_id, "plan").approver == "Reviewer"


def test_change_guard_rejects_files_outside_approved_paths(tmp_path: Path) -> None:
    spec = parse_feature_spec(Path("specs/examples/discount_calculator.yaml"))
    plan = create_plan(spec, "run-1", "hash")
    generated_file = GeneratedFile(
        path="outside/generated.py",
        purpose="escape attempt",
        content="print('bad')\n",
    )

    with pytest.raises(PipelineError, match="outside approved paths"):
        validate_generated_paths([generated_file], PlanArtifact.model_validate(plan), tmp_path)


def test_change_guard_rejects_incomplete_generated_plan(tmp_path: Path) -> None:
    spec = parse_feature_spec(Path("specs/examples/discount_calculator.yaml"))
    plan = create_plan(spec, "run-1", "hash")
    generated_file = GeneratedFile(
        path="demo_app/src/demo_app/discount_calculator.py",
        purpose="partial implementation",
        content="def calculate_discounted_price():\n    return 1\n",
    )

    with pytest.raises(PipelineError, match="missing approved plan files"):
        validate_generated_paths([generated_file], plan, tmp_path)
