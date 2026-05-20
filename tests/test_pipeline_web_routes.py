from pathlib import Path

from fastapi.testclient import TestClient

from pipeline.audit import write_json
from pipeline.models import GateResult, ValidationResults
from pipeline_web.app import app


def test_web_create_run_and_blocked_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    client = TestClient(app, follow_redirects=False)

    response = client.post(
        "/runs",
        data={"spec_file": "specs/examples/discount_calculator.yaml"},
    )
    assert response.status_code == 303
    location = response.headers["location"]
    run_id = location.split("/runs/")[1].split("?")[0]

    detail = client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    assert "Plan approval required" in detail.text

    blocked = client.post(f"/runs/{run_id}/approve-release", data={"approver": "Reviewer"})
    assert blocked.status_code == 303
    assert "cannot+approve+release" in blocked.headers["location"]


def test_web_routes_can_execute_governed_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    client = TestClient(app, follow_redirects=False)
    run_response = client.post(
        "/runs",
        data={"spec_file": "specs/examples/discount_calculator.yaml"},
    )
    run_id = run_response.headers["location"].split("/runs/")[1].split("?")[0]

    approve_response = client.post(
        f"/runs/{run_id}/approve-plan",
        data={"approver": "Reviewer"},
    )
    assert approve_response.status_code == 303

    def fake_implement(run_id: str) -> None:
        write_json(
            tmp_path / run_id / "change_manifest.json",
            {
                "run_id": run_id,
                "provider": "local-template",
                "model": "deterministic-v1",
                "generated_at": "2026-05-20T00:00:00Z",
                "plan_hash": "hash",
                "spec_hash": "hash",
                "allowed_paths": ["demo_app/src/demo_app/", "demo_app/tests/"],
                "summary": ["Generated through UI."],
                "files": [],
            },
        )

    def fake_validate(run_id: str) -> ValidationResults:
        results = ValidationResults(
            run_id=run_id,
            overall_status="passed",
            created_at="2026-05-20T00:00:00Z",
            gates=[
                GateResult(
                    name="policy",
                    status="passed",
                    started_at="2026-05-20T00:00:00Z",
                    finished_at="2026-05-20T00:00:00Z",
                )
            ],
        )
        write_json(tmp_path / run_id / "validation_results.json", results.to_json_data())
        return results

    def fake_evidence(run_id: str) -> Path:
        path = tmp_path / run_id / "deployment_evidence.md"
        path.write_text("# Evidence\n", encoding="utf-8")
        return path

    monkeypatch.setattr("pipeline_web.app.implement_run", fake_implement)
    monkeypatch.setattr("pipeline_web.app.validate_run", fake_validate)
    monkeypatch.setattr("pipeline_web.app.create_deployment_evidence", fake_evidence)

    assert client.post(f"/runs/{run_id}/implement").status_code == 303
    assert client.post(f"/runs/{run_id}/validate").status_code == 303
    assert client.post(
        f"/runs/{run_id}/approve-release",
        data={"approver": "Reviewer"},
    ).status_code == 303
    assert client.post(f"/runs/{run_id}/evidence").status_code == 303

    detail = client.get(f"/runs/{run_id}")
    assert "Evidence complete" in detail.text
