from __future__ import annotations

from pathlib import Path

from ..meta import Meta
from ..meta.resource import MetaResource


class Ymf(MetaResource):
    extension = ".ymf"


def read_ymf(data: bytes | str | Path) -> Ymf:
    if isinstance(data, (str, Path)):
        return Ymf.from_path(data)
    return Ymf.from_bytes(data)


def save_ymf(ymf: Ymf | Meta, path: str | Path | None = None) -> Path:
    resource = ymf if isinstance(ymf, Ymf) else Ymf.from_meta(ymf)
    return resource.save(path)


__all__ = ["Ymf", "read_ymf", "save_ymf"]
