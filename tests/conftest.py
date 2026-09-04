from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import pytest

SUITES = ("unit", "integration", "abi", "performance")
pytest_plugins = ["pytester"]


def pytest_addoption(parser):
    parser.addoption(
        "--suite",
        action="append",
        choices=(*SUITES, "all"),
        help="Select a suite; repeat to combine. Default: unit. External suites require their inputs.",
    )


def suite_of(item):
    return next(
        (
            name
            for name in ("performance", "abi", "integration")
            if item.get_closest_marker(name)
        ),
        "unit",
    )


def pytest_collection_modifyitems(config, items):
    selected = set(config.getoption("suite") or ["unit"])
    if "all" in selected:
        selected.update(SUITES)
    config._suite_inventory = Counter(suite_of(item) for item in items)
    kept, excluded = [], []
    for item in items:
        marker = item.get_closest_marker("requires_platform")
        platform_matches = marker is None or os.name in marker.args
        integration_enabled = (
            not item.get_closest_marker("integration") or "integration" in selected
        )
        (
            kept
            if suite_of(item) in selected and platform_matches and integration_enabled
            else excluded
        ).append(item)
    config.hook.pytest_deselected(items=excluded)
    items[:] = kept


@pytest.fixture(autouse=True)
def external_requirements(request):
    marker = request.node.get_closest_marker("integration")
    if marker:
        for variable in marker.args:
            value = os.environ.get(variable)
            if not value or not Path(value).is_dir():
                pytest.fail(
                    f"Integration prerequisite missing: set {variable} to an existing directory",
                    pytrace=False,
                )
        if "game_path" in request.fixturenames:
            value = request.getfixturevalue("game_path")
            if value is None or not Path(value).is_dir():
                pytest.fail(
                    "Set FIVEFURY_GTA5_LEGACY_PATH or FIVEFURY_GTA5_ENHANCED_PATH for this integration test",
                    pytrace=False,
                )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.skipped:
        report.outcome = "failed"
        report.longrepr = (
            f"Unexpected skip in explicitly selected {suite_of(item)} suite: {item.nodeid}\n"
            f"{report.longrepr}\nFix the dependency or test contract; do not hide it with skip."
        )


def pytest_terminal_summary(terminalreporter, config):
    inventory = getattr(config, "_suite_inventory", {})
    terminalreporter.write_sep("-", "Collected suite inventory (before selection)")
    terminalreporter.write_line(
        ", ".join(f"{name}: {inventory.get(name, 0)}" for name in SUITES)
    )
