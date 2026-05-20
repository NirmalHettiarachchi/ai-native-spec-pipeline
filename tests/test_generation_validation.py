from pathlib import Path

import pytest

import pipeline.gates as gates
from pipeline.approval import create_approval
from pipeline.audit import initialize_run, utc_now
from pipeline.gates import validate_run
from pipeline.generator import implement_run
from pipeline.models import GateResult
from pipeline.planner import create_plan, write_plan
from pipeline.spec_parser import parse_feature_spec


@pytest.mark.integration
def test_implementation_and_policy_validation_trace_acceptance_criteria(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_root = tmp_path / "audit"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(audit_root))

    spec = parse_feature_spec(Path("specs/examples/discount_calculator.yaml"))
    run_id, run_dir, spec_hash = initialize_run(
        spec,
        Path("specs/examples/discount_calculator.yaml"),
    )
    plan = create_plan(spec, run_id, spec_hash)
    write_plan(run_dir, plan, spec)
    create_approval(run_id, "plan", "Reviewer")

    manifest = implement_run(run_id, repo_root=repo_root)

    assert {entry.path for entry in manifest.files} == {
        "demo_app/src/demo_app/discount_calculator.py",
        "demo_app/src/demo_app/__init__.py",
        "demo_app/tests/test_discount_calculator.py",
        "demo_app/tests/test_discount_calculator_acceptance.py",
    }

    def fake_run_command(name: str, command: list[str], repo_root: Path) -> GateResult:
        return GateResult(
            name=name,
            status="passed",
            command=command,
            return_code=0,
            started_at=utc_now(),
            finished_at=utc_now(),
        )

    monkeypatch.setattr(gates, "_run_command", fake_run_command)
    results = validate_run(run_id, repo_root=repo_root)

    assert results.overall_status == "passed"
    assert (run_dir / "validation_results.json").exists()

