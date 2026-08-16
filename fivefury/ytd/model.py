from __future__ import annotations

import dataclasses
from pathlib import Path

from ..authoring.context import BuildContext
from ..authoring.diagnostics import ValidationReport
from ..common import atomic_write_bytes
from ..game_target import GameTarget, coerce_game_target
from .defs import (
    _FORMAT_TO_DX9,
    _FORMAT_TO_RSC8,
    TextureFormat,
    TextureUsage,
    _build_dds_bytes,
    _build_mip_info,
    _total_texture_block_count,
    coerce_texture_usage,
)


@dataclasses.dataclass(slots=True)
class Texture:
    name: str
    width: int
    height: int
    format: TextureFormat
    mip_count: int
    data: bytes
    mip_offsets: tuple[int, ...]
    mip_sizes: tuple[int, ...]
    usage: TextureUsage = TextureUsage.DEFAULT
    usage_flags: int = 0

    @classmethod
    def from_raw(
        cls,
        data: bytes,
        width: int,
        height: int,
        format: TextureFormat,
        mip_count: int,
        *,
        name: str = "",
        mip_offsets: list[int] | tuple[int, ...] | None = None,
        mip_sizes: list[int] | tuple[int, ...] | None = None,
        usage: TextureUsage | int | str = TextureUsage.DEFAULT,
        usage_flags: int = 0,
    ) -> Texture:
        offsets, sizes = _build_mip_info(width, height, format, mip_count)
        if mip_offsets is not None:
            offsets = list(mip_offsets)
        if mip_sizes is not None:
            sizes = list(mip_sizes)
        return cls(
            name=name,
            width=int(width),
            height=int(height),
            format=TextureFormat(format),
            mip_count=int(mip_count),
            data=bytes(data),
            mip_offsets=tuple(int(value) for value in offsets),
            mip_sizes=tuple(int(value) for value in sizes),
            usage=coerce_texture_usage(usage),
            usage_flags=int(usage_flags),
        )

    @property
    def format_name(self) -> str:
        return self.format.name

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        del context
        report = ValidationReport()
        if not self.name:
            report.issue("ytd.texture.name.empty", "Texture name cannot be empty", path="name")
        if self.width <= 0 or self.height <= 0:
            report.issue(
                "ytd.texture.dimensions.invalid",
                f"Texture dimensions must be positive, got {self.width}x{self.height}",
                path="dimensions",
            )
        if self.mip_count <= 0 or self.mip_count > 0xFF:
            report.issue(
                "ytd.texture.mips.count.invalid",
                f"Mip count must fit an unsigned byte, got {self.mip_count}",
                path="mip_count",
            )
        if self.width > 0 and self.height > 0 and self.mip_count > max(self.width, self.height).bit_length():
            report.issue(
                "ytd.texture.mips.count.exceeds_dimensions",
                f"Mip count {self.mip_count} exceeds the chain for {self.width}x{self.height}",
                path="mip_count",
            )
        try:
            texture_format = TextureFormat(self.format)
        except ValueError:
            report.issue(
                "ytd.texture.format.unsupported",
                f"Unsupported texture format: {self.format}",
                path="format",
            )
            return report
        if self.width <= 0 or self.height <= 0 or self.mip_count <= 0:
            return report

        expected_offsets, expected_sizes = _build_mip_info(
            self.width,
            self.height,
            texture_format,
            self.mip_count,
        )
        if self.mip_offsets != tuple(expected_offsets):
            report.issue(
                "ytd.texture.mips.offsets.invalid",
                "Mip offsets must describe one contiguous largest-to-smallest chain",
                path="mip_offsets",
            )
        if self.mip_sizes != tuple(expected_sizes):
            report.issue(
                "ytd.texture.mips.sizes.invalid",
                "Mip sizes do not match the texture dimensions and format",
                path="mip_sizes",
            )
        expected_size = sum(expected_sizes)
        if len(self.data) != expected_size:
            report.issue(
                "ytd.texture.data.size.invalid",
                f"Texture data has {len(self.data)} bytes; expected {expected_size}",
                path="data",
            )
        return report

    def to_dds_bytes(self) -> bytes:
        return _build_dds_bytes(self)

    def save_dds(self, path: str | Path) -> Path:
        return atomic_write_bytes(path, self.to_dds_bytes())


