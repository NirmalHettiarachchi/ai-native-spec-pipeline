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
    assert blocked.headers["location"].endswith("#actions")


def test_web_spec_path_validation_renders_inline_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    client = TestClient(app)

    empty_response = client.post("/runs", data={"spec_file": ""})
    assert empty_response.status_code == 200
    assert str(empty_response.url).endswith("#create-run")
    assert "Choose a spec before creating a run." in empty_response.text
    assert 'role="alert"' not in empty_response.text
    assert "spec_file_error" in empty_response.text
    assert 'aria-invalid="true"' in empty_response.text
    assert "is-invalid" in empty_response.text
    assert "invalid-feedback" in empty_response.text

    extension_response = client.post("/runs", data={"spec_file": "feature.txt"})
    assert extension_response.status_code == 200
    assert "Spec must be .yaml, .yml, .json, .md, or .markdown." in extension_response.text
    assert 'role="alert"' not in extension_response.text

    missing_response = client.post("/runs", data={"spec_file": "missing.yaml"})
    assert missing_response.status_code == 200
    assert "spec file does not exist" in missing_response.text
    assert "spec_file_error" in missing_response.text
    assert 'role="alert"' not in missing_response.text


def test_web_create_run_from_uploaded_spec(
    tmp_path: Path,
    monkeypatch,
) -> None:
    spec_root = tmp_path / "specs"
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path / "audit"))
    monkeypatch.setenv("PIPELINE_SPEC_ROOT", str(spec_root))
    client = TestClient(app, follow_redirects=False)
    content = Path("specs/examples/discount_calculator.yaml").read_bytes()

    response = client.post(
        "/runs",
        data={"spec_source": "upload", "spec_file": ""},
        files={"spec_upload": ("uploaded.yaml", content, "application/x-yaml")},
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/runs/")
    assert list((spec_root / "uploads").glob("*.yaml"))


def test_web_bad_upload_renders_inline_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path / "audit"))
    monkeypatch.setenv("PIPELINE_SPEC_ROOT", str(tmp_path / "specs"))
    client = TestClient(app)

    response = client.post(
        "/runs",
        data={"spec_source": "upload", "spec_file": ""},
        files={"spec_upload": ("bad.txt", b"not a spec", "text/plain")},
    )

    assert response.status_code == 200
    assert "Uploaded spec must be .yaml, .yml, .json, .md, or .markdown." in response.text
    assert "spec_file_error" in response.text
    assert 'role="alert"' not in response.text


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
    assert str(empty_response.url).endswith("#actions")
    assert "Enter approver name." in empty_response.text
    assert "plan_approver_error" in empty_response.text
    assert "invalid-feedback" in empty_response.text
    assert 'role="alert"' not in empty_response.text

    short_response = client.post(f"/runs/{run_id}/approve-plan", data={"approver": "A"})
    assert "Use at least 2 characters." in short_response.text

    long_response = client.post(f"/runs/{run_id}/approve-plan", data={"approver": "A" * 61})
    assert "Use 60 characters or fewer." in long_response.text

    invalid_response = client.post(f"/runs/{run_id}/approve-plan", data={"approver": "A@B"})
    assert "Use letters, numbers, spaces, . _ - or apostrophe." in invalid_response.text

    release_response = client.post(
        f"/runs/{run_id}/approve-release",
        data={"approver": "A"},
    )
    assert "Use at least 2 characters." in release_response.text
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
    assert "table-responsive" in runs_page.text
    assert "loading-overlay" in runs_page.text
    assert "spinner-border" in runs_page.text
    assert 'data-loading-label="Creating run..."' in runs_page.text
    assert 'id="create-run"' in runs_page.text
    assert "create-run-control" in runs_page.text
    assert 'enctype="multipart/form-data"' in runs_page.text
    assert "provider-status" in runs_page.text
    assert "AI mode:" in runs_page.text
    assert "Provider:" in runs_page.text
    assert 'data-spec-source-form' in runs_page.text
    assert 'id="spec_source_repository"' in runs_page.text
    assert 'id="spec_source_upload"' in runs_page.text
    assert 'data-spec-source-panel="repository"' in runs_page.text
    assert 'data-spec-source-panel="upload"' in runs_page.text
    assert 'hidden' in runs_page.text
    assert 'id="spec_upload"' in runs_page.text
    assert "<select" in runs_page.text
    assert "specs/examples/discount_calculator.yaml" in runs_page.text

    detail = client.get(f"/runs/{run_id}")
    assert 'id="actions"' in detail.text
    assert 'id="validation"' in detail.text
    assert 'id="artefacts"' in detail.text
    assert "workflow-stepper" in detail.text
    assert "action-card" in detail.text
    assert 'id="coverage"' in detail.text
    assert "Spec Intake" in detail.text
    assert "Human Approval Workflow" in detail.text
    assert "row-cols-md-2 row-cols-xl-3" in detail.text
    assert "Fix Validation" in detail.text
    assert "Plan approval required." in detail.text
    assert 'data-lucide="shield-check"' in detail.text
    assert 'data-lucide="wrench"' in detail.text
    assert 'data-loading-label="Validating..."' in detail.text
    assert 'data-loading-label="Fixing validation..."' in detail.text
    assert 'maxlength="60"' in detail.text
    assert 'pattern="[A-Za-z0-9 ._\'\\-]+"' in detail.text

    layout = Path("pipeline_web/templates/layout.html").read_text(encoding="utf-8")
    assert "bootstrap@5.3.3" in layout
    assert "lucide" in layout
    assert "alert-success" not in layout
    assert "alert-danger" not in layout
    css = Path("pipeline_web/static/app.css").read_text(encoding="utf-8")
    assert "@media (max-width: 700px)" in css
    assert ".artefact" in css
    assert ".log-output" in css
    assert ".create-run-control" in css
    assert "repeat(5" not in css

    js = Path("pipeline_web/static/app.js").read_text(encoding="utf-8")
    assert "function setLoading" in js
    assert "originalHtml" in js
    assert "createIcons" in js
    assert "syncSpecSource" in js
    assert "pageshow" in js
    assert "visibilitychange" in js
    assert "setTimeout" in js


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
    assert approve_response.headers["location"].endswith("#actions")

    approval_detail = client.get(approve_response.headers["location"])
    assert "Plan approval recorded." in approval_detail.text

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

    def fake_repair(run_id: str) -> None:
        write_json(
            tmp_path / run_id / "validation_repair.json",
            {
                "run_id": run_id,
                "created_at": "2026-05-20T00:00:00Z",
                "status": "passed",
                "commands": [],
                "files": [],
            },
        )

    def fake_evidence(run_id: str) -> Path:
        path = tmp_path / run_id / "deployment_evidence.md"
        path.write_text("# Evidence\n", encoding="utf-8")
        return path

    monkeypatch.setattr("pipeline_web.app.implement_run", fake_implement)
    monkeypatch.setattr("pipeline_web.app.repair_validation", fake_repair)
    monkeypatch.setattr("pipeline_web.app.validate_run", fake_validate)
    monkeypatch.setattr("pipeline_web.app.create_deployment_evidence", fake_evidence)

    assert client.post(f"/runs/{run_id}/implement").status_code == 303
    assert client.post(f"/runs/{run_id}/validate").status_code == 303
    stale_error_detail = client.get(
        f"/runs/{run_id}?error=old+repair+error&action=repair-validation#actions"
    )
    assert "old repair error" not in stale_error_detail.text
    assert "Validation passed." in stale_error_detail.text
    assert client.post(f"/runs/{run_id}/repair-validation").status_code == 303
    assert client.post(
        f"/runs/{run_id}/approve-release",
        data={"approver": "Reviewer"},
    ).status_code == 303
    assert client.post(f"/runs/{run_id}/evidence").status_code == 303

    detail = client.get(f"/runs/{run_id}")
    assert "Evidence complete" in detail.text


