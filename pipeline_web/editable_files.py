"""Safe editor helpers for generated run files."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pipeline.audit import read_json, require_run_dir, write_json
from pipeline.errors import PipelineError
from pipeline.models import ChangeManifest


@dataclass(frozen=True)
class EditableFile:
    path: str
    purpose: str


@dataclass(frozen=True)
class EditorContext:
    run_id: str
    selected_file: EditableFile
    files: tuple[EditableFile, ...]
    content: str
    original_content: str
    gate_name: str
    gate_output: str


def read_editor_context(
    run_id: str,
    *,
    selected_path: str = "",
    gate_name: str = "",
    repo_root: Path | None = None,
) -> EditorContext:
    repo_root = (repo_root or Path.cwd()).resolve()
    run_dir = require_run_dir(run_id)
    manifest = _read_manifest(run_dir)
    files = _editable_files(manifest)
    if not files:
        raise PipelineError("run has no generated files to edit")

    gate_output = _gate_output(run_dir, gate_name)
    selected_path = selected_path or _path_from_gate_output(files, gate_output)
    selected = _select_file(files, selected_path)
    target = _safe_repo_path(selected.path, repo_root)
    if not target.exists():
        raise PipelineError(f"generated file does not exist: {selected.path}")
    content = target.read_text(encoding="utf-8")

    return EditorContext(
        run_id=run_id,
        selected_file=selected,
        files=files,
        content=content,
        original_content=_original_content(run_dir, selected.path, content),
        gate_name=gate_name,
        gate_output=gate_output,
    )


def save_editable_file(
    run_id: str,
    *,
    file_path: str,
    content: str,
    repo_root: Path | None = None,
) -> None:
    repo_root = (repo_root or Path.cwd()).resolve()
    run_dir = require_run_dir(run_id)
    manifest = _read_manifest(run_dir)
    allowed_paths = {entry.path for entry in manifest.files}
    if file_path not in allowed_paths:
        raise PipelineError(f"file is not editable for this run: {file_path}")

    target = _safe_repo_path(file_path, repo_root)
    if not target.exists():
        raise PipelineError(f"generated file does not exist: {file_path}")
    target.write_text(content, encoding="utf-8")

    encoded = content.encode("utf-8")
    for entry in manifest.files:
        if entry.path == file_path:
            entry.content_sha256 = hashlib.sha256(encoded).hexdigest()
            break
    write_json(run_dir / "change_manifest.json", manifest.to_json_data())


def _read_manifest(run_dir: Path) -> ChangeManifest:
    manifest_path = run_dir / "change_manifest.json"
    if not manifest_path.exists():
        raise PipelineError("implementation has not been generated")
    return ChangeManifest.model_validate(read_json(manifest_path))


def _editable_files(manifest: ChangeManifest) -> tuple[EditableFile, ...]:
    return tuple(
        EditableFile(path=entry.path, purpose=entry.purpose)
        for entry in manifest.files
        if Path(entry.path).suffix in {".py", ".md", ".json", ".yaml", ".yml"}
    )


def _select_file(files: tuple[EditableFile, ...], selected_path: str) -> EditableFile:
    if not selected_path:
        return files[0]
    for file in files:
        if file.path == selected_path:
            return file
    raise PipelineError(f"file is not editable for this run: {selected_path}")


def _path_from_gate_output(files: tuple[EditableFile, ...], gate_output: str) -> str:
    normalized_output = gate_output.replace("\\", "/")
    for file in files:
        if file.path.replace("\\", "/") in normalized_output:
            return file.path
    return ""


def _safe_repo_path(file_path: str, repo_root: Path) -> Path:
    relative_path = Path(file_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise PipelineError(f"file path is not safe: {file_path}")
    target = (repo_root / relative_path).resolve()
    if not _is_relative_to(target, repo_root):
        raise PipelineError(f"file path escapes repository root: {file_path}")
    return target


def _gate_output(run_dir: Path, gate_name: str) -> str:
    if not gate_name:
        return ""
    validation_path = run_dir / "validation_results.json"
    if not validation_path.exists():
        return ""
    validation = read_json(validation_path)
    gates = validation.get("gates", [])
    if not isinstance(gates, list):
        return ""
    for gate in gates:
        if not isinstance(gate, dict) or gate.get("name") != gate_name:
            continue
        details = gate.get("details", [])
        detail_text = "\n".join(str(detail) for detail in details if detail)
        return "\n".join(
            part
            for part in [str(gate.get("stdout", "")), str(gate.get("stderr", "")), detail_text]
            if part
        )
    return ""


def _original_content(run_dir: Path, file_path: str, current_content: str) -> str:
    snapshot_path = _snapshot_path(run_dir, file_path)
    if snapshot_path.exists():
        return snapshot_path.read_text(encoding="utf-8")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(current_content, encoding="utf-8")
    return current_content


def _snapshot_path(run_dir: Path, file_path: str) -> Path:
    digest = hashlib.sha256(file_path.encode("utf-8")).hexdigest()
    return run_dir / "editor_snapshots" / f"{digest}.txt"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
