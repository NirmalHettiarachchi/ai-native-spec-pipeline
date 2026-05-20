"""Implementation generation orchestration."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pipeline.ai import build_generation_prompt, get_ai_provider, get_provider_audit_metadata
from pipeline.approval import require_approval
from pipeline.audit import (
    append_jsonl,
    read_json,
    require_run_dir,
    sha256_file,
    utc_now,
    write_json,
)
from pipeline.change_guard import validate_generated_paths
from pipeline.models import ChangeManifest, ChangeManifestEntry, FeatureSpec, PlanArtifact


def implement_run(run_id: str, repo_root: Path | None = None) -> ChangeManifest:
    repo_root = (repo_root or Path.cwd()).resolve()
    run_dir = require_run_dir(run_id)
    require_approval(run_id, "plan")

    spec = FeatureSpec.model_validate(read_json(run_dir / "spec.normalized.json"))
    plan = PlanArtifact.model_validate(read_json(run_dir / "plan.json"))
    provider = get_ai_provider()
    prompt = build_generation_prompt(spec, plan)
    change_set = provider.generate_changes(spec, plan)

    validate_generated_paths(change_set.files, plan, repo_root)
    write_json(run_dir / "generated_output.json", change_set.to_json_data())

    append_jsonl(
        run_dir / "ai_interactions.jsonl",
        {
            "run_id": run_id,
            "created_at": utc_now(),
            "provider": change_set.provider,
            "model": change_set.model,
            "prompt": prompt,
            "response": change_set.to_json_data(),
            "metadata": get_provider_audit_metadata(provider),
        },
    )

    manifest = ChangeManifest(
        run_id=run_id,
        provider=change_set.provider,
        model=change_set.model,
        generated_at=utc_now(),
        plan_hash=sha256_file(run_dir / "plan.json"),
        spec_hash=plan.spec_hash,
        allowed_paths=plan.allowed_paths,
        summary=change_set.summary,
        files=[
            ChangeManifestEntry(
                path=generated_file.path,
                purpose=generated_file.purpose,
                content_sha256=hashlib.sha256(
                    generated_file.content.encode("utf-8")
                ).hexdigest(),
                acceptance_criteria=generated_file.acceptance_criteria,
            )
            for generated_file in change_set.files
        ],
    )
    write_json(run_dir / "change_manifest.json", manifest.to_json_data())

    for generated_file in change_set.files:
        target = repo_root / generated_file.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(generated_file.content, encoding="utf-8")

    _write_summary(run_dir / "change_summary.md", manifest)
    return manifest


def _write_summary(path: Path, manifest: ChangeManifest) -> None:
    lines = [
        f"# Generated Change Summary: {manifest.run_id}",
        "",
        f"- Provider: `{manifest.provider}`",
        f"- Model: `{manifest.model}`",
        "",
        "## Summary",
        "",
    ]
    lines.extend(f"- {item}" for item in manifest.summary)
    lines.extend(["", "## Files", ""])
    for file_entry in manifest.files:
        ac = ", ".join(file_entry.acceptance_criteria) or "N/A"
        lines.append(f"- `{file_entry.path}`: {file_entry.purpose} Acceptance criteria: {ac}.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
