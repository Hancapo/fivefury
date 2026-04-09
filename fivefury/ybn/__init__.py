from __future__ import annotations

import dataclasses
from pathlib import Path

from ..bounds import Bound, build_bound_system_data, read_bound_at
from ..resource import RSC7_MAGIC, build_rsc7, split_rsc7_sections

_ROOT_OFFSET = 0x00
_DEFAULT_YBN_VERSION = 43


@dataclasses.dataclass(slots=True)
class Ybn:
    version: int
    bound: Bound
    path: str = ""

    @classmethod
    def from_bound(cls, bound: Bound, *, version: int = _DEFAULT_YBN_VERSION, path: str | Path = "") -> Ybn:
        return cls(version=version, bound=bound, path=str(path) if path else "")

    def to_bytes(self) -> bytes:
        return build_ybn_bytes(self.bound, version=self.version)

    def set_bound(self, bound: Bound) -> Bound:
        self.bound = bound
        return bound

    def build(self) -> "Ybn":
        return self

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.bound is None:
            issues.append("YBN has no root bound")
        return issues

    def save(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.write_bytes(self.to_bytes())
        self.path = str(target)
        return target


def build_ybn_bytes(source: Ybn | Bound, *, version: int = _DEFAULT_YBN_VERSION) -> bytes:
    bound = source.bound if isinstance(source, Ybn) else source
    system_data = build_bound_system_data(bound)
    return build_rsc7(system_data, version=version, system_alignment=0x200)


def save_ybn(source: Ybn | Bound, destination: str | Path, *, version: int = _DEFAULT_YBN_VERSION) -> Path:
    target = Path(destination)
    target.write_bytes(build_ybn_bytes(source, version=version))
    return target


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
    "build_ybn_bytes",
    "read_ybn",
    "save_ybn",
]
