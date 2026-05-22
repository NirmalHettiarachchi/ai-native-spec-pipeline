"""Deterministic policy guard for generated file writes."""

from __future__ import annotations

from pathlib import Path

from pipeline.errors import PipelineError
from pipeline.models import GeneratedFile, PlanArtifact


def validate_generated_paths(
    files: list[GeneratedFile],
    plan: PlanArtifact,
    repo_root: Path,
) -> None:
    allowed_roots = [(repo_root / path).resolve() for path in plan.allowed_paths]
    if not files:
        raise PipelineError("generated change set contains no files")

    planned_paths = set(plan.impacted_modules_files)
    generated_paths = [generated_file.path for generated_file in files]
    duplicate_paths = sorted(
        {path for path in generated_paths if generated_paths.count(path) > 1}
    )
    if duplicate_paths:
        raise PipelineError(
            "generated change set contains duplicate files: "
            f"{', '.join(duplicate_paths)}"
        )

    for generated_file in files:
        relative_path = Path(generated_file.path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise PipelineError(
                f"generated path is not a safe relative path: {generated_file.path}"
            )

        target = (repo_root / relative_path).resolve()
        if not any(_is_relative_to(target, allowed_root) for allowed_root in allowed_roots):
            raise PipelineError(f"generated file is outside approved paths: {generated_file.path}")

        if generated_file.path not in planned_paths:
            raise PipelineError(
                f"generated file was not listed in the approved plan: {generated_file.path}"
            )

    missing_paths = sorted(planned_paths - set(generated_paths))
    if missing_paths:
        raise PipelineError(
            "generated change set is missing approved plan files: "
            f"{', '.join(missing_paths)}"
        )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
