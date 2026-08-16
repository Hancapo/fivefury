from __future__ import annotations

import struct
from pathlib import Path

from ..binary import align
from ..hashing import jenk_hash
from ..resource import (
    RSC7_MAGIC,
    ResourceHeader,
    build_rsc7,
    physical_to_offset,
    split_rsc7_sections,
    virtual_to_offset,
)
from .catalog import (
    TextureDescriptor,
    YtdCatalog,
    _read_texture_descriptors,
    read_embedded_ytd_catalog,
    read_ytd_catalog,
)
from .defs import (
    _BLOCK_BYTES,
    _ENHANCED_DIM_2D,
    _ENHANCED_TEX_SIZE,
    _FORMAT_TO_DX9,
    _FORMAT_TO_RSC8,
    _GEN9_TEXTURE_DICTIONARY_VERSIONS,
    _GTAV_TEX_SIZE,
    _LEGACY_TEXTURE_DICTIONARY_VERSIONS,
    _YTD_RSC7_VERSION_GEN9,
    _YTD_RSC7_VERSION_LEGACY,
    DAT_PHYSICAL_BASE,
    DAT_VIRTUAL_BASE,
    TextureFormat,
    TextureUsage,
    _is_block_compressed,
    _row_pitch,
    _total_texture_block_count,
    coerce_texture_usage,
    pack_usage_data,
    unpack_usage_data,
)
from .model import Texture, Ytd
from .runtime_headers import GEN9_TEXTURE_RUNTIME_PROFILE


def _v2o(address: int) -> int:
    return virtual_to_offset(address, base=DAT_VIRTUAL_BASE)


def _p2o(address: int) -> int:
    return physical_to_offset(address, base=DAT_PHYSICAL_BASE)


def _split_rsc7_sections(data: bytes) -> tuple[ResourceHeader, bytes, bytes]:
    return split_rsc7_sections(data)


def _is_valid_virtual_ptr(value: int, system_data: bytes) -> bool:
    return DAT_VIRTUAL_BASE <= int(value) < (DAT_VIRTUAL_BASE + len(system_data))


def _prefer_gen9_dictionary(version: int) -> bool | None:
    if version in _GEN9_TEXTURE_DICTIONARY_VERSIONS:
        return True
    if version in _LEGACY_TEXTURE_DICTIONARY_VERSIONS:
        return False
    return None


def _select_texture_dictionary_parser(system_data: bytes, graphics_data: bytes, dict_off: int, version: int) -> str:
    order: list[str]
    prefer_gen9 = _prefer_gen9_dictionary(version)
    if prefer_gen9 is True:
        order = ["gen9", "legacy"]
    elif prefer_gen9 is False:
        order = ["legacy", "gen9"]
    else:
        order = ["legacy", "gen9"]
    for variant in order:
        try:
            if variant == "legacy":
                _parse_legacy_texture_dictionary_at(system_data, graphics_data, dict_off)
            else:
                _parse_gen9_texture_dictionary_at(system_data, graphics_data, dict_off)
            return variant
        except (ValueError, struct.error):
            continue
    raise ValueError("Unsupported embedded texture dictionary layout")


def _parse_legacy_texture_dictionary_at(virtual_data: bytes, physical_data: bytes, dict_off: int) -> Ytd:
    ytd = Ytd(game="gta5")
    for entry in _read_texture_descriptors(virtual_data, version=_YTD_RSC7_VERSION_LEGACY, offset=dict_off):
        descriptor = entry.descriptor
        phys_off = entry.data_offset
        data_size = descriptor.data_size
        if phys_off < 0:
            raise ValueError("Legacy texture pixel data is out of range")
        if phys_off < len(physical_data):
            pixel_data = physical_data[phys_off : phys_off + data_size]
        elif len(virtual_data) >= data_size:
            pixel_data = virtual_data[-data_size:]
        else:
            raise ValueError("Legacy texture pixel data is out of range")
        ytd.textures.append(
            Texture.from_raw(
                pixel_data,
                descriptor.width,
                descriptor.height,
                descriptor.format,
                descriptor.mip_count,
                name=descriptor.name,
                usage=descriptor.usage,
                usage_flags=descriptor.usage_flags,
            )
        )
    return ytd


