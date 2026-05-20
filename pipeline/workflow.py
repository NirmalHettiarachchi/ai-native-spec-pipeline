"""Resumable high-level workflow orchestration."""

from __future__ import annotations

from pathlib import Path

from pipeline.approval import require_approval
from pipeline.audit import initialize_run, require_run_dir
from pipeline.errors import PipelineError
from pipeline.evidence import create_deployment_evidence
from pipeline.gates import validate_run
from pipeline.generator import implement_run
from pipeline.planner import create_plan, write_plan
from pipeline.spec_parser import parse_feature_spec


def run_pipeline(spec_file: Path, run_id: str | None = None) -> list[str]:
    if run_id is None:
        spec = parse_feature_spec(spec_file)
        created_run_id, run_dir, spec_hash = initialize_run(spec, spec_file)
        plan = create_plan(spec, created_run_id, spec_hash)
        write_plan(run_dir, plan, spec)
        return [
            f"created run: {created_run_id}",
            "paused before implementation; plan approval is required",
            f"python -m pipeline approve {created_run_id} --stage plan --approver <name>",
            f"python -m pipeline run {spec_file} --run-id {created_run_id}",
        ]

    run_dir = require_run_dir(run_id)
    messages = [f"resuming run: {run_id}"]

    try:
        require_approval(run_id, "plan")
    except PipelineError as exc:
        return [*messages, str(exc)]

    if not (run_dir / "change_manifest.json").exists():
        manifest = implement_run(run_id)
        messages.append(f"generated {len(manifest.files)} file(s)")

    validation = validate_run(run_id)
    messages.append(f"validation: {validation.overall_status}")
    if validation.overall_status != "passed":
        raise PipelineError(
            "validation failed; inspect validation_results.json before release approval"
        )

    try:
        require_approval(run_id, "release")
    except PipelineError:
        return [
            *messages,
            "paused before deployment evidence; release approval is required",
            f"python -m pipeline approve {run_id} --stage release --approver <name>",
            f"python -m pipeline run {spec_file} --run-id {run_id}",
        ]

    evidence_path = create_deployment_evidence(run_id)
    return [*messages, f"deployment evidence: {evidence_path}"]
