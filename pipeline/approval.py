from __future__ import annotations

from typing import Literal

from pipeline.audit import read_json, require_run_dir, sha256_file, sha256_json, utc_now, write_json
from pipeline.errors import PipelineError
from pipeline.models import ApprovalRecord

ApprovalStage = Literal["plan", "release"]

_STAGE_ARTEFACTS: dict[ApprovalStage, str] = {
    "plan": "plan.json",
    "release": "validation_results.json",
}


def create_approval(run_id: str, stage: ApprovalStage, approver: str) -> ApprovalRecord:
    if not approver.strip():
        raise PipelineError("approver must not be empty")

    run_dir = require_run_dir(run_id)
    artifact_name = _STAGE_ARTEFACTS[stage]
    artifact_path = run_dir / artifact_name
    if not artifact_path.exists():
        raise PipelineError(f"cannot approve {stage}; missing required artefact: {artifact_name}")

    if stage == "release":
        validation = read_json(artifact_path)
        if validation.get("overall_status") != "passed":
            raise PipelineError("release approval requires passing validation_results.json")

    artifact_hash = sha256_file(artifact_path)
    approved_at = utc_now()
    signature = sha256_json(
        {
            "run_id": run_id,
            "stage": stage,
            "approver": approver.strip(),
            "artifact_hash": artifact_hash,
            "approved_at": approved_at,
        }
    )
    record = ApprovalRecord(
        run_id=run_id,
        stage=stage,
        approver=approver.strip(),
        artifact_path=artifact_name,
        artifact_hash=artifact_hash,
        approved_at=approved_at,
        signature=signature,
    )
    write_json(run_dir / f"approval.{stage}.json", record.to_json_data())
    return record


def require_approval(run_id: str, stage: ApprovalStage) -> ApprovalRecord:
    run_dir = require_run_dir(run_id)
    approval_path = run_dir / f"approval.{stage}.json"
    if not approval_path.exists():
        raise PipelineError(
            f"{stage} approval is required. Run: "
            f"python -m pipeline approve {run_id} --stage {stage} --approver <name>"
        )

    record = ApprovalRecord.model_validate(read_json(approval_path))
    artifact_path = run_dir / record.artifact_path
    current_hash = sha256_file(artifact_path)
    if current_hash != record.artifact_hash:
        raise PipelineError(
            f"{stage} approval is stale because {record.artifact_path} changed after approval"
        )
    return record

