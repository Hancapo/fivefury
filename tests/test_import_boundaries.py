from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "fivefury",
        "fivefury.awc",
        "fivefury.cache",
        "fivefury.cut",
        "fivefury.ycd",
    ],
)
def test_public_packages_import_in_fresh_interpreters(module_name: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
