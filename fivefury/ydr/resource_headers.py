"""Runtime class headers used by legacy GTA V drawable resources."""

import dataclasses

RESOURCE_STATE = 1

DRAWABLE_FILE_VFT = 0x40573178
EMBEDDED_DRAWABLE_FILE_VFT = 0x40570C38
SHADER_GROUP_VFT = 0x406137F0
TEXTURE_BASE_VFT = 0x40617568
DRAWABLE_MODEL_VFT = 0x40610A98
DRAWABLE_GEOMETRY_VFT = 0x40618798
VERTEX_BUFFER_VFT = 0x4061D3F8
INDEX_BUFFER_VFT = 0x4061D158
SKELETON_VFT = 0x40613CA0
JOINTS_VFT = 0x40617800


@dataclasses.dataclass(frozen=True, slots=True)
class DrawableRuntimeHeaders:
    drawable: int
    shader_group: int
    texture_base: int
    model: int
    geometry: int
    vertex_buffer: int
    index_buffer: int
    skeleton: int
    joints: int


LEGACY_DRAWABLE_HEADERS = DrawableRuntimeHeaders(
    drawable=DRAWABLE_FILE_VFT,
    shader_group=SHADER_GROUP_VFT,
    texture_base=TEXTURE_BASE_VFT,
    model=DRAWABLE_MODEL_VFT,
    geometry=DRAWABLE_GEOMETRY_VFT,
    vertex_buffer=VERTEX_BUFFER_VFT,
    index_buffer=INDEX_BUFFER_VFT,
    skeleton=SKELETON_VFT,
    joints=JOINTS_VFT,
)

# Shared by the base-game breakable-prop fragments used as binary donors.
LEGACY_FRAGMENT_DRAWABLE_HEADERS = DrawableRuntimeHeaders(
    drawable=0x40604BC8,
    shader_group=0x406117F0,
    texture_base=TEXTURE_BASE_VFT,
    model=0x4060EA98,
    geometry=0x40616798,
    vertex_buffer=0x4061B3F8,
    index_buffer=0x4061B158,
    skeleton=0x40611CA0,
    joints=0x40615C60,
)

# Both texture implementations occur in the legacy prop corpus.
LEGACY_FRAGMENT_TEXTURE_VFTS = (0x40617568, 0x406187F8)

__all__ = [
    "DRAWABLE_FILE_VFT",
    "DRAWABLE_GEOMETRY_VFT",
    "DRAWABLE_MODEL_VFT",
    "EMBEDDED_DRAWABLE_FILE_VFT",
    "INDEX_BUFFER_VFT",
    "JOINTS_VFT",
    "LEGACY_DRAWABLE_HEADERS",
    "LEGACY_FRAGMENT_DRAWABLE_HEADERS",
    "LEGACY_FRAGMENT_TEXTURE_VFTS",
    "RESOURCE_STATE",
    "SHADER_GROUP_VFT",
    "SKELETON_VFT",
    "TEXTURE_BASE_VFT",
    "VERTEX_BUFFER_VFT",
    "DrawableRuntimeHeaders",
]
