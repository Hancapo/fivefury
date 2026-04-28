from __future__ import annotations

from pathlib import Path

from ..meta import Meta
from ..meta.resource import MetaResource


class Ymt(MetaResource):
    extension = ".ymt"


def read_ymt(data: bytes | str | Path) -> Ymt:
    if isinstance(data, (str, Path)):
        return Ymt.from_path(data)
    return Ymt.from_bytes(data)


def save_ymt(ymt: Ymt | Meta, path: str | Path | None = None) -> Path:
    resource = ymt if isinstance(ymt, Ymt) else Ymt.from_meta(ymt)
    return resource.save(path)


__all__ = ["Ymt", "read_ymt", "save_ymt"]
