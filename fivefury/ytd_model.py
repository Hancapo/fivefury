from __future__ import annotations

import dataclasses
from pathlib import Path

from .ytd_defs import TextureFormat, _build_dds_bytes, _build_mip_info


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
    ) -> "Texture":
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
            mip_count=max(1, int(mip_count)),
            data=bytes(data),
            mip_offsets=tuple(int(value) for value in offsets),
            mip_sizes=tuple(int(value) for value in sizes),
        )

    @property
    def format_name(self) -> str:
        return self.format.name

    def to_dds_bytes(self) -> bytes:
        return _build_dds_bytes(self)

    def save_dds(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_dds_bytes())
        return target


@dataclasses.dataclass(slots=True)
class Ytd:
    textures: list[Texture] = dataclasses.field(default_factory=list)
    game: str = "gta5"

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

    def names(self) -> list[str]:
        return [texture.name for texture in self.textures]

    def extract(self, destination: str | Path) -> list[Path]:
        output_dir = Path(destination)
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted: list[Path] = []
        for texture in self.textures:
            extracted.append(texture.save_dds(output_dir / f"{texture.name}.dds"))
        return extracted

    def to_bytes(self, *, game: str | None = None) -> bytes:
        from .ytd import _build_gen9_ytd, _build_legacy_ytd

        target_game = (game or self.game or "gta5").lower()
        if target_game in {"gta5", "legacy"}:
            return _build_legacy_ytd(self.textures)
        if target_game in {"gta5_enhanced", "gen9", "enhanced"}:
            return _build_gen9_ytd(self.textures)
        raise ValueError(f"Unsupported YTD target game: {target_game}")

    def save(self, path: str | Path, *, game: str | None = None) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_bytes(game=game))
        return target

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> "Ytd":
        from .ytd import read_ytd

        return read_ytd(data)


__all__ = ["Texture", "Ytd"]
