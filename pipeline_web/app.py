"""FastAPI application for the local governance dashboard."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pipeline.approval import create_approval
from pipeline.audit import initialize_run
from pipeline.errors import PipelineError
from pipeline.evidence import create_deployment_evidence
from pipeline.gates import validate_run
from pipeline.generator import implement_run
from pipeline.planner import create_plan, write_plan
from pipeline.spec_parser import parse_feature_spec
from pipeline_web.run_state import list_runs, read_allowed_artefact, read_run_detail

BASE_DIR = Path(__file__).resolve().parent
SPEC_SUFFIXES = {".yaml", ".yml", ".json", ".md", ".markdown"}
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Spec-Driven Pipeline Dashboard")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def runs(
    request: Request,
    message: str = "",
    error: str = "",
    field: str = "",
    action: str = "",
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "runs.html",
        {
            "runs": list_runs(),
            "message": message,
            "error": error,
            "field": field,
            "action": action,
            "default_spec": "specs/examples/discount_calculator.yaml",
        },
    )


@app.post("/runs")
async def create_run(request: Request) -> RedirectResponse:
    form = await _read_form(request)
    spec_path_text = form.get("spec_file", "").strip()
    validation_error = _validate_spec_path(spec_path_text)
    if validation_error:
        return _redirect(
            "/",
            error=validation_error,
            field="spec_file",
            action="create-run",
            fragment="create-run",
        )

    spec_path = Path(spec_path_text)
    try:
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
                "runs": list_runs(),
                "message": "",
                "error": str(exc),
                "field": "",
                "action": "",
                "default_spec": "specs/examples/discount_calculator.yaml",
            },
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {"detail": detail, "message": message, "error": error, "field": field, "action": action},
    )


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
    body = (await request.body()).decode("utf-8")
    return {key: values[-1] for key, values in parse_qs(body, keep_blank_values=True).items()}


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


def _validate_spec_path(spec_path: str) -> str:
    if not spec_path:
        return "Enter a spec path before creating a run."
    if Path(spec_path).suffix.lower() not in SPEC_SUFFIXES:
        return "Spec path must end with .yaml, .yml, .json, .md, or .markdown."
    return ""


def _validate_approver(approver: str) -> str:
    stripped = approver.strip()
    if not stripped:
        return "Enter the approver name."
    if len(stripped) < 2:
        return "Approver name must be at least 2 characters."
    return ""
