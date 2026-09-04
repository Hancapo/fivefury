"""Run the repository test suite against an isolated wheel installation."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BOOTSTRAP = """
import sys
from pathlib import Path
package_target, test_root, *pytest_args = sys.argv[1:]
sys.path[:0] = [package_target, test_root]
import fivefury
loaded = Path(fivefury.__file__).resolve()
assert loaded.is_relative_to(Path(package_target).resolve()), loaded
print('Testing installed wheel:', loaded, flush=True)
import pytest
raise SystemExit(pytest.main([str(Path(test_root) / 'tests'), *pytest_args]))
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--junitxml", type=Path)
    args, pytest_args = parser.parse_known_args()
    args.python = str(
        Path(shutil.which(args.python) or args.python).resolve(strict=True)
    )
    wheel = args.wheel.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    if args.junitxml:
        report = args.junitxml.resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        pytest_args.append(f"--junitxml={report}")
    with tempfile.TemporaryDirectory(prefix="fivefury-wheel-tests-") as temporary:
        root = Path(temporary)
        target = root / "installed"
        suite = root / "suite"
        subprocess.run(
            [
                args.python,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-compile",
                "--target",
                str(target),
                str(wheel),
            ],
            check=True,
        )
        shutil.copytree(
            repo / "tests",
            suite / "tests",
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
        )
        shutil.copy2(repo / "pyproject.toml", suite / "pyproject.toml")
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        result = subprocess.run(
            [args.python, "-I", "-c", BOOTSTRAP, str(target), str(suite), *pytest_args],
            cwd=suite,
            env=environment,
            check=False,
        )
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
