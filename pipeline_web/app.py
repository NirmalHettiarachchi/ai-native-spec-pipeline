"""FastAPI application for the local governance dashboard."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData

from pipeline.approval import create_approval
from pipeline.audit import initialize_run
from pipeline.config import get_runtime_config
from pipeline.errors import PipelineError
from pipeline.evidence import create_deployment_evidence
from pipeline.gates import validate_run
from pipeline.generator import implement_run
from pipeline.planner import create_plan, write_plan
from pipeline.repair import repair_validation
from pipeline.spec_parser import parse_feature_spec
from pipeline_web.run_state import list_runs_page, read_allowed_artefact, read_run_detail
from pipeline_web.spec_catalog import (
    DEFAULT_SPEC,
    list_spec_files,
    resolve_spec_path,
    save_uploaded_spec,
)

BASE_DIR = Path(__file__).resolve().parent
APPROVER_PATTERN = re.compile(r"^[A-Za-z0-9 ._'\-]+$")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Spec-Driven Pipeline Dashboard")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def runs(
    request: Request,
    page: str = "1",
    page_size: str = "10",
    message: str = "",
    error: str = "",
    field: str = "",
    action: str = "",
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "runs.html",
        {
            "run_page": list_runs_page(page, page_size),
            "spec_options": list_spec_files(),
            "message": message,
            "error": error,
            "field": field,
            "action": action,
            "default_spec": DEFAULT_SPEC,
            "runtime_config": get_runtime_config().to_public_dict(),
        },
    )


@app.post("/runs")
async def create_run(request: Request) -> RedirectResponse:
    form = await request.form()
    try:
        spec_path = await _resolve_submitted_spec(form)
        spec = parse_feature_spec(spec_path)
        run_id, run_dir, spec_hash = initialize_run(spec, spec_path)
        plan = create_plan(spec, run_id, spec_hash)
        write_plan(run_dir, plan, spec)
    except PipelineError as exc:
        return _redirect(
            "/",
            error=str(exc),
            field="spec_file",
            action="create-run",
            fragment="create-run",
        )
    return _redirect(f"/runs/{run_id}", message="Run created and plan generated.")


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(
    request: Request,
    run_id: str,
    message: str = "",
    error: str = "",
    field: str = "",
    action: str = "",
) -> HTMLResponse:
    try:
        detail = read_run_detail(run_id)
    except PipelineError as exc:
        return templates.TemplateResponse(
            request,
            "runs.html",
            {
                "run_page": list_runs_page(),
                "spec_options": list_spec_files(),
                "message": "",
                "error": str(exc),
                "field": "",
                "action": "",
                "default_spec": DEFAULT_SPEC,
                "runtime_config": get_runtime_config().to_public_dict(),
            },
            status_code=404,
        )
    if (
        error
        and action in {"validate", "repair-validation"}
        and detail["state"].validation_status == "passed"
    ):
        error = ""
        message = message or "Validation passed."
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "detail": detail,
            "message": message,
            "error": error,
            "field": field,
            "action": action,
            "runtime_config": get_runtime_config().to_public_dict(),
        },
    )


@app.get("/api/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "spec-pipeline"}


@app.get("/api/config")
async def api_config() -> dict[str, str | bool]:
    return get_runtime_config().to_public_dict()


@app.get("/api/runs")
async def api_runs(page: str = "1", page_size: str = "10") -> dict[str, Any]:
    run_page = list_runs_page(page, page_size)
    return {
        "items": [_serialize_dataclass(run) for run in run_page.items],
        "total": run_page.total,
        "page": run_page.page,
        "page_size": run_page.page_size,
        "total_pages": run_page.total_pages,
    }


@app.get("/api/runs/{run_id}")
async def api_run_detail(run_id: str) -> dict[str, Any]:
    try:
        detail = read_run_detail(run_id)
    except PipelineError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "state": _serialize_dataclass(detail["state"]),
        "spec": detail["spec"],
        "plan": detail["plan"],
        "manifest": detail["manifest"],
        "validation": detail["validation"],
        "plan_approval": detail["plan_approval"],
        "release_approval": detail["release_approval"],
        "ai_interactions": detail["ai_interactions"],
        "artefacts": detail["artefacts"],
        "coverage": [_serialize_dataclass(item) for item in detail["coverage"]],
    }


@app.post("/runs/{run_id}/approve-plan")
async def approve_plan(request: Request, run_id: str) -> RedirectResponse:
    form = await _read_form(request)
    approver_error = _validate_approver(form.get("approver", ""))
    if approver_error:
        return _redirect(
            f"/runs/{run_id}",
            error=approver_error,
            field="approver",
            action="approve-plan",
            fragment="actions",
        )
    return _run_action(
        run_id,
        lambda: create_approval(run_id, "plan", form.get("approver", "")),
        "Plan approval recorded.",
        "approve-plan",
    )


@app.post("/runs/{run_id}/implement")
async def implement(run_id: str) -> RedirectResponse:
    return _run_action(
        run_id,
        lambda: implement_run(run_id),
        "Implementation generated.",
        "implement",
    )


@app.post("/runs/{run_id}/validate")
async def validate(run_id: str) -> RedirectResponse:
    def action() -> None:
        results = validate_run(run_id)
        if results.overall_status != "passed":
            raise PipelineError("Validation failed. Review gate output before release approval.")

    return _run_action(run_id, action, "Validation passed.", "validate")


@app.post("/runs/{run_id}/repair-validation")
async def repair_validation_action(run_id: str) -> RedirectResponse:
    def action() -> None:
        repair_validation(run_id)
        results = validate_run(run_id)
        if results.overall_status != "passed":
            raise PipelineError("Repair completed, but validation still fails. Review gate output.")

    return _run_action(
        run_id,
        action,
        "Validation fixes applied and gates passed.",
        "repair-validation",
    )


@app.post("/runs/{run_id}/approve-release")
async def approve_release(request: Request, run_id: str) -> RedirectResponse:
    form = await _read_form(request)
    approver_error = _validate_approver(form.get("approver", ""))
    if approver_error:
        return _redirect(
            f"/runs/{run_id}",
            error=approver_error,
            field="approver",
            action="approve-release",
            fragment="actions",
        )
    return _run_action(
        run_id,
        lambda: create_approval(run_id, "release", form.get("approver", "")),
        "Release approval recorded.",
        "approve-release",
    )


@app.post("/runs/{run_id}/evidence")
async def evidence(run_id: str) -> RedirectResponse:
    return _run_action(
        run_id,
        lambda: create_deployment_evidence(run_id),
        "Evidence generated.",
        "evidence",
    )


@app.get("/runs/{run_id}/artefacts/{name}", response_class=HTMLResponse)
async def artefact(
    request: Request,
    run_id: str,
    name: str,
    message: str = "",
    error: str = "",
) -> HTMLResponse:
    try:
        content = read_allowed_artefact(run_id, name)
    except PipelineError as exc:
        return templates.TemplateResponse(
            request,
            "artefact.html",
            {
                "run_id": run_id,
                "name": name,
                "content": "",
                "message": message,
                "error": str(exc),
            },
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "artefact.html",
        {
            "run_id": run_id,
            "name": name,
            "content": content,
            "message": message,
            "error": error,
        },
    )


async def _read_form(request: Request) -> dict[str, str]:
    form = await request.form()
    values: dict[str, str] = {}
    for key, value in form.multi_items():
        if hasattr(value, "filename"):
            continue
        values[key] = str(value)
    return values


async def _resolve_submitted_spec(form: FormData) -> Path:
    source = str(form.get("spec_source") or "repository").strip()
    selected = str(form.get("spec_file") or "").strip()
    upload: Any = form.get("spec_upload")
    upload_name = str(getattr(upload, "filename", "") or "").strip()
    if source == "upload":
        if not upload_name:
            raise PipelineError("Choose a spec file to upload.")
        content = await upload.read()
        return save_uploaded_spec(upload_name, content)
    if source == "repository":
        return resolve_spec_path(selected)
    raise PipelineError("Choose repository spec or upload spec.")


def _run_action(
    run_id: str,
    action: Callable[[], object],
    success: str,
    action_name: str,
) -> RedirectResponse:
    try:
        action()
    except PipelineError as exc:
        return _redirect(
            f"/runs/{run_id}",
            error=str(exc),
            action=action_name,
            fragment="actions",
        )
    return _redirect(
        f"/runs/{run_id}",
        message=success,
        action=action_name,
        fragment="actions",
    )


def _redirect(
    path: str,
    *,
    message: str = "",
    error: str = "",
    field: str = "",
    action: str = "",
    fragment: str = "",
) -> RedirectResponse:
    params: dict[str, str] = {}
    if message:
        params["message"] = message
    if error:
        params["error"] = error
    if field:
        params["field"] = field
    if action:
        params["action"] = action
    suffix = f"?{urlencode(params)}" if params else ""
    anchor = f"#{fragment}" if fragment else ""
    return RedirectResponse(f"{path}{suffix}{anchor}", status_code=303)


def _validate_approver(approver: str) -> str:
    stripped = approver.strip()
    if not stripped:
        return "Enter approver name."
    if len(stripped) < 2:
        return "Use at least 2 characters."
    if len(stripped) > 60:
        return "Use 60 characters or fewer."
    if not APPROVER_PATTERN.fullmatch(stripped):
        return "Use letters, numbers, spaces, . _ - or apostrophe."
    return ""


def _serialize_dataclass(value: Any) -> dict[str, Any]:
    serialized = asdict(value)
    if "run_dir" in serialized:
        serialized["run_dir"] = str(serialized["run_dir"])
    return serialized
