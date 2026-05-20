"""Deterministic validation gates for generated changes."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

from pipeline.audit import read_json, require_run_dir, utc_now, write_json
from pipeline.models import ChangeManifest, FeatureSpec, GateResult, PlanArtifact, ValidationResults


def validate_run(run_id: str, repo_root: Path | None = None) -> ValidationResults:
    repo_root = (repo_root or Path.cwd()).resolve()
    run_dir = require_run_dir(run_id)

    gates = [
        _run_command("ruff", [sys.executable, "-m", "ruff", "check", "."], repo_root),
        _run_command("mypy", [sys.executable, "-m", "mypy", "pipeline", "demo_app/src"], repo_root),
        _run_command("pytest", [sys.executable, "-m", "pytest"], repo_root),
        _run_command(
            "bandit",
            [
                sys.executable,
                "-m",
                "bandit",
                "-q",
                "-r",
                "pipeline",
                "demo_app/src",
                "-x",
                "tests,demo_app/tests",
                "-ll",
            ],
            repo_root,
        ),
        _policy_gate(run_dir, repo_root),
    ]
    overall_status = "passed" if all(gate.status == "passed" for gate in gates) else "failed"
    results = ValidationResults(
        run_id=run_id,
        overall_status=overall_status,
        created_at=utc_now(),
        gates=gates,
    )
    write_json(run_dir / "validation_results.json", results.to_json_data())
    return results


def _run_command(name: str, command: list[str], repo_root: Path) -> GateResult:
    started = utc_now()
    completed = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    finished = utc_now()
    return GateResult(
        name=name,
        status="passed" if completed.returncode == 0 else "failed",
        command=command,
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        details=[],
        started_at=started,
        finished_at=finished,
    )


def _policy_gate(run_dir: Path, repo_root: Path) -> GateResult:
    started = utc_now()
    details: list[str] = []
    try:
        spec = FeatureSpec.model_validate(read_json(run_dir / "spec.normalized.json"))
        plan = PlanArtifact.model_validate(read_json(run_dir / "plan.json"))
        manifest = ChangeManifest.model_validate(read_json(run_dir / "change_manifest.json"))

        _check_manifest_paths(manifest, plan, repo_root, details)
        _check_manifest_hashes(manifest, repo_root, details)
        _check_acceptance_coverage(spec, plan, repo_root, details)
    except Exception as exc:  # noqa: BLE001 - policy gate must convert all failures to evidence
        details.append(str(exc))

    finished = utc_now()
    return GateResult(
        name="policy",
        status="passed" if not details else "failed",
        details=details,
        started_at=started,
        finished_at=finished,
    )


def _check_manifest_paths(
    manifest: ChangeManifest,
    plan: PlanArtifact,
    repo_root: Path,
    details: list[str],
) -> None:
    allowed_roots = [(repo_root / allowed_path).resolve() for allowed_path in plan.allowed_paths]
    planned_paths = set(plan.impacted_modules_files)

    for entry in manifest.files:
        relative_path = Path(entry.path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            details.append(f"unsafe generated path: {entry.path}")
            continue
        target = (repo_root / relative_path).resolve()
        if not any(_is_relative_to(target, allowed_root) for allowed_root in allowed_roots):
            details.append(f"generated path outside allowed paths: {entry.path}")
        if entry.path not in planned_paths:
            details.append(f"generated path was not in approved plan: {entry.path}")


def _check_manifest_hashes(
    manifest: ChangeManifest,
    repo_root: Path,
    details: list[str],
) -> None:
    for entry in manifest.files:
        target = repo_root / entry.path
        if not target.exists():
            details.append(f"generated file listed in manifest is missing: {entry.path}")
            continue
        actual_hash = hashlib.sha256(target.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        if actual_hash != entry.content_sha256:
            details.append(f"generated file hash mismatch: {entry.path}")


def _check_acceptance_coverage(
    spec: FeatureSpec,
    plan: PlanArtifact,
    repo_root: Path,
    details: list[str],
) -> None:
    required_ids = {criterion.id for criterion in spec.acceptance_criteria}
    test_files = sorted((repo_root / "demo_app/tests").glob(f"test_{plan.target_module}*.py"))
    observed_ids: set[str] = set()
    for test_file in test_files:
        observed_ids.update(re.findall(r"\bAC-\d{3,}\b", test_file.read_text(encoding="utf-8")))
    missing = sorted(required_ids - observed_ids)
    if missing:
        details.append(f"missing acceptance coverage for: {', '.join(missing)}")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False

