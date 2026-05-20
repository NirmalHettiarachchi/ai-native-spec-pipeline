"""Parse Markdown, YAML, and JSON feature specifications."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from pipeline.errors import SpecValidationError
from pipeline.models import AcceptanceCriterion, FeatureSpec

_REQUIRED_FIELDS = {
    "feature_objective",
    "user_story",
    "business_rules",
    "acceptance_criteria",
    "non_functional_requirements",
    "out_of_scope",
}

_KEY_ALIASES = {
    "objective": "feature_objective",
    "feature_objective": "feature_objective",
    "feature_id": "feature_id",
    "feature_name": "feature_name",
    "schema_version": "schema_version",
    "user_story": "user_story",
    "business_rules": "business_rules",
    "business_rule": "business_rules",
    "acceptance_criteria": "acceptance_criteria",
    "acceptance_criterion": "acceptance_criteria",
    "nonfunctional_requirements": "non_functional_requirements",
    "non_functional_requirements": "non_functional_requirements",
    "out_of_scope": "out_of_scope",
}


def parse_feature_spec(path: Path) -> FeatureSpec:
    """Load and validate a feature specification from disk."""

    if not path.exists():
        raise SpecValidationError(f"spec file does not exist: {path}")

    suffix = path.suffix.lower()
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecValidationError(f"could not read spec file {path}: {exc}") from exc

    if suffix in {".yaml", ".yml"}:
        raw_data = _load_yaml(raw_text, path)
    elif suffix == ".json":
        raw_data = _load_json(raw_text, path)
    elif suffix in {".md", ".markdown"}:
        raw_data = _load_markdown(raw_text, path)
    else:
        raise SpecValidationError(
            f"unsupported spec format '{suffix}'. Use Markdown, YAML, or JSON."
        )

    return normalize_feature_spec(raw_data)


def normalize_feature_spec(raw_data: Any) -> FeatureSpec:
    """Normalize loose input forms into the canonical FeatureSpec model."""

    if not isinstance(raw_data, dict):
        raise SpecValidationError("spec root must be an object with named sections")

    normalized: dict[str, Any] = {}
    for key, value in raw_data.items():
        canonical_key = _KEY_ALIASES.get(_normalize_key(str(key)))
        if canonical_key is not None:
            normalized[canonical_key] = value
        else:
            normalized[key] = value

    missing = sorted(field for field in _REQUIRED_FIELDS if field not in normalized)
    if missing:
        raise SpecValidationError(f"spec is missing required section(s): {', '.join(missing)}")

    normalized["business_rules"] = _coerce_string_list(
        normalized.get("business_rules"), "business_rules"
    )
    normalized["non_functional_requirements"] = _coerce_string_list(
        normalized.get("non_functional_requirements"), "non_functional_requirements"
    )
    normalized["out_of_scope"] = _coerce_string_list(
        normalized.get("out_of_scope"), "out_of_scope"
    )
    normalized["acceptance_criteria"] = _coerce_acceptance_criteria(
        normalized.get("acceptance_criteria")
    )

    try:
        return FeatureSpec.model_validate(normalized)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise SpecValidationError(f"spec validation failed: {details}") from exc
    except ValueError as exc:
        raise SpecValidationError(f"spec validation failed: {exc}") from exc


def _load_yaml(raw_text: str, path: Path) -> Any:
    try:
        return yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise SpecValidationError(f"invalid YAML in {path}: {exc}") from exc


def _load_json(raw_text: str, path: Path) -> Any:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SpecValidationError(f"invalid JSON in {path}: {exc}") from exc


def _load_markdown(raw_text: str, path: Path) -> dict[str, Any]:
    frontmatter, body = _split_frontmatter(raw_text, path)
    if frontmatter:
        return frontmatter
    return _parse_markdown_sections(body)


def _split_frontmatter(raw_text: str, path: Path) -> tuple[dict[str, Any] | None, str]:
    if not raw_text.startswith("---"):
        return None, raw_text

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw_text, flags=re.DOTALL)
    if not match:
        raise SpecValidationError(f"invalid Markdown frontmatter block in {path}")

    frontmatter = _load_yaml(match.group(1), path)
    if not isinstance(frontmatter, dict):
        raise SpecValidationError("Markdown frontmatter must be a YAML object")
    return frontmatter, match.group(2)


def _parse_markdown_sections(body: str) -> dict[str, Any]:
    sections: dict[str, list[str]] = {}
    current_key: str | None = None
    feature_name: str | None = None

    for raw_line in body.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", raw_line)
        if heading:
            title = heading.group(2).strip()
            if heading.group(1) == "#" and feature_name is None:
                feature_name = title
            current_key = _KEY_ALIASES.get(_normalize_key(title))
            if current_key is not None:
                sections.setdefault(current_key, [])
            continue
        if current_key is not None:
            sections[current_key].append(raw_line)

    parsed: dict[str, Any] = {}
    if feature_name:
        parsed["feature_name"] = feature_name

    for key, lines in sections.items():
        text = "\n".join(lines).strip()
        if key in {"feature_objective", "user_story"}:
            parsed[key] = _compact_markdown_text(text)
        elif key == "acceptance_criteria":
            parsed[key] = _parse_markdown_acceptance(text)
        else:
            parsed[key] = _parse_markdown_list(text)

    return parsed


def _parse_markdown_acceptance(text: str) -> list[dict[str, str]]:
    items = _parse_markdown_list(text)
    criteria = []
    for index, item in enumerate(items, start=1):
        match = re.match(r"^([A-Za-z]{1,5}[-_]?\d{1,4})\s*[:\-]\s*(.+)$", item)
        if match:
            criteria.append(
                {
                    "id": match.group(1).upper().replace("_", "-"),
                    "description": match.group(2),
                }
            )
        else:
            criteria.append({"id": f"AC-{index:03d}", "description": item})
    return criteria


def _parse_markdown_list(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        numbered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if bullet:
            items.append(bullet.group(1).strip())
        elif numbered:
            items.append(numbered.group(1).strip())
        elif stripped:
            items.append(stripped)
    return items


def _compact_markdown_text(text: str) -> str:
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def _coerce_string_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        items = [line.strip(" -*\t") for line in value.splitlines() if line.strip(" -*\t")]
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        raise SpecValidationError(f"{field_name} must be a string or list of strings")
    return items


def _coerce_acceptance_criteria(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise SpecValidationError("acceptance_criteria must be a list")

    criteria: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, AcceptanceCriterion):
            criteria.append(item.model_dump(mode="json"))
        elif isinstance(item, str):
            criteria.extend(_parse_markdown_acceptance(item))
        elif isinstance(item, dict):
            normalized = {_KEY_ALIASES.get(_normalize_key(str(k)), k): v for k, v in item.items()}
            criterion_id = str(
                normalized.get("id") or normalized.get("criterion_id") or f"AC-{index:03d}"
            )
            description = (
                normalized.get("description")
                or normalized.get("criterion")
                or normalized.get("text")
            )
            if description is None:
                raise SpecValidationError(
                    f"acceptance criterion {criterion_id} is missing description"
                )
            criteria.append({"id": criterion_id, "description": str(description)})
        else:
            raise SpecValidationError("acceptance_criteria items must be strings or objects")
    return criteria


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
