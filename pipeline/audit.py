from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.errors import PipelineError
from pipeline.models import FeatureSpec

AUDIT_ROOT = Path("audit") / "runs"


def get_audit_root() -> Path:
    return Path(os.getenv("PIPELINE_AUDIT_ROOT", str(AUDIT_ROOT)))


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_run_id(spec: FeatureSpec, audit_root: Path | None = None) -> str:
    audit_root = audit_root or get_audit_root()
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    base = f"{timestamp}-{spec.slug}"
    candidate = base
    counter = 2
    while (audit_root / candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def get_run_dir(run_id: str, audit_root: Path | None = None) -> Path:
    audit_root = audit_root or get_audit_root()
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise PipelineError(f"invalid run id: {run_id}")
    return audit_root / run_id


def require_run_dir(run_id: str, audit_root: Path | None = None) -> Path:
    run_dir = get_run_dir(run_id, audit_root)
    if not run_dir.exists():
        raise PipelineError(f"run does not exist: {run_id}")
    return run_dir


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, sort_keys=True) + "\n")


def read_json(path: Path) -> Any:
    if not path.exists():
        raise PipelineError(f"required audit artefact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_json(data: Any) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.exists():
        raise PipelineError(f"cannot hash missing artefact: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def initialize_run(
    spec: FeatureSpec,
    spec_file: Path,
    audit_root: Path | None = None,
) -> tuple[str, Path, str]:
    audit_root = audit_root or get_audit_root()
    run_id = create_run_id(spec, audit_root)
    run_dir = get_run_dir(run_id, audit_root)
    spec_data = spec.to_json_data()
    spec_hash = sha256_json(spec_data)

    write_json(run_dir / "spec.normalized.json", spec_data)
    write_json(
        run_dir / "run_metadata.json",
        {
            "run_id": run_id,
            "created_at": utc_now(),
            "spec_file": str(spec_file),
            "spec_hash": spec_hash,
            "spec_slug": spec.slug,
        },
    )
    return run_id, run_dir, spec_hash
