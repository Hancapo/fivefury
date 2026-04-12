from __future__ import annotations

import dataclasses
from pathlib import Path

from ..bounds import Bound, BoundResourcePagesInfo, build_bound_system_layout, read_bound_at
from ..resource import (
    RSC7_MAGIC,
    build_rsc7,
    get_resource_flags_from_block_layout,
    get_resource_total_page_count,
    split_rsc7_sections,
)

_ROOT_OFFSET = 0x00
_DEFAULT_YBN_VERSION = 43


@dataclasses.dataclass(slots=True)
class Ybn:
    version: int
    bound: Bound
    path: str = ""
    system_pages_count: int = 0
    graphics_pages_count: int = 0

    @classmethod
    def from_bound(cls, bound: Bound, *, version: int = _DEFAULT_YBN_VERSION, path: str | Path = "") -> Ybn:
        return cls(version=version, bound=bound, path=str(path) if path else "")

    def to_bytes(self) -> bytes:
        return build_ybn_bytes(self, version=self.version)

    def set_bound(self, bound: Bound) -> Bound:
        self.bound = bound
        return bound

    def build(self) -> "Ybn":
        return self

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.bound is None:
            issues.append("YBN has no root bound")
        pages_info = self.bound.file_pages_info if self.bound is not None else None
        if pages_info is not None:
            system_count_present = self.system_pages_count or pages_info.system_pages_count
            graphics_count_present = self.graphics_pages_count or pages_info.graphics_pages_count
            if system_count_present and pages_info.system_pages_count != self.system_pages_count:
                issues.append("YBN ResourcePagesInfo system page count does not match the RSC7 header")
            if graphics_count_present and pages_info.graphics_pages_count != self.graphics_pages_count:
                issues.append("YBN ResourcePagesInfo graphics page count does not match the RSC7 header")
        return issues

    def save(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.write_bytes(self.to_bytes())
        self.path = str(target)
        return target


def build_ybn_bytes(source: Ybn | Bound, *, version: int | None = None) -> bytes:
    bound = source.bound if isinstance(source, Ybn) else source
    if version is None:
        version = source.version if isinstance(source, Ybn) else _DEFAULT_YBN_VERSION
    version = int(version)
    pages_info = bound.file_pages_info or BoundResourcePagesInfo()
    page_count = 1
    system_flags = None
    system_data = b""
    for _ in range(16):
        root_pages_info = dataclasses.replace(
            pages_info,
            system_pages_count=page_count,
            graphics_pages_count=0,
        )
        system_data, block_sizes = build_bound_system_layout(bound, root_pages_info=root_pages_info)
        system_flags, _ = get_resource_flags_from_block_layout(block_sizes, version=version)
        next_page_count = get_resource_total_page_count(system_flags)
        if next_page_count == page_count:
            break
        page_count = next_page_count
    assert system_flags is not None
    return build_rsc7(system_data, version=version, system_alignment=0x200, system_flags=system_flags)


def save_ybn(source: Ybn | Bound, destination: str | Path, *, version: int | None = None) -> Path:
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
    system_pages_count = get_resource_total_page_count(header.system_flags)
    graphics_pages_count = get_resource_total_page_count(header.graphics_flags)
    return Ybn(
        version=int(header.version),
        bound=read_bound_at(_ROOT_OFFSET, system_data),
        path=str(path or source) if isinstance(source, (str, Path)) or path else "",
        system_pages_count=system_pages_count,
        graphics_pages_count=graphics_pages_count,
    )


__all__ = [
    "Ybn",
    "build_ybn_bytes",
    "read_ybn",
    "save_ybn",
]
