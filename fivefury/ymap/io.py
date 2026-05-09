from __future__ import annotations

from pathlib import Path

from .model import Ymap


def read_ymap(data: bytes) -> Ymap:
    return Ymap.from_bytes(data)


def save_ymap(
    ymap: Ymap,
    path: str | Path | None = None,
    *,
    version: int = 2,
    auto_extents: bool = False,
    auto_flags: bool = True,
) -> Path:
    return ymap.save(path, version=version, auto_extents=auto_extents, auto_flags=auto_flags)


__all__ = ["read_ymap", "save_ymap"]