def _parse_gen9_texture_dictionary_at(virtual_data: bytes, physical_data: bytes, dict_off: int) -> Ytd:
    ytd = Ytd(game="gta5_enhanced")
    for entry in _read_texture_descriptors(virtual_data, version=_YTD_RSC7_VERSION_GEN9, offset=dict_off):
        descriptor = entry.descriptor
        phys_off = entry.data_offset
        data_size = descriptor.data_size
        if phys_off < 0:
            raise ValueError("Gen9 texture pixel data is out of range")
        if phys_off < len(physical_data):
            pixel_data = physical_data[phys_off : phys_off + data_size]
        elif len(virtual_data) >= data_size:
            pixel_data = virtual_data[-data_size:]
        else:
            raise ValueError("Gen9 texture pixel data is out of range")
        ytd.textures.append(
            Texture.from_raw(
                pixel_data,
                descriptor.width,
                descriptor.height,
                descriptor.format,
                descriptor.mip_count,
                name=descriptor.name,
                usage=descriptor.usage,
                usage_flags=descriptor.usage_flags,
            )
        )
    return ytd


def _parse_legacy_ytd(data: bytes) -> Ytd:
    _, virtual_data, physical_data = _split_rsc7_sections(data)
    return _parse_legacy_texture_dictionary_at(virtual_data, physical_data, 0)


def _parse_gen9_ytd(data: bytes) -> Ytd:
    _, virtual_data, physical_data = _split_rsc7_sections(data)
    return _parse_gen9_texture_dictionary_at(virtual_data, physical_data, 0)


def _build_legacy_ytd(textures: list[Texture]) -> bytes:
    if not textures:
        raise ValueError("Cannot build a YTD with zero textures")
    entries = sorted(textures, key=lambda item: jenk_hash(item.name))
    count = len(entries)

    dict_size = 0x40
    keys_offset = dict_size
    ptrs_offset = align(keys_offset + (4 * count), 16)
    textures_offset = align(ptrs_offset + (8 * count), 16)

    current = textures_offset + (_GTAV_TEX_SIZE * count)
    name_offsets: list[int] = []
    name_bytes: list[bytes] = []
    for texture in entries:
        encoded = texture.name.encode("utf-8") + b"\x00"
        name_offsets.append(current)
        name_bytes.append(encoded)
        current += len(encoded)

    pagemap_offset = align(current, 16)
    virtual_size = pagemap_offset + 0x10
    vbuf = bytearray(virtual_size)

    physical_offsets: list[int] = []
    physical_cursor = 0
    for texture in entries:
        physical_offsets.append(physical_cursor)
        physical_cursor += len(texture.data)
    pbuf = bytearray(physical_cursor)

    struct.pack_into("<Q", vbuf, 0x00, 0)
    struct.pack_into("<Q", vbuf, 0x08, DAT_VIRTUAL_BASE + pagemap_offset)
    struct.pack_into("<Q", vbuf, 0x10, 0)
    struct.pack_into("<I", vbuf, 0x18, 1)
    struct.pack_into("<I", vbuf, 0x1C, 0)
    struct.pack_into("<Q", vbuf, 0x20, DAT_VIRTUAL_BASE + keys_offset)
    struct.pack_into("<HHI", vbuf, 0x28, count, count, 0)
    struct.pack_into("<Q", vbuf, 0x30, DAT_VIRTUAL_BASE + ptrs_offset)
    struct.pack_into("<HHI", vbuf, 0x38, count, count, 0)

    for index, texture in enumerate(entries):
        struct.pack_into("<I", vbuf, keys_offset + (index * 4), jenk_hash(texture.name))
        struct.pack_into("<Q", vbuf, ptrs_offset + (index * 8), DAT_VIRTUAL_BASE + textures_offset + (_GTAV_TEX_SIZE * index))

        off = textures_offset + (_GTAV_TEX_SIZE * index)
        format_value = _FORMAT_TO_DX9[texture.format]
        stride = _row_pitch(texture.width, texture.format)

        struct.pack_into("<Q", vbuf, off + 0x28, DAT_VIRTUAL_BASE + name_offsets[index])
        struct.pack_into("<h", vbuf, off + 0x30, 1)
        struct.pack_into("<I", vbuf, off + 0x40, pack_usage_data(texture.usage, texture.usage_flags))
        struct.pack_into("<h", vbuf, off + 0x50, texture.width)
        struct.pack_into("<h", vbuf, off + 0x52, texture.height)
        struct.pack_into("<h", vbuf, off + 0x54, 1)
        struct.pack_into("<h", vbuf, off + 0x56, stride)
        struct.pack_into("<I", vbuf, off + 0x58, format_value)
        struct.pack_into("<B", vbuf, off + 0x5D, texture.mip_count)
        struct.pack_into("<Q", vbuf, off + 0x70, DAT_PHYSICAL_BASE + physical_offsets[index])

        encoded_name = name_bytes[index]
        start = name_offsets[index]
        vbuf[start : start + len(encoded_name)] = encoded_name
        pbuf[physical_offsets[index] : physical_offsets[index] + len(texture.data)] = texture.data

    vbuf[pagemap_offset] = 1
    vbuf[pagemap_offset + 1] = 1
    return build_rsc7(bytes(vbuf), version=_YTD_RSC7_VERSION_LEGACY, graphics_data=bytes(pbuf))


