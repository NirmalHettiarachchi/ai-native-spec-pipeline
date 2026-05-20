"""Spec discovery and upload helpers for the dashboard."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from pipeline.errors import PipelineError
from pipeline.spec_parser import parse_feature_spec

DEFAULT_SPEC = "specs/examples/discount_calculator.yaml"
SUPPORTED_SPEC_SUFFIXES = {".yaml", ".yml", ".json", ".md", ".markdown"}


def get_spec_root() -> Path:
    """Return the root directory where selectable specs are stored."""

    return Path(os.getenv("PIPELINE_SPEC_ROOT", "specs")).resolve()


def list_spec_files(spec_root: Path | None = None) -> list[str]:
    """Discover supported spec files below the spec root."""

    root = (spec_root or get_spec_root()).resolve()
    if not root.exists():
        return []

    specs = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SPEC_SUFFIXES:
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        specs.append(_display_path(path, root))
    return sorted(specs)


def resolve_spec_path(spec_path: str, spec_root: Path | None = None) -> Path:
    """Resolve a submitted spec path while keeping it inside the spec root."""

    if not spec_path.strip():
        raise PipelineError("Choose a spec before creating a run.")

    root = (spec_root or get_spec_root()).resolve()
    submitted = Path(spec_path.strip())
    if submitted.suffix.lower() not in SUPPORTED_SPEC_SUFFIXES:
        raise PipelineError("Spec must be .yaml, .yml, .json, .md, or .markdown.")

    if submitted.is_absolute():
        candidate = submitted.resolve()
    else:
        parts = submitted.parts
        if parts and parts[0] == root.name:
            candidate = root.joinpath(*parts[1:]).resolve()
        else:
            candidate = root.joinpath(submitted).resolve()

    if not _is_relative_to(candidate, root):
        raise PipelineError("Spec path must stay inside specs/.")
    if not candidate.exists() or not candidate.is_file():
        raise PipelineError(f"spec file does not exist: {spec_path}")
    return candidate


def save_uploaded_spec(
    filename: str,
    content: bytes,
    spec_root: Path | None = None,
) -> Path:
    """Validate and store an uploaded spec under specs/uploads."""

    if not filename:
        raise PipelineError("Choose a spec file to upload.")
    if not content:
        raise PipelineError("Uploaded spec is empty.")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SPEC_SUFFIXES:
        raise PipelineError("Uploaded spec must be .yaml, .yml, .json, .md, or .markdown.")

    root = (spec_root or get_spec_root()).resolve()
    upload_dir = root / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = _safe_stem(Path(filename).stem)
    digest = hashlib.sha256(content).hexdigest()[:10]
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    path = upload_dir / f"{timestamp}-{safe_stem}-{digest}{suffix}"
    path.write_bytes(content)

    try:
        parse_feature_spec(path)
    except PipelineError:
        path.unlink(missing_ok=True)
        raise
    return path


def _display_path(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return f"{root.name}/{relative}"


def _safe_stem(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip(".-")
    return cleaned[:80] or "spec"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
