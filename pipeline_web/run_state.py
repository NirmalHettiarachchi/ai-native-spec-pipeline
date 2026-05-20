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

