from __future__ import annotations

import dataclasses
import struct
from pathlib import Path

from ..binary import read_c_string
from ..hashing import jenk_hash
from ..resource import (
    RSC7_MAGIC,
    physical_to_offset,
    split_rsc7_sections,
    virtual_to_offset,
)
from .defs import (
    _GEN9_TEXTURE_DICTIONARY_VERSIONS,
    _RSC8_TO_FORMAT,
    DAT_PHYSICAL_BASE,
    DAT_VIRTUAL_BASE,
    TextureFormat,
    TextureUsage,
    _resolve_legacy_format,
    _total_mip_data_size,
    unpack_usage_data,
)


@dataclasses.dataclass(frozen=True, slots=True)
class TextureDescriptor:
    name: str
    name_hash: int
    width: int
    height: int
    format: TextureFormat
    mip_count: int
    usage: TextureUsage
    usage_flags: int
    data_size: int
    index: int
    game: str


@dataclasses.dataclass(frozen=True, slots=True)
class YtdCatalog:
    textures: tuple[TextureDescriptor, ...]
    game: str

    def __len__(self) -> int:
        return len(self.textures)

    def __iter__(self):
        return iter(self.textures)

    def names(self) -> tuple[str, ...]:
        return tuple(texture.name for texture in self.textures)

    def find(self, value: str | int) -> TextureDescriptor | None:
        target_hash = int(value) & 0xFFFFFFFF if isinstance(value, int) else jenk_hash(value)
        for texture in self.textures:
            if texture.name_hash == target_hash:
                return texture
        return None

    def get(self, value: str | int) -> TextureDescriptor:
        texture = self.find(value)
        if texture is None:
            raise KeyError(value)
        return texture


@dataclasses.dataclass(frozen=True, slots=True)
class _TextureStorageDescriptor:
    descriptor: TextureDescriptor
    data_offset: int


def _virtual_offset(pointer: int) -> int:
    return virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE)


def _physical_offset(pointer: int) -> int:
    return physical_to_offset(pointer, base=DAT_PHYSICAL_BASE)


def _checked_dictionary_items(system_data: bytes, offset: int) -> tuple[int, int]:
    if offset < 0 or offset + 0x40 > len(system_data):
        raise ValueError("Texture dictionary offset is out of range")
    count = struct.unpack_from("<H", system_data, offset + 0x28)[0]
    items_pointer = struct.unpack_from("<Q", system_data, offset + 0x30)[0]
    items_offset = _virtual_offset(items_pointer)
    if count > 0x4000 or items_offset < 0 or items_offset + count * 8 > len(system_data):
        raise ValueError("Texture dictionary has an invalid item table")
    return count, items_offset


def _checked_texture_offset(system_data: bytes, items_offset: int, index: int, minimum_size: int) -> int:
    pointer = struct.unpack_from("<Q", system_data, items_offset + index * 8)[0]
    offset = _virtual_offset(pointer)
    if offset < 0 or offset + minimum_size > len(system_data):
        raise ValueError("Texture dictionary contains an invalid texture pointer")
    return offset


def _checked_texture_name(system_data: bytes, pointer: int) -> str:
    offset = _virtual_offset(pointer)
    if offset < 0 or offset >= len(system_data):
        raise ValueError("Texture dictionary contains an invalid name pointer")
    return read_c_string(system_data, offset)


def _read_legacy_texture_descriptors(
    system_data: bytes,
    offset: int = 0,
) -> tuple[_TextureStorageDescriptor, ...]:
    count, items_offset = _checked_dictionary_items(system_data, offset)
    entries: list[_TextureStorageDescriptor] = []
    for index in range(count):
        texture_offset = _checked_texture_offset(system_data, items_offset, index, 0x78)
        name = _checked_texture_name(system_data, struct.unpack_from("<Q", system_data, texture_offset + 0x28)[0])
        width, height = struct.unpack_from("<hh", system_data, texture_offset + 0x50)
        format_value = struct.unpack_from("<I", system_data, texture_offset + 0x58)[0]
        mip_count = system_data[texture_offset + 0x5D]
        usage, usage_flags = unpack_usage_data(struct.unpack_from("<I", system_data, texture_offset + 0x40)[0])
        texture_format = _resolve_legacy_format(format_value)
        if width <= 0 or height <= 0 or mip_count <= 0 or texture_format is None:
            raise ValueError(f"Legacy texture dictionary contains invalid metadata for '{name}'")
        data_size = _total_mip_data_size(width, height, texture_format, mip_count)
        entries.append(
            _TextureStorageDescriptor(
                TextureDescriptor(
                    name=name,
                    name_hash=jenk_hash(name),
                    width=width,
                    height=height,
                    format=texture_format,
                    mip_count=mip_count,
                    usage=usage,
                    usage_flags=usage_flags,
                    data_size=data_size,
                    index=index,
                    game="gta5",
                ),
                _physical_offset(struct.unpack_from("<Q", system_data, texture_offset + 0x70)[0]),
            )
        )
    return tuple(entries)


