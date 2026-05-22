import hashlib
import importlib.util
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


def test_repair_validation_replaces_scientific_calculator_eval(
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
                'select = ["E", "F", "I", "S"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    spec = parse_feature_spec(Path("specs/examples/scientific_calculator.yaml"))
    run_id, run_dir, spec_hash = initialize_run(
        spec,
        Path("specs/examples/scientific_calculator.yaml"),
    )
    relative_path = "demo_app/src/demo_app/scientific_calculator.py"
    content = (
        "import math\n\n"
        "ACCEPTANCE_CRITERIA = ['AC-001']\n\n"
        "def run_scientific_calculator(expression):\n"
        "    return eval(expression, {'math': math, '__builtins__': None})\n"
    )
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
            "summary": ["Generated unsafe scientific calculator."],
            "files": [
                {
                    "path": relative_path,
                    "purpose": "Generated implementation.",
                    "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "acceptance_criteria": ["AC-001"],
                }
            ],
        },
    )

    results = repair_validation(run_id, repo_root=repo_root)

    repaired = target.read_text(encoding="utf-8")
    assert results[-1].status == "passed"
    assert results[-1].name == "ruff-check-after-generated-repair"
    assert "eval(" not in repaired
    assert "ast.parse" in repaired

    module_spec = importlib.util.spec_from_file_location("scientific_calculator", target)
    assert module_spec is not None
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(module)
    assert module.run_scientific_calculator("2 + 2") == 4
    assert module.run_scientific_calculator("1 / 0") == "Validation Error: Division by zero"


def test_repair_validation_fixes_generated_exception_contract(
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
                'select = ["E", "F", "I", "B"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    spec = parse_feature_spec(Path("specs/examples/scientific_calculator.yaml"))
    run_id, run_dir, spec_hash = initialize_run(
        spec,
        Path("specs/examples/scientific_calculator.yaml"),
    )
    files = {
        "demo_app/src/demo_app/scientific_calculator.py": (
            "import math\n\n"
            "class CalculatorError(Exception):\n"
            "    pass\n\n"
            "def run_scientific_calculator(expression):\n"
            "    try:\n"
            "        return math.sqrt(float(expression))\n"
            "    except Exception as e:\n"
            "        raise CalculatorError(f\"Invalid expression: {str(e)}\")\n"
        ),
        "demo_app/src/demo_app/__init__.py": (
            "from .scientific_calculator import run_scientific_calculator\n"
            "\n"
            '__all__ = ["run_scientific_calculator"]\n'
        ),
        "demo_app/tests/test_scientific_calculator.py": (
            "from demo_app import CalculatorError, run_scientific_calculator\n\n"
            "def test_invalid_expression():\n"
            "    try:\n"
            "        run_scientific_calculator('bad')\n"
            "    except CalculatorError:\n"
            "        pass\n"
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
            "summary": ["Generated exception contract drift."],
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

    module_content = (
        repo_root / "demo_app/src/demo_app/scientific_calculator.py"
    ).read_text(encoding="utf-8")
    package_content = (repo_root / "demo_app/src/demo_app/__init__.py").read_text(
        encoding="utf-8"
    )
    assert results[-1].status == "passed"
    assert "from e" in module_content
    assert "CalculatorError" in package_content


def test_repair_validation_normalizes_prefix_scientific_calculator(
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
                'select = ["E", "F", "I", "B"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    spec = parse_feature_spec(Path("specs/examples/scientific_calculator.yaml"))
    run_id, run_dir, spec_hash = initialize_run(
        spec,
        Path("specs/examples/scientific_calculator.yaml"),
    )
    files = {
        "demo_app/src/demo_app/scientific_calculator.py": (
            "import math\n\n"
            "ALLOWED_OPERATIONS = {\n"
            "    '/': lambda x, y: x / y if y != 0 else (ValueError, 'bad'),\n"
            "    'log': lambda x: math.log(x),\n"
            "}\n\n"
            "class CalculatorError(Exception):\n"
            "    pass\n\n"
            "def run_scientific_calculator(expression):\n"
            "    try:\n"
            "        tokens = expression.split()\n"
            "        result = ALLOWED_OPERATIONS[tokens[0]](*map(float, tokens[1:]))\n"
            "        return result\n"
            "    except Exception as e:\n"
            "        raise CalculatorError(f'Invalid expression: {str(e)}')\n"
        ),
        "demo_app/src/demo_app/__init__.py": (
            "from .scientific_calculator import run_scientific_calculator\n"
            "\n"
            '__all__ = ["run_scientific_calculator"]\n'
        ),
        "demo_app/src/demo_app/discount_calculator.py": (
            "class DiscountValidationError(Exception):\n"
            "    pass\n\n"
            "def calculate_discounted_price(base_price, discount_percentage):\n"
            "    return base_price * (1 - discount_percentage / 100)\n"
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
            "summary": ["Generated prefix calculator drift."],
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

    target = repo_root / "demo_app/src/demo_app/scientific_calculator.py"
    module_spec = importlib.util.spec_from_file_location("scientific_calculator", target)
    assert module_spec is not None
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(module)

    assert results[-1].status == "passed"
    assert module.run_scientific_calculator("log 10") == 1.0
    assert module.run_scientific_calculator("log", module.math.e) == 1.0
    package_content = (repo_root / "demo_app/src/demo_app/__init__.py").read_text(
        encoding="utf-8"
    )
    assert "calculate_discounted_price" in package_content
    assert "run_scientific_calculator" in package_content
    try:
        module.run_scientific_calculator("/ 1 0")
    except module.CalculatorError:
        pass
    else:
        raise AssertionError("division by zero should raise CalculatorError")
    try:
        module.run_scientific_calculator("/", 1, 0)
    except module.CalculatorError:
        pass
    else:
        raise AssertionError("division by zero should raise CalculatorError")
