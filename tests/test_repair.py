import hashlib
from pathlib import Path

import pytest

from pipeline.audit import initialize_run, read_json, utc_now, write_json
from pipeline.repair import repair_validation
from pipeline.spec_parser import parse_feature_spec


def test_repair_validation_formats_generated_python_and_updates_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_root = tmp_path / "audit"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("PIPELINE_AUDIT_ROOT", str(audit_root))

    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.ruff]",
                "line-length = 100",
                "",
                "[tool.ruff.lint]",
                'select = ["E", "F", "I"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    spec = parse_feature_spec(Path("specs/examples/discount_calculator.yaml"))
    run_id, run_dir, spec_hash = initialize_run(
        spec,
        Path("specs/examples/discount_calculator.yaml"),
    )
    files = {
        "demo_app/src/demo_app/__init__.py": (
            "from .discount_calculator import calculate_discounted_price, "
            "DiscountValidationError\n"
            "\n"
            "__all__ = ['calculate_discounted_price', 'DiscountValidationError']\n"
        ),
        "demo_app/src/demo_app/discount_calculator.py": (
            "class DiscountValidationError(Exception):\n"
            "    pass\n"
            "\n"
            "def calculate_discounted_price(\n"
            "    base_price: float, discount_percentage: float\n"
            ") -> float:\n"
            "    return round(base_price * (1 - discount_percentage / 100), 2)\n"
        ),
        "demo_app/tests/test_discount_calculator.py": (
            "import pytest\n"
            "from demo_app import calculate_discounted_price, DiscountValidationError\n"
            "\n"
            "def test_invalid_discount():\n"
            "    with pytest.raises(DiscountValidationError, match="
            '"Discount percentage must be between 0 and 100."):\n'
            "        calculate_discounted_price(100.0, -10.0)\n"
        ),
    }
    for relative_path, content in files.items():
        target = repo_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    write_json(
        run_dir / "change_manifest.json",
        {
            "run_id": run_id,
            "provider": "openai-responses",
            "model": "gpt-4o",
            "generated_at": utc_now(),
            "plan_hash": "hash",
            "spec_hash": spec_hash,
            "allowed_paths": ["demo_app/src/demo_app/", "demo_app/tests/"],
            "summary": ["Generated lint-drifted files."],
            "files": [
                {
                    "path": relative_path,
                    "purpose": "Generated file.",
                    "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "acceptance_criteria": ["AC-001"],
                }
                for relative_path, content in files.items()
            ],
        },
    )

    results = repair_validation(run_id, repo_root=repo_root)

    assert results[-1].status == "passed"
    assert (run_dir / "validation_repair.json").exists()
    manifest = read_json(run_dir / "change_manifest.json")
    for file_entry in manifest["files"]:
        content = (repo_root / file_entry["path"]).read_text(encoding="utf-8").encode("utf-8")
        assert file_entry["content_sha256"] == hashlib.sha256(content).hexdigest()
