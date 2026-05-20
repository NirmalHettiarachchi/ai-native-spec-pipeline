from pathlib import Path

from fastapi.testclient import TestClient

from pipeline.audit import write_json
from pipeline.models import GateResult, ValidationResults
from pipeline_web.app import app


def _create_run(client: TestClient) -> str:
    response = client.post(
        "/runs",
        data={"spec_file": "specs/examples/discount_calculator.yaml"},
    )
    assert response.status_code == 303
    return response.headers["location"].split("/runs/")[1].split("?")[0]


def test_web_create_run_and_blocked_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    client = TestClient(app, follow_redirects=False)

    run_id = _create_run(client)

    detail = client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    assert "Plan approval required" in detail.text

    blocked = client.post(f"/runs/{run_id}/approve-release", data={"approver": "Reviewer"})
    assert blocked.status_code == 303
    assert "cannot+approve+release" in blocked.headers["location"]


def test_web_spec_path_validation_renders_inline_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    client = TestClient(app)

    empty_response = client.post("/runs", data={"spec_file": ""})
    assert empty_response.status_code == 200
    assert "Enter a spec path before creating a run." in empty_response.text
    assert 'aria-invalid="true"' in empty_response.text

    extension_response = client.post("/runs", data={"spec_file": "feature.txt"})
    assert extension_response.status_code == 200
    assert "Spec path must end with .yaml, .yml, .json, .md, or .markdown." in (
        extension_response.text
    )


def test_web_approver_validation_renders_inline_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    create_client = TestClient(app, follow_redirects=False)
    client = TestClient(app)
    run_id = _create_run(create_client)

    empty_response = client.post(f"/runs/{run_id}/approve-plan", data={"approver": ""})
    assert empty_response.status_code == 200
    assert "Enter the approver name." in empty_response.text
    assert "plan_approver_error" in empty_response.text

    short_response = client.post(f"/runs/{run_id}/approve-plan", data={"approver": "A"})
    assert "Approver name must be at least 2 characters." in short_response.text

    release_response = client.post(
        f"/runs/{run_id}/approve-release",
        data={"approver": "A"},
    )
    assert "Approver name must be at least 2 characters." in release_response.text
    assert "release_approver_error" in release_response.text


def test_web_pages_include_mobile_and_loading_affordances(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    client = TestClient(app, follow_redirects=False)
    run_id = _create_run(client)

    runs_page = client.get("/")
    assert "run-card-list" in runs_page.text
    assert "loading-overlay" in runs_page.text
    assert 'data-loading-label="Creating run..."' in runs_page.text

    detail = client.get(f"/runs/{run_id}")
    assert "workflow-stepper" in detail.text
    assert "action-card" in detail.text
    assert "Plan approval is required first." in detail.text
    assert 'data-loading-label="Validating..."' in detail.text

    css = Path("pipeline_web/static/app.css").read_text(encoding="utf-8")
    assert "@media (max-width: 700px)" in css
    assert ".run-card-list" in css
    assert ".action-grid" in css


def test_web_routes_can_execute_governed_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    client = TestClient(app, follow_redirects=False)
    run_id = _create_run(client)

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
