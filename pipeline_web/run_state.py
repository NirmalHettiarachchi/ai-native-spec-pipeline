"""Read-only run state derived from audit artefacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.audit import get_audit_root, read_json
from pipeline.errors import PipelineError

ALLOWED_ARTEFACTS = {
    "spec.normalized.json",
    "run_metadata.json",
    "plan.json",
    "plan.md",
    "approval.plan.json",
    "ai_interactions.jsonl",
    "generated_output.json",
    "change_manifest.json",
    "change_summary.md",
    "validation_results.json",
    "approval.release.json",
    "deployment_evidence.md",
}


@dataclass(frozen=True)
class RunState:
    run_id: str
    run_dir: Path
    feature: str
    created_at: str
    spec_file: str
    stage: str
    next_action: str
    validation_status: str
    plan_approved: bool
    release_approved: bool
    has_plan: bool
    has_changes: bool
    has_validation: bool
    has_evidence: bool


@dataclass(frozen=True)
class RunPage:
    items: list[RunState]
    total: int
    page: int
    page_size: int
    total_pages: int
    page_numbers: tuple[int, ...]

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def start_index(self) -> int:
        if self.total == 0:
            return 0
        return (self.page - 1) * self.page_size + 1

    @property
    def end_index(self) -> int:
        return min(self.page * self.page_size, self.total)


@dataclass(frozen=True)
class CoverageItem:
    label: str
    status: str
    detail: str


def list_runs(audit_root: Path | None = None) -> list[RunState]:
    root = audit_root or get_audit_root()
    if not root.exists():
        return []
    runs = [
        get_run_state(path.name, audit_root=root)
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ]
    return sorted(runs, key=lambda run: run.created_at or run.run_id, reverse=True)


def list_runs_page(
    page: int | str = 1,
    page_size: int | str = 10,
    audit_root: Path | None = None,
) -> RunPage:
    runs = list_runs(audit_root)
    total = len(runs)
    normalized_size = _clamp_int(page_size, default=10, minimum=1, maximum=50)
    total_pages = max(1, (total + normalized_size - 1) // normalized_size)
    normalized_page = _clamp_int(page, default=1, minimum=1, maximum=total_pages)
    start = (normalized_page - 1) * normalized_size
    end = start + normalized_size
    return RunPage(
        items=runs[start:end],
        total=total,
        page=normalized_page,
        page_size=normalized_size,
        total_pages=total_pages,
        page_numbers=_page_window(normalized_page, total_pages),
    )


def get_run_state(run_id: str, audit_root: Path | None = None) -> RunState:
    run_dir = _safe_run_dir(run_id, audit_root)
    metadata = _read_optional_json(run_dir / "run_metadata.json")
    spec = _read_optional_json(run_dir / "spec.normalized.json")
    validation = _read_optional_json(run_dir / "validation_results.json")

    has_plan = (run_dir / "plan.json").exists()
    plan_approved = (run_dir / "approval.plan.json").exists()
    has_changes = (run_dir / "change_manifest.json").exists()
    has_validation = (run_dir / "validation_results.json").exists()
    release_approved = (run_dir / "approval.release.json").exists()
    has_evidence = (run_dir / "deployment_evidence.md").exists()
    validation_status = validation.get("overall_status", "not run") if validation else "not run"
    stage, next_action = _stage_and_next_action(
        has_plan=has_plan,
        plan_approved=plan_approved,
        has_changes=has_changes,
        has_validation=has_validation,
        validation_status=validation_status,
        release_approved=release_approved,
        has_evidence=has_evidence,
    )

    return RunState(
        run_id=run_id,
        run_dir=run_dir,
        feature=str(
            spec.get("feature_name")
            or spec.get("feature_id")
            or metadata.get("spec_slug")
            or run_id
        ),
        created_at=str(metadata.get("created_at", "")),
        spec_file=str(metadata.get("spec_file", "")),
        stage=stage,
        next_action=next_action,
        validation_status=str(validation_status),
        plan_approved=plan_approved,
        release_approved=release_approved,
        has_plan=has_plan,
        has_changes=has_changes,
        has_validation=has_validation,
        has_evidence=has_evidence,
    )


def read_run_detail(run_id: str, audit_root: Path | None = None) -> dict[str, Any]:
    run_dir = _safe_run_dir(run_id, audit_root)
    state = get_run_state(run_id, audit_root)
    return {
        "state": state,
        "spec": _read_optional_json(run_dir / "spec.normalized.json"),
        "plan": _read_optional_json(run_dir / "plan.json"),
        "manifest": _read_optional_json(run_dir / "change_manifest.json"),
        "validation": _read_optional_json(run_dir / "validation_results.json"),
        "plan_approval": _read_optional_json(run_dir / "approval.plan.json"),
        "release_approval": _read_optional_json(run_dir / "approval.release.json"),
        "ai_interactions": _read_jsonl(run_dir / "ai_interactions.jsonl"),
        "artefacts": sorted(name for name in ALLOWED_ARTEFACTS if (run_dir / name).exists()),
        "coverage": build_coverage(run_dir, state),
    }


def read_allowed_artefact(run_id: str, name: str, audit_root: Path | None = None) -> str:
    if name not in ALLOWED_ARTEFACTS:
        raise PipelineError(f"artefact is not allowed: {name}")
    run_dir = _safe_run_dir(run_id, audit_root)
    path = run_dir / name
    if not path.exists():
        raise PipelineError(f"artefact does not exist: {name}")
    return path.read_text(encoding="utf-8")


def _safe_run_dir(run_id: str, audit_root: Path | None) -> Path:
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise PipelineError(f"invalid run id: {run_id}")
    root = audit_root or get_audit_root()
    run_dir = root / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        raise PipelineError(f"run does not exist: {run_id}")
    return run_dir


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        return {}
    return data


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    interactions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                interactions.append(parsed)
    return interactions


def build_coverage(run_dir: Path, state: RunState) -> tuple[CoverageItem, ...]:
    manifest = _read_optional_json(run_dir / "change_manifest.json")
    validation = _read_optional_json(run_dir / "validation_results.json")
    has_spec = (run_dir / "spec.normalized.json").exists()
    artefact_count = sum(1 for name in ALLOWED_ARTEFACTS if (run_dir / name).exists())
    manifest_files = manifest.get("files", []) if isinstance(manifest.get("files"), list) else []
    generated_tests = [
        file
        for file in manifest_files
        if isinstance(file, dict) and str(file.get("path", "")).startswith("demo_app/tests/")
    ]
    mapped_tests = [
        file
        for file in generated_tests
        if isinstance(file.get("acceptance_criteria"), list) and file["acceptance_criteria"]
    ]
    gate_status = validation.get("overall_status", "not run") if validation else "not run"

    return (
        CoverageItem(
            "Spec Intake",
            "complete" if has_spec else "pending",
            "Normalized spec captured" if has_spec else "Waiting for a valid spec",
        ),
        CoverageItem(
            "Planning Layer",
            "complete" if state.has_plan else "pending",
            "Technical plan available" if state.has_plan else "Plan not created",
        ),
        CoverageItem(
            "AI-assisted Implementation",
            "complete" if state.has_changes else "pending",
            (
                "Generated change manifest present"
                if state.has_changes
                else "Implementation not generated"
            ),
        ),
        CoverageItem(
            "Automated Test Generation",
            "complete" if mapped_tests else "pending" if not state.has_changes else "attention",
            f"{len(mapped_tests)} generated test file(s) mapped to AC IDs"
            if mapped_tests
            else "No mapped generated tests yet",
        ),
        CoverageItem(
            "Quality Gates",
            (
                "complete"
                if gate_status == "passed"
                else "attention"
                if state.has_validation
                else "pending"
            ),
            f"Validation {gate_status}",
        ),
        CoverageItem(
            "Human Approval Workflow",
            "complete"
            if state.plan_approved and state.release_approved
            else "partial"
            if state.plan_approved or state.release_approved
            else "pending",
            _approval_detail(state),
        ),
        CoverageItem(
            "Auditability",
            "complete" if state.has_evidence else "partial" if artefact_count >= 3 else "pending",
            f"{artefact_count} audit artefact(s) captured",
        ),
    )


def _approval_detail(state: RunState) -> str:
    if state.plan_approved and state.release_approved:
        return "Plan and release approved"
    if state.plan_approved:
        return "Plan approved; release pending"
    if state.release_approved:
        return "Release approved; plan approval missing"
    return "Approvals pending"


def _clamp_int(value: int | str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _page_window(page: int, total_pages: int) -> tuple[int, ...]:
    start = max(1, page - 2)
    end = min(total_pages, page + 2)
    return tuple(range(start, end + 1))


def _stage_and_next_action(
    *,
    has_plan: bool,
    plan_approved: bool,
    has_changes: bool,
    has_validation: bool,
    validation_status: str,
    release_approved: bool,
    has_evidence: bool,
) -> tuple[str, str]:
    if not has_plan:
        return "Intake", "Create plan"
    if not plan_approved:
        return "Plan ready", "Plan approval required"
    if not has_changes:
        return "Plan approved", "Generate implementation"
    if not has_validation:
        return "Implementation generated", "Run validation"
    if validation_status != "passed":
        return "Validation failed", "Fix issues and rerun validation"
    if not release_approved:
        return "Validation passed", "Release approval required"
    if not has_evidence:
        return "Release approved", "Generate deployment evidence"
    return "Evidence complete", "Review evidence"
