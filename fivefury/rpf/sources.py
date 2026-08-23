from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .utils import _is_rpf7


@dataclass(frozen=True, slots=True)
class RpfFileSource:
    """Immutable path-backed RPF payload for streaming into another archive."""

    path: Path
    size: int = field(init=False)

    def __post_init__(self) -> None:
        source = Path(self.path).resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"RPF source path must be a file: {source}")
        with source.open("rb") as stream:
            magic = stream.read(4)
        if not _is_rpf7(magic):
            raise ValueError(f"RPF source does not start with an RPF7 header: {source}")
        object.__setattr__(self, "path", source)
        object.__setattr__(self, "size", source.stat().st_size)


__all__ = ["RpfFileSource"]
