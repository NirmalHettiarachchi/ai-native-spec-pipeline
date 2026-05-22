import hashlib
from pathlib import Path

import pytest

import pipeline.gates as gates
from pipeline.approval import create_approval
from pipeline.audit import initialize_run, utc_now, write_json
from pipeline.gates import validate_run
from pipeline.generator import implement_run
from pipeline.models import GateResult
from pipeline.planner import create_plan, write_plan
from pipeline.spec_parser import parse_feature_spec
from pipeline.workflow import run_pipeline


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


def test_policy_validation_reports_incomplete_manifest_and_contract_drift(
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

    broken_module = (
        "class DiscountCalculatorError(Exception):\n"
        "    pass\n\n"
        "def calculate_discounted_price() -> int:\n"
        "    return 1\n"
    )
    module_path = repo_root / "demo_app/src/demo_app/discount_calculator.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text(broken_module, encoding="utf-8")
    write_json(
        run_dir / "change_manifest.json",
        {
            "run_id": run_id,
            "provider": "openai-responses",
            "model": "gpt-4o",
            "generated_at": utc_now(),
            "plan_hash": "hash",
            "spec_hash": spec_hash,
            "allowed_paths": plan.allowed_paths,
            "summary": ["Generated an incomplete change set."],
            "files": [
                {
                    "path": "demo_app/src/demo_app/discount_calculator.py",
                    "purpose": "Generated implementation.",
                    "content_sha256": hashlib.sha256(
                        broken_module.encode("utf-8")
                    ).hexdigest(),
                    "acceptance_criteria": ["AC-001"],
                }
            ],
        },
    )

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

    policy = next(gate for gate in results.gates if gate.name == "policy")
    assert results.overall_status == "failed"
    assert policy.status == "failed"
    assert any("missing approved plan files" in detail for detail in policy.details)
    assert any("generated module is missing public symbols" in detail for detail in policy.details)


def test_resumable_workflow_does_not_stale_release_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_root = tmp_path / "audit"
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(audit_root))
    spec_path = Path("specs/examples/discount_calculator.yaml")
    spec = parse_feature_spec(spec_path)
    run_id, run_dir, spec_hash = initialize_run(spec, spec_path)
    plan = create_plan(spec, run_id, spec_hash)
    write_plan(run_dir, plan, spec)
    create_approval(run_id, "plan", "Reviewer")
    write_json(
        run_dir / "change_manifest.json",
        {
            "run_id": run_id,
            "provider": "local-template",
            "model": "deterministic-v1",
            "generated_at": utc_now(),
            "plan_hash": "hash",
            "spec_hash": spec_hash,
            "allowed_paths": plan.allowed_paths,
            "summary": [],
            "files": [],
        },
    )
    write_json(
        run_dir / "validation_results.json",
        {
            "run_id": run_id,
            "overall_status": "passed",
            "created_at": utc_now(),
            "gates": [],
        },
    )
    create_approval(run_id, "release", "Reviewer")

    def fail_validation(run_id: str) -> None:
        raise AssertionError("validation should not run after release approval")

    monkeypatch.setattr("pipeline.workflow.validate_run", fail_validation)
    monkeypatch.setattr(
        "pipeline.workflow.create_deployment_evidence",
        lambda run_id: run_dir / "deployment_evidence.md",
    )

    messages = run_pipeline(spec_path, run_id)

    assert any("deployment evidence" in message for message in messages)
