from __future__ import annotations

import dataclasses
from pathlib import Path

from ..bounds import (
    Bound,
    BoundResourcePagesInfo,
    build_bound_system_layout,
    get_bound_file_vft_resolver,
    infer_bound_game,
    read_bound_at,
)
from ..common import atomic_write_bytes
from ..game_target import GameTarget, coerce_game_target
from ..resource import (
    RSC7_MAGIC,
    build_rsc7,
    get_resource_total_page_count,
    layout_resource_sections,
    split_rsc7_sections,
)
from .mlo import collision_room_ids, set_collision_room, validate_mlo_collision

_ROOT_OFFSET = 0x00
YBN_VERSION = 43


@dataclasses.dataclass(slots=True)
class Ybn:
    version: int
    bound: Bound
    path: str = ""
    game: GameTarget = GameTarget.GTA5
    system_pages_count: int = 0
    graphics_pages_count: int = 0

    @classmethod
    def from_bound(
        cls,
        bound: Bound,
        *,
        game: str | GameTarget = GameTarget.GTA5,
        version: int = YBN_VERSION,
        path: str | Path = "",
    ) -> Ybn:
        return cls(
            version=version,
            bound=bound,
            path=str(path) if path else "",
            game=coerce_game_target(game),
        )

    def to_bytes(self) -> bytes:
        return build_ybn_bytes(self, game=self.game, version=self.version)

    def build(self) -> Ybn:
        self.bound = self.bound.build()
        return self

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.bound is None:
            issues.append("YBN has no root bound")
        if self.bound is not None:
            issues.extend(self.bound.validate())
        pages_info = self.bound.file_pages_info if self.bound is not None else None
        if pages_info is not None:
            system_count_present = self.system_pages_count or pages_info.system_pages_count
            graphics_count_present = self.graphics_pages_count or pages_info.graphics_pages_count
            if system_count_present and pages_info.system_pages_count != self.system_pages_count:
                issues.append("YBN ResourcePagesInfo system page count does not match the RSC7 header")
            if graphics_count_present and pages_info.graphics_pages_count != self.graphics_pages_count:
                issues.append("YBN ResourcePagesInfo graphics page count does not match the RSC7 header")
        return issues

    @property
    def room_ids(self) -> frozenset[int]:
        return collision_room_ids(self)

    def bind_room(self, room_id: int) -> Ybn:
        set_collision_room(self, room_id)
        return self

    def validate_mlo(self, archetype: object) -> list[str]:
        return validate_mlo_collision(self, archetype)

    def save(self, destination: str | Path) -> Path:
        target = atomic_write_bytes(destination, self.to_bytes())
        self.path = str(target)
        return target


def build_ybn_bytes(
    source: Ybn | Bound,
    *,
    game: str | GameTarget | None = None,
    version: int | None = None,
) -> bytes:
    bound = source.bound if isinstance(source, Ybn) else source
    bound = bound.build()
    if version is None:
        version = source.version if isinstance(source, Ybn) else YBN_VERSION
    version = int(version)
    if version != YBN_VERSION:
        raise ValueError(f"YBN resources require version {YBN_VERSION}, got {version}")
    target = coerce_game_target(
        game if game is not None else source.game if isinstance(source, Ybn) else GameTarget.GTA5
    )
    file_vft_resolver = get_bound_file_vft_resolver(target)
    issues = bound.validate()
    if issues:
        issue_lines = "\n".join(f"- {issue}" for issue in issues)
        raise ValueError(f"cannot build invalid YBN bound:\n{issue_lines}")
    pages_info = bound.file_pages_info or BoundResourcePagesInfo()
    page_count = 1
    system_flags = None
    graphics_flags = None
    system_data = b""
    prepared_bvhs = {}
    for _ in range(16):
        root_pages_info = dataclasses.replace(
            pages_info,
            system_pages_count=page_count,
            graphics_pages_count=0,
        )
        raw_system_data, block_spans = build_bound_system_layout(
            bound,
            root_pages_info=root_pages_info,
            file_vft_resolver=file_vft_resolver,
            _prepared_bvhs=prepared_bvhs,
        )
        system_data, _, system_flags, graphics_flags = layout_resource_sections(
            raw_system_data,
            block_spans,
            version=version,
        )
        next_page_count = get_resource_total_page_count(system_flags)
        if next_page_count == page_count:
            break
        page_count = next_page_count
    assert system_flags is not None
    assert graphics_flags is not None
    return build_rsc7(system_data, version=version, system_flags=system_flags, graphics_flags=graphics_flags)


def save_ybn(
    source: Ybn | Bound,
    destination: str | Path,
    *,
    game: str | GameTarget | None = None,
    version: int | None = None,
) -> Path:
    return atomic_write_bytes(destination, build_ybn_bytes(source, game=game, version=version))


def read_ybn(source: bytes | bytearray | memoryview | str | Path, *, path: str | Path = "") -> Ybn:
    data = Path(source).read_bytes() if isinstance(source, (str, Path)) else bytes(source)
    if len(data) < 16:
        raise ValueError("YBN data is too short")
    if int.from_bytes(data[:4], "little") != RSC7_MAGIC:
        raise ValueError("YBN data must be a standalone RSC7 resource")
    header, system_data, _ = split_rsc7_sections(data)
    system_pages_count = get_resource_total_page_count(header.system_flags)
    graphics_pages_count = get_resource_total_page_count(header.graphics_flags)
    ybn = Ybn(
        version=int(header.version),
        bound=read_bound_at(_ROOT_OFFSET, system_data),
        path=str(path or source) if isinstance(source, (str, Path)) or path else "",
        game=infer_bound_game(int.from_bytes(system_data[_ROOT_OFFSET : _ROOT_OFFSET + 4], "little")),
        system_pages_count=system_pages_count,
        graphics_pages_count=graphics_pages_count,
    )
    ybn.build()
    return ybn


__all__ = [
    "YBN_VERSION",
    "Ybn",
    "build_ybn_bytes",
    "collision_room_ids",
    "read_ybn",
    "save_ybn",
    "set_collision_room",
    "validate_mlo_collision",
]