def _build_gen9_ytd(textures: list[Texture]) -> bytes:
    if not textures:
        raise ValueError("Cannot build a YTD with zero textures")
    entries = sorted(textures, key=lambda item: jenk_hash(item.name))
    count = len(entries)
    profile = GEN9_TEXTURE_RUNTIME_PROFILE

    dict_size = 0x40
    keys_offset = dict_size
    ptrs_offset = align(keys_offset + (4 * count), 16)
    textures_offset = align(ptrs_offset + (8 * count), 16)
    current = textures_offset + (_ENHANCED_TEX_SIZE * count)

    name_offsets: list[int] = []
    name_bytes: list[bytes] = []
    for texture in entries:
        encoded = texture.name.encode("utf-8") + b"\x00"
        name_offsets.append(current)
        name_bytes.append(encoded)
        current += len(encoded)

    pagemap_offset = align(current, 16)
    virtual_size = pagemap_offset + 0x10

    physical_offsets: list[int] = []
    physical_blocks: list[bytes] = []
    physical_cursor = 0
    for texture in entries:
        physical_offsets.append(physical_cursor)
        data = texture.data
        physical_blocks.append(data)
        physical_cursor = align(physical_cursor + len(data), 16)

    vbuf = bytearray(virtual_size)
    pbuf = bytearray(physical_cursor)

    struct.pack_into("<Q", vbuf, 0x00, 0)
    struct.pack_into("<Q", vbuf, 0x08, DAT_VIRTUAL_BASE + pagemap_offset)
    struct.pack_into("<Q", vbuf, 0x10, 0)
    struct.pack_into("<I", vbuf, 0x18, 1)
    struct.pack_into("<I", vbuf, 0x1C, 0)
    struct.pack_into("<Q", vbuf, 0x20, DAT_VIRTUAL_BASE + keys_offset)
    struct.pack_into("<HHI", vbuf, 0x28, count, count, 0)
    struct.pack_into("<Q", vbuf, 0x30, DAT_VIRTUAL_BASE + ptrs_offset)
    struct.pack_into("<HHI", vbuf, 0x38, count, count, 0)

    for index, texture in enumerate(entries):
        struct.pack_into("<I", vbuf, keys_offset + (index * 4), jenk_hash(texture.name))
        struct.pack_into("<Q", vbuf, ptrs_offset + (index * 8), DAT_VIRTUAL_BASE + textures_offset + (_ENHANCED_TEX_SIZE * index))

        off = textures_offset + (_ENHANCED_TEX_SIZE * index)
        block_stride = 4 if not _is_block_compressed(texture.format) else _BLOCK_BYTES[texture.format]
        block_count = _total_texture_block_count(
            texture.width,
            texture.height,
            texture.format,
            texture.mip_count,
        )

        struct.pack_into("<Q", vbuf, off + 0x00, profile.texture_vft)
        struct.pack_into("<II", vbuf, off + 0x08, block_count, block_stride)
        struct.pack_into("<II", vbuf, off + 0x10, profile.descriptor_flags, 0)
        struct.pack_into("<HHH", vbuf, off + 0x18, texture.width, texture.height, 1)
        vbuf[off + 0x1E] = _ENHANCED_DIM_2D
        vbuf[off + 0x1F] = _FORMAT_TO_RSC8[texture.format]
        vbuf[off + 0x20] = profile.tile_mode
        vbuf[off + 0x22] = texture.mip_count
        vbuf[off + 0x23] = profile.image_flags
        struct.pack_into("<H", vbuf, off + 0x26, 1)
        struct.pack_into("<Q", vbuf, off + 0x28, DAT_VIRTUAL_BASE + name_offsets[index])
        struct.pack_into("<Q", vbuf, off + 0x30, DAT_VIRTUAL_BASE + off + 0x58)
        struct.pack_into("<Q", vbuf, off + 0x38, DAT_PHYSICAL_BASE + physical_offsets[index])
        struct.pack_into(
            "<II",
            vbuf,
            off + 0x40,
            pack_usage_data(texture.usage, texture.usage_flags),
            profile.usage_class,
        )
        struct.pack_into("<Q", vbuf, off + 0x58, profile.srv_vft)
        struct.pack_into("<HHI", vbuf, off + 0x68, profile.srv_dimension, 0xFFFF, 0xFFFFFFFF)

        encoded_name = name_bytes[index]
        start = name_offsets[index]
        vbuf[start : start + len(encoded_name)] = encoded_name
        data = physical_blocks[index]
        pbuf[physical_offsets[index] : physical_offsets[index] + len(data)] = data

    vbuf[pagemap_offset] = 1
    vbuf[pagemap_offset + 1] = 1
    return build_rsc7(bytes(vbuf), version=_YTD_RSC7_VERSION_GEN9, graphics_data=bytes(pbuf))


