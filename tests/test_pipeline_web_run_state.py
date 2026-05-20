from pathlib import Path

import pytest

from pipeline.approval import create_approval
from pipeline.audit import initialize_run, write_json
from pipeline.errors import PipelineError
from pipeline.planner import create_plan, write_plan
from pipeline.spec_parser import parse_feature_spec
from pipeline_web.run_state import (
    get_run_state,
    list_runs_page,
    read_allowed_artefact,
    read_run_detail,
)


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


def test_run_pagination_returns_newest_page(
    tmp_path: Path,
) -> None:
    for index in range(12):
        run_id = f"202605201200{index:02d}-feature-{index}"
        run_dir = tmp_path / run_id
        write_json(
            run_dir / "run_metadata.json",
            {
                "run_id": run_id,
                "created_at": f"2026-05-20T12:00:{index:02d}Z",
                "spec_file": "specs/examples/discount_calculator.yaml",
                "spec_hash": "hash",
                "spec_slug": f"feature-{index}",
            },
        )

    page_one = list_runs_page(1, 10, audit_root=tmp_path)
    page_two = list_runs_page(2, 10, audit_root=tmp_path)

    assert page_one.total == 12
    assert page_one.total_pages == 2
    assert len(page_one.items) == 10
    assert page_one.items[0].run_id.endswith("feature-11")
    assert len(page_two.items) == 2
    assert page_two.items[0].run_id.endswith("feature-1")


def test_run_pagination_clamps_invalid_values(tmp_path: Path) -> None:
    page = list_runs_page("bad", "999", audit_root=tmp_path)

    assert page.page == 1
    assert page.page_size == 50
    assert page.total_pages == 1


def test_run_detail_includes_assessment_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = _create_planned_run(tmp_path, monkeypatch)

    detail = read_run_detail(run_id)

    labels = [item.label for item in detail["coverage"]]
    assert "Spec Intake" in labels
    assert "Planning Layer" in labels
    assert "Quality Gates" in labels
