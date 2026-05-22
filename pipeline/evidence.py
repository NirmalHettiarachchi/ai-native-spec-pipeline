from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline.approval import require_approval
from pipeline.audit import read_json, require_run_dir, utc_now
from pipeline.errors import PipelineError


def create_deployment_evidence(run_id: str, repo_root: Path | None = None) -> Path:
    repo_root = (repo_root or Path.cwd()).resolve()
    run_dir = require_run_dir(run_id)
    require_approval(run_id, "release")

    validation = read_json(run_dir / "validation_results.json")
    if validation.get("overall_status") != "passed":
        raise PipelineError("deployment evidence requires passing validation results")

    spec = read_json(run_dir / "spec.normalized.json")
    plan = read_json(run_dir / "plan.json")
    manifest = read_json(run_dir / "change_manifest.json")
    plan_approval = read_json(run_dir / "approval.plan.json")
    release_approval = read_json(run_dir / "approval.release.json")
    git_info = _git_info(repo_root)

    lines = [
        f"# Deployment Evidence: {run_id}",
        "",
        f"- Created at: `{utc_now()}`",
        f"- Feature: `{spec.get('feature_name') or spec.get('feature_id')}`",
        f"- Spec hash: `{plan['spec_hash']}`",
        f"- Git commit: `{git_info['commit']}`",
        f"- Working tree clean: `{git_info['working_tree_clean']}`",
        f"- Validation status: `{validation['overall_status']}`",
        "",
        "## Approvals",
        "",
        (
            f"- Plan: approved by `{plan_approval['approver']}` at "
            f"`{plan_approval['approved_at']}` for `{plan_approval['artifact_hash']}`"
        ),
        (
            f"- Release: approved by `{release_approval['approver']}` at "
            f"`{release_approval['approved_at']}` for `{release_approval['artifact_hash']}`"
        ),
        "",
        "## Generated Changes",
        "",
    ]
    for file_entry in manifest["files"]:
        ac = ", ".join(file_entry.get("acceptance_criteria") or []) or "N/A"
        lines.append(f"- `{file_entry['path']}`: {file_entry['purpose']} AC: {ac}.")

    lines.extend(["", "## Validation Gates", ""])
    for gate in validation["gates"]:
        lines.append(f"- `{gate['name']}`: `{gate['status']}`")

    lines.extend(["", "## Reproducibility", ""])
    lines.extend(
        [
            "- Re-run validation with `python -m pipeline validate <run-id>`.",
            "- Review prompts and generated outputs in `ai_interactions.jsonl` "
            "and `generated_output.json`.",
            "- Review the bounded change manifest in `change_manifest.json`.",
            "",
        ]
    )

    evidence_path = run_dir / "deployment_evidence.md"
    evidence_path.write_text("\n".join(lines), encoding="utf-8")
    return evidence_path


def _git_info(repo_root: Path) -> dict[str, str | bool]:
    commit = _git(["rev-parse", "HEAD"], repo_root)
    status = _git(["status", "--short"], repo_root)
    return {
        "commit": commit or "unavailable",
        "working_tree_clean": status == "",
    }


def _git(args: list[str], repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()
