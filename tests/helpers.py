from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def touch(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def reference_root() -> Path:
    configured = os.environ.get("FIVEFURY_REFERENCE_DIR")
    return (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parents[1] / "references"
    )


def configured_path(variable: str, default: str | Path) -> Path:
    return Path(os.environ.get(variable, default)).expanduser()


def require_reference(*parts: str) -> Path:
    path = reference_root().joinpath(*parts)
    if not path.exists():
        pytest.fail(
            f"external reference not available: {path}; "
            "set FIVEFURY_REFERENCE_DIR to the corpus directory"
        )
    return path


def retail_games():
    from fivefury import GameTarget

    games = []
    for edition, variable, target in (
        ("legacy", "FIVEFURY_GTA5_LEGACY_PATH", GameTarget.GTA5),
        ("enhanced", "FIVEFURY_GTA5_ENHANCED_PATH", GameTarget.GTA5_ENHANCED),
    ):
        value = os.environ.get(variable)
        if value:
            games.append((edition, Path(value).expanduser(), target))
    return games or [("unconfigured", None, GameTarget.GTA5)]


def run_python(code: str, *, timeout: float = 15) -> subprocess.CompletedProcess[str]:
    import fivefury

    package_parent = str(Path(fivefury.__file__).resolve().parent.parent)
    bootstrap = f"import sys; sys.path.insert(0, {package_parent!r});\n"
    return subprocess.run(
        [sys.executable, "-I", "-c", bootstrap + code],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
