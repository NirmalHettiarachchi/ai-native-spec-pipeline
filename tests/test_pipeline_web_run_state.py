from pathlib import Path

import pytest

from pipeline.approval import create_approval
from pipeline.audit import initialize_run, write_json
from pipeline.errors import PipelineError
from pipeline.planner import create_plan, write_plan
from pipeline.spec_parser import parse_feature_spec
from pipeline_web.run_state import get_run_state, read_allowed_artefact


def _create_planned_run(audit_root: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(audit_root))
    spec_path = Path("specs/examples/discount_calculator.yaml")
    spec = parse_feature_spec(spec_path)
    run_id, run_dir, spec_hash = initialize_run(spec, spec_path)
    plan = create_plan(spec, run_id, spec_hash)
    write_plan(run_dir, plan, spec)
    return run_id


def test_run_state_tracks_governance_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = _create_planned_run(tmp_path, monkeypatch)
    run_dir = tmp_path / run_id

    state = get_run_state(run_id)
    assert state.stage == "Plan ready"
    assert state.next_action == "Plan approval required"

    create_approval(run_id, "plan", "Reviewer")
    state = get_run_state(run_id)
    assert state.stage == "Plan approved"

    write_json(
        run_dir / "change_manifest.json",
        {
            "run_id": run_id,
            "provider": "local-template",
            "model": "deterministic-v1",
            "generated_at": "2026-05-20T00:00:00Z",
            "plan_hash": "hash",
            "spec_hash": "hash",
            "allowed_paths": ["demo_app/src/demo_app/", "demo_app/tests/"],
            "summary": [],
            "files": [],
        },
    )
    state = get_run_state(run_id)
    assert state.stage == "Implementation generated"

    write_json(
        run_dir / "validation_results.json",
        {
            "run_id": run_id,
            "overall_status": "passed",
            "created_at": "2026-05-20T00:00:00Z",
            "gates": [],
        },
    )
    state = get_run_state(run_id)
    assert state.stage == "Validation passed"

    create_approval(run_id, "release", "Reviewer")
    state = get_run_state(run_id)
    assert state.stage == "Release approved"

    (run_dir / "deployment_evidence.md").write_text("# Evidence\n", encoding="utf-8")
    state = get_run_state(run_id)
    assert state.stage == "Evidence complete"


def test_artefact_allowlist_rejects_unknown_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = _create_planned_run(tmp_path, monkeypatch)

    assert "Implementation Plan" in read_allowed_artefact(run_id, "plan.md")
    with pytest.raises(PipelineError, match="not allowed"):
        read_allowed_artefact(run_id, "../README.md")

