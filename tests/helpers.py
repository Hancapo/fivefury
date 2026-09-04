from __future__ import annotations

import os
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
        pytest.skip(
            f"external reference not available: {path}; "
            "set FIVEFURY_REFERENCE_DIR to the corpus directory"
        )
    return path
