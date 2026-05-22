"""Automated repair helpers for generated validation failures."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from pipeline.audit import read_json, require_run_dir, utc_now, write_json
from pipeline.errors import PipelineError
from pipeline.models import ChangeManifest, GateResult


def repair_validation(run_id: str, repo_root: Path | None = None) -> list[GateResult]:
    """Apply deterministic formatting fixes to generated Python files."""

    repo_root = (repo_root or Path.cwd()).resolve()
    run_dir = require_run_dir(run_id)
    manifest = ChangeManifest.model_validate(read_json(run_dir / "change_manifest.json"))
    targets = _generated_python_paths(manifest, repo_root)
    if not targets:
        raise PipelineError("validation repair found no generated Python files to fix")

    commands = [
        ("ruff-check-fix", [sys.executable, "-m", "ruff", "check", "--fix", *targets]),
        ("ruff-format", [sys.executable, "-m", "ruff", "format", *targets]),
        ("ruff-check", [sys.executable, "-m", "ruff", "check", *targets]),
    ]
    results = [_run_command(name, command, repo_root) for name, command in commands]

    _refresh_manifest_hashes(manifest, repo_root)
    write_json(run_dir / "change_manifest.json", manifest.to_json_data())
    write_json(
        run_dir / "validation_repair.json",
        {
            "run_id": run_id,
            "created_at": utc_now(),
            "status": "passed" if results[-1].status == "passed" else "failed",
            "strategy": "ruff check --fix followed by ruff format on generated files",
            "files": targets,
            "commands": [result.model_dump(mode="json") for result in results],
        },
    )

    if results[-1].status != "passed":
        raise PipelineError("Automated validation repair completed but Ruff still fails.")
    return results


def _generated_python_paths(manifest: ChangeManifest, repo_root: Path) -> list[str]:
    targets: list[str] = []
    for entry in manifest.files:
        relative_path = Path(entry.path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise PipelineError(f"generated path is not a safe relative path: {entry.path}")
        target = (repo_root / relative_path).resolve()
        if not _is_relative_to(target, repo_root):
            raise PipelineError(f"generated path escapes repository root: {entry.path}")
        if target.suffix == ".py":
            targets.append(entry.path)
    return targets


def _refresh_manifest_hashes(manifest: ChangeManifest, repo_root: Path) -> None:
    for entry in manifest.files:
        target = repo_root / entry.path
        if not target.exists():
            raise PipelineError(f"generated file listed in manifest is missing: {entry.path}")
        content = target.read_text(encoding="utf-8").encode("utf-8")
        entry.content_sha256 = hashlib.sha256(content).hexdigest()


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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
