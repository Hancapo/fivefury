import ast
from pathlib import Path

import pytest


@pytest.fixture
def isolated_suite(pytester):
    source = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    pytester.makeconftest(source)
    pytester.makeini("""
[pytest]
markers =
    integration: external data
    abi: external interpreter
    performance: timings
    requires_platform: OS-specific
""")
    return pytester


def test_default_suite_does_not_run_external_tests(isolated_suite):
    isolated_suite.makepyfile("""
import pytest
def test_unit(): pass
@pytest.mark.integration
def test_external(): raise AssertionError('must not execute by default')
""")
    isolated_suite.runpytest_subprocess("-q").assert_outcomes(passed=1, deselected=1)


def test_explicit_integration_requires_its_inputs(isolated_suite, monkeypatch):
    monkeypatch.delenv("FIVEFURY_POLICY_FIXTURE", raising=False)
    isolated_suite.makepyfile("""
import pytest
@pytest.mark.integration('FIVEFURY_POLICY_FIXTURE')
def test_external(): pass
""")
    result = isolated_suite.runpytest_subprocess("--suite", "integration", "-q")
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(
        ["*Integration prerequisite missing*FIVEFURY_POLICY_FIXTURE*"]
    )


def test_selected_tests_cannot_silently_skip(isolated_suite):
    isolated_suite.makepyfile("""
import pytest
def test_regression(): pytest.skip('API disappeared')
""")
    result = isolated_suite.runpytest_subprocess("-q")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Unexpected skip*"])


def test_suite_selection_can_be_combined(isolated_suite):
    isolated_suite.makepyfile("""
import pytest
def test_unit(): pass
@pytest.mark.abi
def test_abi(): pass
@pytest.mark.integration
def test_external(): pass
""")
    isolated_suite.runpytest_subprocess(
        "--suite", "unit", "--suite", "abi", "-q"
    ).assert_outcomes(passed=2, deselected=1)


def test_suite_sources_do_not_hide_contract_failures():
    forbidden = {
        "pytest.skip",
        "pytest.importorskip",
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "resolve_symbol",
        "call_if_present",
        "import_module_candidates",
    }
    violations = []
    for path in Path(__file__).parent.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if name in forbidden or name.endswith(".skipTest"):
                    violations.append(f"{path.name}:{node.lineno}: {name}")
    assert not violations, "\n".join(violations)
