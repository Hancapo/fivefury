from __future__ import annotations

import pytest

from tests.helpers import run_python


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
    result = run_python(f"import {module_name}")

    assert result.returncode == 0, result.stderr