def read_embedded_texture_dictionary(
    system_data: bytes | bytearray | memoryview,
    graphics_data: bytes | bytearray | memoryview,
    *,
    version: int,
    offset: int | None = None,
    pointer: int | None = None,
) -> Ytd:
    virtual_data = bytes(system_data)
    physical_data = bytes(graphics_data)
    if pointer is not None:
        dict_off = _v2o(pointer)
    elif offset is not None:
        dict_off = int(offset)
    else:
        dict_off = 0
    parser = _select_texture_dictionary_parser(virtual_data, physical_data, dict_off, int(version))
    if parser == "gen9":
        return _parse_gen9_texture_dictionary_at(virtual_data, physical_data, dict_off)
    return _parse_legacy_texture_dictionary_at(virtual_data, physical_data, dict_off)


def read_ytd(source: bytes | bytearray | memoryview | str | Path) -> Ytd:
    if isinstance(source, (str, Path)):
        data = Path(source).read_bytes()
    else:
        data = bytes(source)
    if len(data) < 16:
        raise ValueError("YTD data is too short")
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != RSC7_MAGIC:
        raise ValueError("YTD data must be a standalone RSC7 resource")
    version = struct.unpack_from("<I", data, 4)[0]
    if version == _YTD_RSC7_VERSION_GEN9:
        return _parse_gen9_ytd(data)
    return _parse_legacy_ytd(data)


def save_ytd(ytd: Ytd, path: str | Path, *, game: str | None = None) -> Path:
    return ytd.save(path, game=game)


__all__ = [
    "Texture",
    "TextureDescriptor",
    "TextureFormat",
    "TextureUsage",
    "Ytd",
    "YtdCatalog",
    "coerce_texture_usage",
    "pack_usage_data",
    "read_embedded_texture_dictionary",
    "read_embedded_ytd_catalog",
    "read_ytd",
    "read_ytd_catalog",
    "save_ytd",
    "unpack_usage_data",
]





