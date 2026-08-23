from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .utils import _is_rpf7, _is_rsc7


class RpfSourceKind(str, Enum):
    RAW = "raw"
    DEFLATE = "deflate"
    RSC7 = "rsc7"
    RPF7 = "rpf7"


@dataclass(frozen=True, slots=True)
class RpfFileSource:
    """Explicit file-backed payload used by the streaming RPF writer."""

    path: Path
    kind: RpfSourceKind
    compression_level: int = 9
    size: int = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RpfSourceKind):
            raise TypeError("kind must be an RpfSourceKind")
        source = Path(self.path).resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"RPF source path must be a file: {source}")
        with source.open("rb") as stream:
            magic = stream.read(4)
        if self.kind is RpfSourceKind.RSC7 and not _is_rsc7(magic):
            raise ValueError(f"RSC7 source does not start with an RSC7 header: {source}")
        if self.kind is RpfSourceKind.RPF7 and not _is_rpf7(magic):
            raise ValueError(f"RPF7 source does not start with an RPF7 header: {source}")
        if not 0 <= self.compression_level <= 9:
            raise ValueError("compression_level must be between 0 and 9")
        object.__setattr__(self, "path", source)
        object.__setattr__(self, "size", source.stat().st_size)

    @classmethod
    def raw(cls, path: str | Path) -> RpfFileSource:
        return cls(Path(path), RpfSourceKind.RAW)

    @classmethod
    def compressed(cls, path: str | Path, *, level: int = 9) -> RpfFileSource:
        return cls(Path(path), RpfSourceKind.DEFLATE, compression_level=level)

    @classmethod
    def resource(cls, path: str | Path) -> RpfFileSource:
        return cls(Path(path), RpfSourceKind.RSC7)

    @classmethod
    def archive(cls, path: str | Path) -> RpfFileSource:
        return cls(Path(path), RpfSourceKind.RPF7)


def _detect_file_source(path: str | Path) -> RpfFileSource:
    source = Path(path).resolve(strict=True)
    with source.open("rb") as stream:
        magic = stream.read(4)
    if _is_rpf7(magic):
        return RpfFileSource.archive(source)
    if _is_rsc7(magic):
        return RpfFileSource.resource(source)
    return RpfFileSource.raw(source)


__all__ = ["RpfFileSource", "RpfSourceKind"]
