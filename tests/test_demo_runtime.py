import os
import subprocess
import sys
from pathlib import Path


def test_demo_app_imports_from_repo_root_without_pytest_pythonpath() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from demo_app import calculate_discounted_price; "
                "print(calculate_discounted_price(100, 15))"
            ),
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "85.0"
