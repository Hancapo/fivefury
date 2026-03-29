from __future__ import annotations

import dataclasses
import struct
from enum import IntEnum
from pathlib import Path
from typing import Any

from .binary import align, read_c_string
from .hashing import jenk_hash
from .resource import (
    RSC7_MAGIC,
    ResourceHeader,
    build_rsc7,
    parse_rsc7,
    physical_to_offset,
    split_rsc7_sections,
    virtual_to_offset,
)

DAT_VIRTUAL_BASE = 0x50000000
DAT_PHYSICAL_BASE = 0x60000000

_DDS_MAGIC = 0x20534444
_DDSD_CAPS = 0x1
_DDSD_HEIGHT = 0x2
_DDSD_WIDTH = 0x4
_DDSD_PITCH = 0x8
_DDSD_PIXELFORMAT = 0x1000
_DDSD_MIPMAPCOUNT = 0x20000
_DDSD_LINEARSIZE = 0x80000
_DDPF_ALPHAPIXELS = 0x1
_DDPF_FOURCC = 0x4
_DDPF_RGB = 0x40
_DDSCAPS_TEXTURE = 0x1000
_DDSCAPS_COMPLEX = 0x8
_DDSCAPS_MIPMAP = 0x400000

_FOURCC_DXT1 = 0x31545844
_FOURCC_DXT3 = 0x33545844
_FOURCC_DXT5 = 0x35545844
_FOURCC_ATI1 = 0x31495441
_FOURCC_ATI2 = 0x32495441
_FOURCC_BC7 = 0x20374342
_FOURCC_DX10 = 0x30315844

_D3DFMT_A8R8G8B8 = 21
_D3DFMT_A8 = 28
_D3DFMT_A1R5G5B5 = 25
_D3DFMT_R5G6B5 = 23
_D3DFMT_L8 = 50

_YTD_RSC7_VERSION_LEGACY = 13
_YTD_RSC7_VERSION_GEN9 = 5
_GTAV_TEX_SIZE = 0x90
_ENHANCED_TEX_SIZE = 0x80
_ENHANCED_FLAGS = 0x00260208
_ENHANCED_TILE_AUTO = 255
_ENHANCED_UNK_23H = 0x28
_ENHANCED_UNK_44H = 2
_ENHANCED_DIM_2D = 1
_ENHANCED_SRV_VFT = 0x00000001406B77D8
_ENHANCED_SRV_DIM_2D = 0x41


class TextureFormat(IntEnum):
    BC1 = 0
    BC3 = 1
    BC4 = 2
    BC5 = 3
    BC7 = 4
    A8R8G8B8 = 5
    BC2 = 6
    BC6H = 7
    R8G8B8A8 = 10
    B5G6R5 = 11
    B5G5R5A1 = 12
    R10G10B10A2 = 13
    R8 = 20
    A8 = 21
    R8G8 = 22
    R16_FLOAT = 30
    R16G16_FLOAT = 31
    R16G16B16A16_FLOAT = 32
    R32_FLOAT = 33
    R32G32B32A32_FLOAT = 34


class DxgiFormat(IntEnum):
    R32G32B32A32_FLOAT = 2
    R16G16B16A16_FLOAT = 10
    R10G10B10A2_UNORM = 24
    R8G8B8A8_UNORM = 28
    R16G16_FLOAT = 34
    R32_FLOAT = 41
    R8G8_UNORM = 49
    R16_FLOAT = 54
    R8_UNORM = 61
    A8_UNORM = 65
    BC1_UNORM = 71
    BC2_UNORM = 74
    BC3_UNORM = 77
    BC4_UNORM = 80
    BC5_UNORM = 83
    B5G6R5_UNORM = 85
    B5G5R5A1_UNORM = 86
    B8G8R8A8_UNORM = 87
    BC6H_UF16 = 95
    BC7_UNORM = 98


