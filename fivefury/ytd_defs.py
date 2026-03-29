from __future__ import annotations

import struct
from enum import IntEnum
from typing import TYPE_CHECKING

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

DAT_VIRTUAL_BASE = 0x50000000
DAT_PHYSICAL_BASE = 0x60000000

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

if TYPE_CHECKING:
    from .ytd_model import Texture


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


__all__ = [
    "DAT_PHYSICAL_BASE",
    "DAT_VIRTUAL_BASE",
    "DxgiFormat",
    "Rsc8TextureFormat",
    "TextureFormat",
    "_BLOCK_BYTES",
    "_ENHANCED_DIM_2D",
    "_ENHANCED_FLAGS",
    "_ENHANCED_SRV_DIM_2D",
    "_ENHANCED_SRV_VFT",
    "_ENHANCED_TEX_SIZE",
    "_ENHANCED_TILE_AUTO",
    "_ENHANCED_UNK_23H",
    "_ENHANCED_UNK_44H",
    "_FORMAT_TO_DX9",
    "_FORMAT_TO_RSC8",
    "_GEN9_TEXTURE_DICTIONARY_VERSIONS",
    "_GTAV_TEX_SIZE",
    "_LEGACY_TEXTURE_DICTIONARY_VERSIONS",
    "_RSC8_TO_FORMAT",
    "_YTD_RSC7_VERSION_GEN9",
    "_YTD_RSC7_VERSION_LEGACY",
    "_build_dds_bytes",
    "_build_mip_info",
    "_is_block_compressed",
    "_mip_data_size",
    "_resolve_legacy_format",
    "_row_pitch",
    "_total_mip_data_size",
]