@dataclasses.dataclass(slots=True)
class Ytd:
    textures: list[Texture] = dataclasses.field(default_factory=list)
    game: str | GameTarget = GameTarget.GTA5

    def __len__(self) -> int:
        return len(self.textures)

    def __iter__(self):
        return iter(self.textures)

    def get(self, name: str) -> Texture:
        lower = name.lower()
        for texture in self.textures:
            if texture.name.lower() == lower:
                return texture
        raise KeyError(name)

    def get_texture(self, name: str) -> Texture | None:
        try:
            return self.get(name)
        except KeyError:
            return None

    def texture(self, texture: Texture, *, replace: bool = True) -> Texture:
        existing = self.get_texture(texture.name)
        if existing is not None:
            if not replace:
                raise ValueError(f"Texture '{texture.name}' already exists")
            self.textures = [item for item in self.textures if item.name.lower() != texture.name.lower()]
        self.textures.append(texture)
        return texture

    def remove_texture(self, name: str) -> bool:
        previous = len(self.textures)
        self.textures = [item for item in self.textures if item.name.lower() != str(name).lower()]
        return len(self.textures) != previous

    def build(self) -> Ytd:
        deduped: list[Texture] = []
        seen: set[str] = set()
        for texture in self.textures:
            key = texture.name.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(texture)
        self.textures = deduped
        return self

    def _validate_for_target(self, target: GameTarget) -> ValidationReport:
        report = ValidationReport()
        if not self.textures:
            report.issue("ytd.textures.empty", "YTD must contain at least one texture", path="textures")
        seen: set[str] = set()
        for index, texture in enumerate(self.textures):
            lowered = texture.name.lower()
            if lowered in seen:
                report.issue(
                    "ytd.texture.name.duplicate",
                    f"Texture name '{texture.name}' is duplicated",
                    path=f"textures[{index}].name",
                )
            seen.add(lowered)
            report.extend(texture.validate(), path=f"textures[{index}]")
            maximum_dimension = 0xFFFF if target is GameTarget.GTA5_ENHANCED else 0x7FFF
            if texture.width > maximum_dimension or texture.height > maximum_dimension:
                report.issue(
                    "ytd.texture.dimensions.out_of_range",
                    f"Texture dimensions exceed the {target.value} descriptor limit of {maximum_dimension}",
                    path=f"textures[{index}].dimensions",
                )
            supported_formats = _FORMAT_TO_RSC8 if target is GameTarget.GTA5_ENHANCED else _FORMAT_TO_DX9
            if texture.format not in supported_formats:
                report.issue(
                    "ytd.texture.format.target_unsupported",
                    f"Texture format {texture.format!r} is not supported by {target.value}",
                    path=f"textures[{index}].format",
                )
            if (
                target is GameTarget.GTA5_ENHANCED
                and texture.width > 0
                and texture.height > 0
                and texture.mip_count > 0
                and _total_texture_block_count(
                    texture.width,
                    texture.height,
                    texture.format,
                    texture.mip_count,
                )
                > 0xFFFFFFFF
            ):
                report.issue(
                    "ytd.texture.blocks.out_of_range",
                    "Texture block count exceeds the Enhanced descriptor field",
                    path=f"textures[{index}].data",
                )
        return report

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        target = context.game if context is not None else coerce_game_target(self.game)
        return self._validate_for_target(target)

    def names(self) -> list[str]:
        return [texture.name for texture in self.textures]

    def extract(self, destination: str | Path) -> list[Path]:
        output_dir = Path(destination)
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted: list[Path] = []
        for texture in self.textures:
            extracted.append(texture.save_dds(output_dir / f"{texture.name}.dds"))
        return extracted

    def to_bytes(self, *, game: str | GameTarget | None = None) -> bytes:
        from . import _build_gen9_ytd, _build_legacy_ytd

        target_game = coerce_game_target(game or self.game)
        self._validate_for_target(target_game).raise_for_errors()
        if target_game is GameTarget.GTA5:
            return _build_legacy_ytd(self.textures)
        if target_game is GameTarget.GTA5_ENHANCED:
            return _build_gen9_ytd(self.textures)
        raise ValueError(f"Unsupported YTD target game: {target_game.value}")

    def save(self, path: str | Path, *, game: str | GameTarget | None = None) -> Path:
        return atomic_write_bytes(path, self.to_bytes(game=game))

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> Ytd:
        from . import read_ytd

        return read_ytd(data)


__all__ = ["Texture", "Ytd"]