def _read_gen9_texture_descriptors(
    system_data: bytes,
    offset: int = 0,
) -> tuple[_TextureStorageDescriptor, ...]:
    count, items_offset = _checked_dictionary_items(system_data, offset)
    entries: list[_TextureStorageDescriptor] = []
    for index in range(count):
        texture_offset = _checked_texture_offset(system_data, items_offset, index, 0x48)
        name = _checked_texture_name(system_data, struct.unpack_from("<Q", system_data, texture_offset + 0x28)[0])
        width, height = struct.unpack_from("<HH", system_data, texture_offset + 0x18)
        format_value = system_data[texture_offset + 0x1F]
        mip_count = system_data[texture_offset + 0x22]
        usage, usage_flags = unpack_usage_data(struct.unpack_from("<I", system_data, texture_offset + 0x40)[0])
        texture_format = _RSC8_TO_FORMAT.get(format_value)
        if width <= 0 or height <= 0 or mip_count <= 0 or texture_format is None:
            raise ValueError(f"Enhanced texture dictionary contains invalid metadata for '{name}'")
        data_size = _total_mip_data_size(width, height, texture_format, mip_count)
        entries.append(
            _TextureStorageDescriptor(
                TextureDescriptor(
                    name=name,
                    name_hash=jenk_hash(name),
                    width=width,
                    height=height,
                    format=texture_format,
                    mip_count=mip_count,
                    usage=usage,
                    usage_flags=usage_flags,
                    data_size=data_size,
                    index=index,
                    game="gta5_enhanced",
                ),
                _physical_offset(struct.unpack_from("<Q", system_data, texture_offset + 0x38)[0]),
            )
        )
    return tuple(entries)


def _read_texture_descriptors(
    system_data: bytes,
    *,
    version: int,
    offset: int = 0,
) -> tuple[_TextureStorageDescriptor, ...]:
    readers = (
        (_read_gen9_texture_descriptors, _read_legacy_texture_descriptors)
        if version in _GEN9_TEXTURE_DICTIONARY_VERSIONS
        else (_read_legacy_texture_descriptors, _read_gen9_texture_descriptors)
    )
    errors: list[Exception] = []
    for reader in readers:
        try:
            return reader(system_data, offset)
        except (ValueError, struct.error) as exc:
            errors.append(exc)
    raise ValueError("Unsupported texture dictionary layout") from errors[-1]


def read_embedded_ytd_catalog(
    system_data: bytes | bytearray | memoryview,
    *,
    version: int,
    offset: int = 0,
) -> YtdCatalog:
    entries = _read_texture_descriptors(bytes(system_data), version=int(version), offset=int(offset))
    game = entries[0].descriptor.game if entries else (
        "gta5_enhanced" if int(version) in _GEN9_TEXTURE_DICTIONARY_VERSIONS else "gta5"
    )
    return YtdCatalog(tuple(entry.descriptor for entry in entries), game)


def read_ytd_catalog(source: bytes | bytearray | memoryview | str | Path) -> YtdCatalog:
    data = Path(source).read_bytes() if isinstance(source, (str, Path)) else bytes(source)
    if len(data) < 16 or struct.unpack_from("<I", data, 0)[0] != RSC7_MAGIC:
        raise ValueError("YTD data must be a standalone RSC7 resource")
    header, system_data, _graphics_data = split_rsc7_sections(data)
    return read_embedded_ytd_catalog(system_data, version=header.version)


__all__ = [
    "TextureDescriptor",
    "YtdCatalog",
    "read_embedded_ytd_catalog",
    "read_ytd_catalog",
]