class Rsc8TextureFormat(IntEnum):
    BC1_UNORM = 0x47
    BC1_UNORM_SRGB = 0x48
    BC2_UNORM = 0x4A
    BC2_UNORM_SRGB = 0x4B
    BC3_UNORM = 0x4D
    BC3_UNORM_SRGB = 0x4E
    BC4_UNORM = 0x50
    BC5_UNORM = 0x53
    BC6H_UF16 = 0x5F
    BC7_UNORM = 0x62
    BC7_UNORM_SRGB = 0x63
    R8_UNORM = 0x3D
    A8_UNORM = 0x41
    R8G8_UNORM = 0x31
    R8G8B8A8_UNORM = 0x1C
    R8G8B8A8_UNORM_SRGB = 0x1D
    B8G8R8A8_UNORM = 0x57
    B8G8R8A8_UNORM_SRGB = 0x5B
    B5G6R5_UNORM = 0x55
    B5G5R5A1_UNORM = 0x56
    R10G10B10A2_UNORM = 0x18
    R16_FLOAT = 0x36
    R16G16_FLOAT = 0x22
    R16G16B16A16_FLOAT = 0x0A
    R32_FLOAT = 0x29
    R32G32B32A32_FLOAT = 0x02


_BLOCK_COMPRESSED = frozenset(
    {
        TextureFormat.BC1,
        TextureFormat.BC2,
        TextureFormat.BC3,
        TextureFormat.BC4,
        TextureFormat.BC5,
        TextureFormat.BC6H,
        TextureFormat.BC7,
    }
)

_BLOCK_BYTES: dict[TextureFormat, int] = {
    TextureFormat.BC1: 8,
    TextureFormat.BC2: 16,
    TextureFormat.BC3: 16,
    TextureFormat.BC4: 8,
    TextureFormat.BC5: 16,
    TextureFormat.BC6H: 16,
    TextureFormat.BC7: 16,
}

_PIXEL_BYTES: dict[TextureFormat, int] = {
    TextureFormat.A8R8G8B8: 4,
    TextureFormat.R8G8B8A8: 4,
    TextureFormat.R10G10B10A2: 4,
    TextureFormat.B5G6R5: 2,
    TextureFormat.B5G5R5A1: 2,
    TextureFormat.R8: 1,
    TextureFormat.A8: 1,
    TextureFormat.R8G8: 2,
    TextureFormat.R16_FLOAT: 2,
    TextureFormat.R16G16_FLOAT: 4,
    TextureFormat.R16G16B16A16_FLOAT: 8,
    TextureFormat.R32_FLOAT: 4,
    TextureFormat.R32G32B32A32_FLOAT: 16,
}

_FORMAT_TO_DXGI: dict[TextureFormat, int] = {
    TextureFormat.BC1: DxgiFormat.BC1_UNORM,
    TextureFormat.BC2: DxgiFormat.BC2_UNORM,
    TextureFormat.BC3: DxgiFormat.BC3_UNORM,
    TextureFormat.BC4: DxgiFormat.BC4_UNORM,
    TextureFormat.BC5: DxgiFormat.BC5_UNORM,
    TextureFormat.BC6H: DxgiFormat.BC6H_UF16,
    TextureFormat.BC7: DxgiFormat.BC7_UNORM,
    TextureFormat.A8R8G8B8: DxgiFormat.B8G8R8A8_UNORM,
    TextureFormat.R8G8B8A8: DxgiFormat.R8G8B8A8_UNORM,
    TextureFormat.B5G6R5: DxgiFormat.B5G6R5_UNORM,
    TextureFormat.B5G5R5A1: DxgiFormat.B5G5R5A1_UNORM,
    TextureFormat.R10G10B10A2: DxgiFormat.R10G10B10A2_UNORM,
    TextureFormat.R8: DxgiFormat.R8_UNORM,
    TextureFormat.A8: DxgiFormat.A8_UNORM,
    TextureFormat.R8G8: DxgiFormat.R8G8_UNORM,
    TextureFormat.R16_FLOAT: DxgiFormat.R16_FLOAT,
    TextureFormat.R16G16_FLOAT: DxgiFormat.R16G16_FLOAT,
    TextureFormat.R16G16B16A16_FLOAT: DxgiFormat.R16G16B16A16_FLOAT,
    TextureFormat.R32_FLOAT: DxgiFormat.R32_FLOAT,
    TextureFormat.R32G32B32A32_FLOAT: DxgiFormat.R32G32B32A32_FLOAT,
}
_DXGI_TO_FORMAT = {value: key for key, value in _FORMAT_TO_DXGI.items()}

