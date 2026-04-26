from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import ClassVar, Iterator

from ..binary import u16 as _u16, u32 as _u32, u64 as _u64
from ..common import ByteSource, read_source_bytes
from ..gamefile import GameFileType, guess_game_file_type
from ..resource import checked_virtual_offset, read_virtual_pointer_array, split_rsc7_sections
from ..ytd import Ytd, read_embedded_texture_dictionary

_DAT_VIRTUAL_BASE = 0x50000000


@dataclasses.dataclass(slots=True)
class EmbeddedTextureDictionary:
    ytd: Ytd
    label: str = "embedded"
    pointer: int = 0

def _coerce_kind(
    value: GameFileType | str | None,
    source: ByteSource,
) -> GameFileType | None:
    if isinstance(value, GameFileType):
        return value
    if isinstance(value, str) and value:
        if value.startswith("."):
            return guess_game_file_type(f"x{value}", GameFileType.UNKNOWN)
        return guess_game_file_type(f"x.{value}", GameFileType.UNKNOWN)
    if isinstance(source, (str, Path)):
        return guess_game_file_type(source, GameFileType.UNKNOWN)
    return None


def _virtual_offset(pointer_or_offset: int, data: bytes) -> int:
    return checked_virtual_offset(pointer_or_offset, data, base=_DAT_VIRTUAL_BASE, allow_plain_offset=True)


def _read_pointer_array(data: bytes, pointer: int, count: int) -> list[int]:
    return read_virtual_pointer_array(data, pointer, count, base=_DAT_VIRTUAL_BASE, allow_plain_offset=True)


def _drawable_texture_dictionary_pointer(data: bytes, drawable_pointer: int) -> int | None:
    if not drawable_pointer:
        return None
    drawable_off = _virtual_offset(drawable_pointer, data)
    shader_group_pointer = _u64(data, drawable_off + 0x10)
    if not shader_group_pointer:
        return None
    shader_group_off = _virtual_offset(shader_group_pointer, data)
    texture_dictionary_pointer = _u64(data, shader_group_off + 0x08)
    return texture_dictionary_pointer or None


@dataclasses.dataclass(slots=True)
class ResourceTextureAsset:
    path: str = ""
    version: int = 0
    system_data: bytes = b""
    graphics_data: bytes = b""

    kind: ClassVar[GameFileType] = GameFileType.UNKNOWN

    @classmethod
    def from_bytes(
        cls,
        data: bytes | bytearray | memoryview,
        *,
        path: str | Path = "",
    ) -> "ResourceTextureAsset":
        header, system_data, graphics_data = split_rsc7_sections(bytes(data))
        return cls(
            path=str(path),
            version=int(header.version),
            system_data=system_data,
            graphics_data=graphics_data,
        )

    @property
    def name(self) -> str:
        return Path(self.path).name if self.path else ""

    @property
    def stem(self) -> str:
        return Path(self.path).stem if self.path else ""

    def iter_texture_dictionary_pointers(self) -> Iterator[tuple[str, int]]:
        raise NotImplementedError

    def iter_embedded_texture_dictionaries(self) -> Iterator[EmbeddedTextureDictionary]:
        for label, pointer in self.iter_texture_dictionary_pointers():
            try:
                ytd = read_embedded_texture_dictionary(
                    self.system_data,
                    self.graphics_data,
                    version=self.version,
                    pointer=pointer,
                )
            except Exception:
                continue
            yield EmbeddedTextureDictionary(ytd=ytd, label=label, pointer=pointer)

    def list_embedded_texture_dictionaries(self) -> list[EmbeddedTextureDictionary]:
        return list(self.iter_embedded_texture_dictionaries())


__all__ = [
    "EmbeddedTextureDictionary",
    "ResourceTextureAsset",
    "_DAT_VIRTUAL_BASE",
    "_coerce_kind",
    "_drawable_texture_dictionary_pointer",
    "_read_pointer_array",
    "_u16",
    "_u32",
    "_u64",
    "_virtual_offset",
]
