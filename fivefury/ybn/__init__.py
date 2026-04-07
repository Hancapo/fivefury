from __future__ import annotations

import dataclasses
from pathlib import Path

from ..bounds import Bound, read_bound_at
from ..resource import RSC7_MAGIC, split_rsc7_sections

_ROOT_OFFSET = 0x00


@dataclasses.dataclass(slots=True)
class Ybn:
    version: int
    bound: Bound
    path: str = ""


def read_ybn(source: bytes | bytearray | memoryview | str | Path, *, path: str | Path = "") -> Ybn:
    data = Path(source).read_bytes() if isinstance(source, (str, Path)) else bytes(source)
    if len(data) < 16:
        raise ValueError("YBN data is too short")
    if int.from_bytes(data[:4], "little") != RSC7_MAGIC:
        raise ValueError("YBN data must be a standalone RSC7 resource")
    header, system_data, _ = split_rsc7_sections(data)
    return Ybn(
        version=int(header.version),
        bound=read_bound_at(_ROOT_OFFSET, system_data),
        path=str(path or source) if isinstance(source, (str, Path)) or path else "",
    )


__all__ = [
    "Ybn",
    "read_ybn",
]