_FORMAT_TO_FOURCC: dict[TextureFormat, int] = {
    TextureFormat.BC1: _FOURCC_DXT1,
    TextureFormat.BC2: _FOURCC_DXT3,
    TextureFormat.BC3: _FOURCC_DXT5,
    TextureFormat.BC4: _FOURCC_ATI1,
    TextureFormat.BC5: _FOURCC_ATI2,
}
_FOURCC_TO_FORMAT = {value: key for key, value in _FORMAT_TO_FOURCC.items()}

_FORMAT_TO_DX9: dict[TextureFormat, int] = {
    TextureFormat.BC1: _FOURCC_DXT1,
    TextureFormat.BC2: _FOURCC_DXT3,
    TextureFormat.BC3: _FOURCC_DXT5,
    TextureFormat.BC4: _FOURCC_ATI1,
    TextureFormat.BC5: _FOURCC_ATI2,
    TextureFormat.BC7: _FOURCC_BC7,
    TextureFormat.A8R8G8B8: _D3DFMT_A8R8G8B8,
    TextureFormat.A8: _D3DFMT_A8,
    TextureFormat.B5G5R5A1: _D3DFMT_A1R5G5B5,
    TextureFormat.B5G6R5: _D3DFMT_R5G6B5,
    TextureFormat.R8: _D3DFMT_L8,
}
_DX9_TO_FORMAT = {value: key for key, value in _FORMAT_TO_DX9.items()}

_FORMAT_TO_RSC8: dict[TextureFormat, int] = {
    TextureFormat.BC1: Rsc8TextureFormat.BC1_UNORM,
    TextureFormat.BC2: Rsc8TextureFormat.BC2_UNORM,
    TextureFormat.BC3: Rsc8TextureFormat.BC3_UNORM,
    TextureFormat.BC4: Rsc8TextureFormat.BC4_UNORM,
    TextureFormat.BC5: Rsc8TextureFormat.BC5_UNORM,
    TextureFormat.BC6H: Rsc8TextureFormat.BC6H_UF16,
    TextureFormat.BC7: Rsc8TextureFormat.BC7_UNORM,
    TextureFormat.A8R8G8B8: Rsc8TextureFormat.B8G8R8A8_UNORM,
    TextureFormat.R8G8B8A8: Rsc8TextureFormat.R8G8B8A8_UNORM,
    TextureFormat.B5G6R5: Rsc8TextureFormat.B5G6R5_UNORM,
    TextureFormat.B5G5R5A1: Rsc8TextureFormat.B5G5R5A1_UNORM,
    TextureFormat.R10G10B10A2: Rsc8TextureFormat.R10G10B10A2_UNORM,
    TextureFormat.R8: Rsc8TextureFormat.R8_UNORM,
    TextureFormat.A8: Rsc8TextureFormat.A8_UNORM,
    TextureFormat.R8G8: Rsc8TextureFormat.R8G8_UNORM,
    TextureFormat.R16_FLOAT: Rsc8TextureFormat.R16_FLOAT,
    TextureFormat.R16G16_FLOAT: Rsc8TextureFormat.R16G16_FLOAT,
    TextureFormat.R16G16B16A16_FLOAT: Rsc8TextureFormat.R16G16B16A16_FLOAT,
    TextureFormat.R32_FLOAT: Rsc8TextureFormat.R32_FLOAT,
    TextureFormat.R32G32B32A32_FLOAT: Rsc8TextureFormat.R32G32B32A32_FLOAT,
}
_RSC8_TO_FORMAT = {value: key for key, value in _FORMAT_TO_RSC8.items()}
_RSC8_TO_FORMAT[Rsc8TextureFormat.BC1_UNORM_SRGB] = TextureFormat.BC1
_RSC8_TO_FORMAT[Rsc8TextureFormat.BC2_UNORM_SRGB] = TextureFormat.BC2
_RSC8_TO_FORMAT[Rsc8TextureFormat.BC3_UNORM_SRGB] = TextureFormat.BC3
_RSC8_TO_FORMAT[Rsc8TextureFormat.BC7_UNORM_SRGB] = TextureFormat.BC7
_RSC8_TO_FORMAT[Rsc8TextureFormat.R8G8B8A8_UNORM_SRGB] = TextureFormat.R8G8B8A8
_RSC8_TO_FORMAT[Rsc8TextureFormat.B8G8R8A8_UNORM_SRGB] = TextureFormat.A8R8G8B8