def test_web_run_list_renders_pagination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    client = TestClient(app, follow_redirects=False)

    for _ in range(11):
        _create_run(client)

    response = client.get("/")

    assert "Showing 1-10 of 11" in response.text
    assert 'aria-label="Run pages"' in response.text
    assert "page=2" in response.text


def test_web_api_endpoints_expose_status_and_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path))
    client = TestClient(app, follow_redirects=False)
    run_id = _create_run(client)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    config = client.get("/api/config")
    assert config.status_code == 200
    assert "openai_api_key_configured" in config.json()
    assert "OPENAI_API_KEY" not in config.text

    runs = client.get("/api/runs")
    assert runs.status_code == 200
    assert runs.json()["total"] == 1
    assert runs.json()["items"][0]["run_id"] == run_id

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["state"]["run_id"] == run_id
    assert "coverage" in detail.json()

    missing = client.get("/api/runs/missing")
    assert missing.status_code == 404


def test_web_editor_edits_manifest_file_and_refreshes_hash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(tmp_path / "audit"))
    run_id = "20260522080000-editor-test"
    run_dir = tmp_path / "audit" / run_id
    run_dir.mkdir(parents=True)
    target = tmp_path / "demo_app/src/demo_app/sample.py"
    target.parent.mkdir(parents=True)
    other = tmp_path / "demo_app/src/demo_app/other.py"
    original = "VALUE = 1\n"
    other.write_text("OTHER = 0\n", encoding="utf-8")
    target.write_text(original, encoding="utf-8")
    write_json(
        run_dir / "change_manifest.json",
        {
            "run_id": run_id,
            "provider": "local-template",
            "model": "deterministic-v1",
            "generated_at": "2026-05-22T00:00:00Z",
            "plan_hash": "hash",
            "spec_hash": "hash",
            "allowed_paths": ["demo_app/src/demo_app/"],
            "summary": ["Generated sample file."],
            "files": [
                {
                    "path": "demo_app/src/demo_app/other.py",
                    "purpose": "Other generated file.",
                    "content_sha256": "other",
                    "acceptance_criteria": [],
                },
                {
                    "path": "demo_app/src/demo_app/sample.py",
                    "purpose": "Editable generated file.",
                    "content_sha256": "old",
                    "acceptance_criteria": ["AC-001"],
                }
            ],
        },
    )
    write_json(
        run_dir / "validation_results.json",
        {
            "run_id": run_id,
            "overall_status": "failed",
            "created_at": "2026-05-22T00:00:00Z",
            "gates": [
                {
                    "name": "pytest",
                    "status": "failed",
                    "command": [],
                    "return_code": 1,
                    "stdout": "demo_app\\src\\demo_app\\sample.py: sample failure",
                    "stderr": "",
                    "details": [],
                    "started_at": "2026-05-22T00:00:00Z",
                    "finished_at": "2026-05-22T00:00:00Z",
                }
            ],
        },
    )
    client = TestClient(app, follow_redirects=False)

    editor = client.get(f"/runs/{run_id}/editor?gate=pytest")
    assert editor.status_code == 200
    assert "sample failure" in editor.text
    assert "<h1 class=\"h4 mb-1 text-break\">demo_app/src/demo_app/sample.py</h1>" in (
        editor.text
    )
    assert "VALUE = 1" in editor.text

    response = client.post(
        f"/runs/{run_id}/editor",
        data={
            "file_path": "demo_app/src/demo_app/sample.py",
            "gate": "pytest",
            "content": "VALUE = 2\n",
        },
    )

    assert response.status_code == 303
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    manifest = (run_dir / "change_manifest.json").read_text(encoding="utf-8")
    assert "old" not in manifest
