from __future__ import annotations

import dataclasses
import struct
from pathlib import Path
from typing import Iterator

from .gamefile import GameFileType, guess_game_file_type
from .resource import split_rsc7_sections, virtual_to_offset
from .ytd import Ytd, read_embedded_texture_dictionary

_DAT_VIRTUAL_BASE = 0x50000000
_SUPPORTED_KINDS = frozenset(
    {
        GameFileType.YDR,
        GameFileType.YDD,
        GameFileType.YFT,
        GameFileType.YPT,
    }
)


@dataclasses.dataclass(slots=True)
class EmbeddedTextureDictionary:
    ytd: Ytd
    label: str = "embedded"
    pointer: int = 0


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError("offset is out of range")
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("offset is out of range")
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 8 > len(data):
        raise ValueError("offset is out of range")
    return struct.unpack_from("<Q", data, offset)[0]


def _coerce_kind(value: GameFileType | str | None, source: bytes | bytearray | memoryview | str | Path) -> GameFileType | None:
    if isinstance(value, GameFileType):
        return value
    if isinstance(value, str) and value:
        return guess_game_file_type(f"x{value}" if value.startswith(".") else f"x.{value}", GameFileType.UNKNOWN)
    if isinstance(source, (str, Path)):
        return guess_game_file_type(source, GameFileType.UNKNOWN)
    return None


def _load_source_bytes(source: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    return bytes(source)


def _virtual_offset(pointer_or_offset: int, data: bytes) -> int:
    value = int(pointer_or_offset)
    offset = virtual_to_offset(value, base=_DAT_VIRTUAL_BASE) if value >= _DAT_VIRTUAL_BASE else value
    if offset < 0 or offset >= len(data):
        raise ValueError("virtual pointer is out of range")
    return offset


def _read_pointer_array(data: bytes, pointer: int, count: int) -> list[int]:
    if not pointer or count <= 0:
        return []
    array_off = _virtual_offset(pointer, data)
    end = array_off + (count * 8)
    if end > len(data):
        raise ValueError("pointer array is truncated")
    return [struct.unpack_from("<Q", data, array_off + (index * 8))[0] for index in range(count)]


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


def _iter_ydr_dict_pointers(data: bytes) -> Iterator[tuple[str, int]]:
    texture_dictionary_pointer = _drawable_texture_dictionary_pointer(data, _DAT_VIRTUAL_BASE)
    if texture_dictionary_pointer:
        yield "embedded", texture_dictionary_pointer


def _iter_ydd_dict_pointers(data: bytes) -> Iterator[tuple[str, int]]:
    count = _u16(data, 0x38)
    drawables_pointer = _u64(data, 0x30)
    for index, drawable_pointer in enumerate(_read_pointer_array(data, drawables_pointer, count)):
        texture_dictionary_pointer = _drawable_texture_dictionary_pointer(data, drawable_pointer)
        if texture_dictionary_pointer:
            yield f"drawable_{index}", texture_dictionary_pointer


def _iter_yft_dict_pointers(data: bytes) -> Iterator[tuple[str, int]]:
    seen: set[int] = set()

    def emit(label: str, drawable_pointer: int) -> Iterator[tuple[str, int]]:
        texture_dictionary_pointer = _drawable_texture_dictionary_pointer(data, drawable_pointer)
        if texture_dictionary_pointer and texture_dictionary_pointer not in seen:
            seen.add(texture_dictionary_pointer)
            yield label, texture_dictionary_pointer

    main_drawable_pointer = _u64(data, 0x30)
    yield from emit("drawable", main_drawable_pointer)

    drawable_array_pointer = _u64(data, 0x38)
    drawable_array_count = _u32(data, 0x48)
    for index, drawable_pointer in enumerate(_read_pointer_array(data, drawable_array_pointer, drawable_array_count)):
        yield from emit(f"drawable_array_{index}", drawable_pointer)

    drawable_cloth_pointer = _u64(data, 0xF8)
    yield from emit("drawable_cloth", drawable_cloth_pointer)


def _iter_ypt_dict_pointers(data: bytes) -> Iterator[tuple[str, int]]:
    texture_dictionary_pointer = _u64(data, 0x20)
    if texture_dictionary_pointer:
        yield "embedded", texture_dictionary_pointer


def iter_embedded_texture_dictionaries(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    kind: GameFileType | str | None = None,
) -> Iterator[EmbeddedTextureDictionary]:
    data = _load_source_bytes(source)
    kind_value = _coerce_kind(kind, source)
    if kind_value not in _SUPPORTED_KINDS:
        return

    header, system_data, graphics_data = split_rsc7_sections(data)
    if kind_value is GameFileType.YDR:
        pointers = _iter_ydr_dict_pointers(system_data)
    elif kind_value is GameFileType.YDD:
        pointers = _iter_ydd_dict_pointers(system_data)
    elif kind_value is GameFileType.YFT:
        pointers = _iter_yft_dict_pointers(system_data)
    else:
        pointers = _iter_ypt_dict_pointers(system_data)

    for label, pointer in pointers:
        try:
            ytd = read_embedded_texture_dictionary(system_data, graphics_data, version=header.version, pointer=pointer)
        except Exception:
            continue
        yield EmbeddedTextureDictionary(ytd=ytd, label=label, pointer=pointer)


def list_embedded_texture_dictionaries(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    kind: GameFileType | str | None = None,
) -> list[EmbeddedTextureDictionary]:
    return list(iter_embedded_texture_dictionaries(source, kind=kind))


__all__ = [
    "EmbeddedTextureDictionary",
    "iter_embedded_texture_dictionaries",
    "list_embedded_texture_dictionaries",
]