_LEGACY_TEXTURE_DICTIONARY_VERSIONS = {13, 68, 162, 165}
_GEN9_TEXTURE_DICTIONARY_VERSIONS = {5, 71, 154, 159, 171}


def _is_block_compressed(fmt: TextureFormat) -> bool:
    return fmt in _BLOCK_COMPRESSED


def _row_pitch(width: int, fmt: TextureFormat) -> int:
    if _is_block_compressed(fmt):
        return max(1, (width + 3) // 4) * _BLOCK_BYTES[fmt]
    return width * _PIXEL_BYTES[fmt]


def _mip_data_size(width: int, height: int, fmt: TextureFormat) -> int:
    if _is_block_compressed(fmt):
        bw = max(1, (width + 3) // 4)
        bh = max(1, (height + 3) // 4)
        return bw * bh * _BLOCK_BYTES[fmt]
    return width * height * _PIXEL_BYTES[fmt]


def _total_mip_data_size(width: int, height: int, fmt: TextureFormat, mip_count: int) -> int:
    total = 0
    w = max(1, int(width))
    h = max(1, int(height))
    for _ in range(max(1, int(mip_count))):
        total += _mip_data_size(w, h, fmt)
        w = max(1, w // 2)
        h = max(1, h // 2)
    return total


def _build_mip_info(width: int, height: int, fmt: TextureFormat, mip_count: int) -> tuple[list[int], list[int]]:
    offsets: list[int] = []
    sizes: list[int] = []
    w = max(1, int(width))
    h = max(1, int(height))
    offset = 0
    for _ in range(max(1, int(mip_count))):
        size = _mip_data_size(w, h, fmt)
        offsets.append(offset)
        sizes.append(size)
        offset += size
        w = max(1, w // 2)
        h = max(1, h // 2)
    return offsets, sizes


def _v2o(address: int) -> int:
    return virtual_to_offset(address, base=DAT_VIRTUAL_BASE)


def _p2o(address: int) -> int:
    return physical_to_offset(address, base=DAT_PHYSICAL_BASE)


def _split_rsc7_sections(data: bytes) -> tuple[ResourceHeader, bytes, bytes]:
    return split_rsc7_sections(data)


def _is_valid_virtual_ptr(value: int, system_data: bytes) -> bool:
    return DAT_VIRTUAL_BASE <= int(value) < (DAT_VIRTUAL_BASE + len(system_data))


def _is_valid_physical_ptr(value: int, graphics_data: bytes) -> bool:
    return DAT_PHYSICAL_BASE <= int(value) <= (DAT_PHYSICAL_BASE + len(graphics_data))


def _prefer_gen9_dictionary(version: int) -> bool | None:
    if version in _GEN9_TEXTURE_DICTIONARY_VERSIONS:
        return True
    if version in _LEGACY_TEXTURE_DICTIONARY_VERSIONS:
        return False
    return None


def _select_texture_dictionary_parser(system_data: bytes, graphics_data: bytes, dict_off: int, version: int) -> str:
    order = []
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
        except Exception:
            continue
    raise ValueError("Unsupported embedded texture dictionary layout")


def _resolve_legacy_format(value: int) -> TextureFormat | None:
    if value in _DX9_TO_FORMAT:
        return _DX9_TO_FORMAT[value]
    if value in _FOURCC_TO_FORMAT:
        return _FOURCC_TO_FORMAT[value]
    if value in _DXGI_TO_FORMAT:
        return _DXGI_TO_FORMAT[value]
    return None


def _build_dds_bytes(texture: Texture) -> bytes:
    compressed = _is_block_compressed(texture.format)
    legacy_fourcc = _FORMAT_TO_FOURCC.get(texture.format)
    legacy_uncompressed = texture.format is TextureFormat.A8R8G8B8
    use_dx10 = not legacy_fourcc and not legacy_uncompressed

    header = bytearray(124)
    struct.pack_into("<I", header, 0, 124)

    flags = _DDSD_CAPS | _DDSD_HEIGHT | _DDSD_WIDTH | _DDSD_PIXELFORMAT
    if compressed:
        flags |= _DDSD_LINEARSIZE
    else:
        flags |= _DDSD_PITCH
    if texture.mip_count > 1:
        flags |= _DDSD_MIPMAPCOUNT

    struct.pack_into("<I", header, 4, flags)
    struct.pack_into("<I", header, 8, texture.height)
    struct.pack_into("<I", header, 12, texture.width)
    struct.pack_into("<I", header, 16, texture.mip_sizes[0] if compressed else _row_pitch(texture.width, texture.format))
    struct.pack_into("<I", header, 20, 1)
    struct.pack_into("<I", header, 24, texture.mip_count)
    struct.pack_into("<I", header, 72, 32)

    if legacy_uncompressed:
        struct.pack_into("<I", header, 76, _DDPF_RGB | _DDPF_ALPHAPIXELS)
        struct.pack_into("<I", header, 84, 32)
        struct.pack_into("<I", header, 88, 0x00FF0000)
        struct.pack_into("<I", header, 92, 0x0000FF00)
        struct.pack_into("<I", header, 96, 0x000000FF)
        struct.pack_into("<I", header, 100, 0xFF000000)
    elif legacy_fourcc:
        struct.pack_into("<I", header, 76, _DDPF_FOURCC)
        struct.pack_into("<I", header, 80, legacy_fourcc)
    else:
        struct.pack_into("<I", header, 76, _DDPF_FOURCC)
        struct.pack_into("<I", header, 80, _FOURCC_DX10)

    caps = _DDSCAPS_TEXTURE
    if texture.mip_count > 1:
        caps |= _DDSCAPS_COMPLEX | _DDSCAPS_MIPMAP
    struct.pack_into("<I", header, 104, caps)

    parts = [struct.pack("<I", _DDS_MAGIC), bytes(header)]
    if use_dx10:
        dx10 = bytearray(20)
        struct.pack_into("<I", dx10, 0, int(_FORMAT_TO_DXGI[texture.format]))
        struct.pack_into("<I", dx10, 4, 3)
        struct.pack_into("<I", dx10, 12, 1)
        parts.append(bytes(dx10))
    parts.append(texture.data)
    return b"".join(parts)


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
        return read_ytd(data)


def _parse_legacy_texture_dictionary_at(virtual_data: bytes, physical_data: bytes, dict_off: int) -> Ytd:
    if dict_off < 0 or dict_off + 0x40 > len(virtual_data):
        raise ValueError("Legacy texture dictionary offset is out of range")
    count = struct.unpack_from("<H", virtual_data, dict_off + 0x28)[0]
    items_ptr = struct.unpack_from("<Q", virtual_data, dict_off + 0x30)[0]
    if count < 0 or count > 0x4000 or not _is_valid_virtual_ptr(items_ptr, virtual_data):
        raise ValueError("Legacy texture dictionary has an invalid item table")
    items_off = _v2o(items_ptr)
    if items_off + (count * 8) > len(virtual_data):
        raise ValueError("Legacy texture pointer table is truncated")
    ytd = Ytd(game="gta5")

    for index in range(count):
        tex_ptr = struct.unpack_from("<Q", virtual_data, items_off + (index * 8))[0]
        if not _is_valid_virtual_ptr(tex_ptr, virtual_data):
            raise ValueError("Legacy texture pointer is out of range")
        tex_off = _v2o(tex_ptr)
        name_ptr = struct.unpack_from("<Q", virtual_data, tex_off + 0x28)[0]
        if not _is_valid_virtual_ptr(name_ptr, virtual_data):
            raise ValueError("Legacy texture name pointer is out of range")
        name = read_c_string(virtual_data, _v2o(name_ptr))
        width = struct.unpack_from("<h", virtual_data, tex_off + 0x50)[0]
        height = struct.unpack_from("<h", virtual_data, tex_off + 0x52)[0]
        format_value = struct.unpack_from("<I", virtual_data, tex_off + 0x58)[0]
        mip_count = virtual_data[tex_off + 0x5D]
        data_ptr = struct.unpack_from("<Q", virtual_data, tex_off + 0x70)[0]
        if width <= 0 or height <= 0 or mip_count <= 0:
            raise ValueError("Legacy texture dictionary contains invalid texture metadata")

        texture_format = _resolve_legacy_format(format_value)
        if texture_format is None:
            raise ValueError(f"Unsupported GTA V YTD format 0x{format_value:08X} in '{name}'")

        phys_off = _p2o(data_ptr)
        data_size = _total_mip_data_size(width, height, texture_format, mip_count)
        if phys_off < 0:
            raise ValueError("Legacy texture pixel data is out of range")
        if phys_off < len(physical_data):
            pixel_data = physical_data[phys_off : phys_off + data_size]
        elif len(virtual_data) >= data_size:
            pixel_data = virtual_data[-data_size:]
        else:
            raise ValueError("Legacy texture pixel data is out of range")
        ytd.textures.append(Texture.from_raw(pixel_data, width, height, texture_format, mip_count, name=name))
    return ytd


def _parse_gen9_texture_dictionary_at(virtual_data: bytes, physical_data: bytes, dict_off: int) -> Ytd:
    if dict_off < 0 or dict_off + 0x40 > len(virtual_data):
        raise ValueError("Gen9 texture dictionary offset is out of range")
    count = struct.unpack_from("<H", virtual_data, dict_off + 0x28)[0]
    items_ptr = struct.unpack_from("<Q", virtual_data, dict_off + 0x30)[0]
    if count < 0 or count > 0x4000 or not _is_valid_virtual_ptr(items_ptr, virtual_data):
        raise ValueError("Gen9 texture dictionary has an invalid item table")
    items_off = _v2o(items_ptr)
    if items_off + (count * 8) > len(virtual_data):
        raise ValueError("Gen9 texture pointer table is truncated")
    ytd = Ytd(game="gta5_enhanced")

    for index in range(count):
        tex_ptr = struct.unpack_from("<Q", virtual_data, items_off + (index * 8))[0]
        if not _is_valid_virtual_ptr(tex_ptr, virtual_data):
            raise ValueError("Gen9 texture pointer is out of range")
        tex_off = _v2o(tex_ptr)
        name_ptr = struct.unpack_from("<Q", virtual_data, tex_off + 0x28)[0]
        if not _is_valid_virtual_ptr(name_ptr, virtual_data):
            raise ValueError("Gen9 texture name pointer is out of range")
        name = read_c_string(virtual_data, _v2o(name_ptr))
        width = struct.unpack_from("<H", virtual_data, tex_off + 0x18)[0]
        height = struct.unpack_from("<H", virtual_data, tex_off + 0x1A)[0]
        format_value = virtual_data[tex_off + 0x1F]
        mip_count = virtual_data[tex_off + 0x22]
        data_ptr = struct.unpack_from("<Q", virtual_data, tex_off + 0x38)[0]
        if width <= 0 or height <= 0 or mip_count <= 0:
            raise ValueError("Gen9 texture dictionary contains invalid texture metadata")

        texture_format = _RSC8_TO_FORMAT.get(format_value)
        if texture_format is None:
            raise ValueError(f"Unsupported GTA V Enhanced YTD format 0x{format_value:02X} in '{name}'")

        phys_off = _p2o(data_ptr)
        data_size = _total_mip_data_size(width, height, texture_format, mip_count)
        if phys_off < 0:
            raise ValueError("Gen9 texture pixel data is out of range")
        if phys_off < len(physical_data):
            pixel_data = physical_data[phys_off : phys_off + data_size]
        elif len(virtual_data) >= data_size:
            pixel_data = virtual_data[-data_size:]
        else:
            raise ValueError("Gen9 texture pixel data is out of range")
        ytd.textures.append(Texture.from_raw(pixel_data, width, height, texture_format, mip_count, name=name))
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
        data_size_large = 0
        for level in range(texture.mip_count):
            width = max(1, texture.width >> level)
            height = max(1, texture.height >> level)
            if width >= 16 and height >= 16:
                data_size_large += _mip_data_size(width, height, texture.format)

        struct.pack_into("<Q", vbuf, off + 0x28, DAT_VIRTUAL_BASE + name_offsets[index])
        struct.pack_into("<h", vbuf, off + 0x30, 1)
        struct.pack_into("<I", vbuf, off + 0x40, data_size_large)
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
        block_count = 0
        width = texture.width
        height = texture.height
        for _ in range(texture.mip_count):
            block_w = max(1, (width + (3 if _is_block_compressed(texture.format) else 0)) // (4 if _is_block_compressed(texture.format) else 1))
            block_h = max(1, (height + (3 if _is_block_compressed(texture.format) else 0)) // (4 if _is_block_compressed(texture.format) else 1))
            block_count += block_w * block_h
            width = max(1, width // 2)
            height = max(1, height // 2)

        struct.pack_into("<II", vbuf, off + 0x00, 0, 1)
        struct.pack_into("<II", vbuf, off + 0x08, block_count, block_stride)
        struct.pack_into("<II", vbuf, off + 0x10, _ENHANCED_FLAGS, 0)
        struct.pack_into("<HHH", vbuf, off + 0x18, texture.width, texture.height, 1)
        vbuf[off + 0x1E] = _ENHANCED_DIM_2D
        vbuf[off + 0x1F] = _FORMAT_TO_RSC8[texture.format]
        vbuf[off + 0x20] = _ENHANCED_TILE_AUTO
        vbuf[off + 0x22] = texture.mip_count
        vbuf[off + 0x23] = _ENHANCED_UNK_23H
        struct.pack_into("<H", vbuf, off + 0x26, 1)
        struct.pack_into("<Q", vbuf, off + 0x28, DAT_VIRTUAL_BASE + name_offsets[index])
        struct.pack_into("<Q", vbuf, off + 0x30, DAT_VIRTUAL_BASE + off + 0x58)
        struct.pack_into("<Q", vbuf, off + 0x38, DAT_PHYSICAL_BASE + physical_offsets[index])
        struct.pack_into("<II", vbuf, off + 0x40, 0, _ENHANCED_UNK_44H)
        struct.pack_into("<Q", vbuf, off + 0x58, _ENHANCED_SRV_VFT)
        struct.pack_into("<HHI", vbuf, off + 0x68, _ENHANCED_SRV_DIM_2D, 0xFFFF, 0xFFFFFFFF)

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
    "TextureFormat",
    "Ytd",
    "read_embedded_texture_dictionary",
    "read_ytd",
    "save_ytd",
]


