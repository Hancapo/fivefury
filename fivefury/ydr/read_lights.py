from __future__ import annotations

import struct
from typing import Callable

from .model import YdrLight, YdrLightType


def parse_inline_simple_list(
    header_off: int,
    system_data: bytes,
    *,
    virtual_offset: Callable[[int, bytes], int],
    u16: Callable[[bytes, int], int],
    u64: Callable[[bytes, int], int],
) -> tuple[int, int]:
    data_pointer = u64(system_data, header_off + 0x00)
    count = u16(system_data, header_off + 0x08)
    if not data_pointer or count <= 0:
        return 0, 0
    return virtual_offset(data_pointer, system_data), int(count)


def parse_light(
    system_data: bytes,
    light_off: int,
    *,
    u16: Callable[[bytes, int], int],
    u32: Callable[[bytes, int], int],
    f32: Callable[[bytes, int], float],
    vec3: Callable[[bytes, int], tuple[float, float, float]],
) -> YdrLight:
    raw_light_type = system_data[light_off + 0x26]
    return YdrLight(
        unknown_0h=u32(system_data, light_off + 0x00),
        unknown_4h=u32(system_data, light_off + 0x04),
        position=vec3(system_data, light_off + 0x08),
        unknown_14h=u32(system_data, light_off + 0x14),
        color=struct.unpack_from("<3B", system_data, light_off + 0x18),
        flashiness=system_data[light_off + 0x1B],
        intensity=f32(system_data, light_off + 0x1C),
        flags=u32(system_data, light_off + 0x20),
        bone_id=u16(system_data, light_off + 0x24),
        light_type=YdrLightType(raw_light_type) if raw_light_type in {1, 2, 4} else YdrLightType.POINT,
        group_id=system_data[light_off + 0x27],
        time_flags=u32(system_data, light_off + 0x28),
        falloff=f32(system_data, light_off + 0x2C),
        falloff_exponent=f32(system_data, light_off + 0x30),
        culling_plane_normal=vec3(system_data, light_off + 0x34),
        culling_plane_offset=f32(system_data, light_off + 0x40),
        shadow_blur=system_data[light_off + 0x44],
        unknown_45h=system_data[light_off + 0x45],
        unknown_46h=u16(system_data, light_off + 0x46),
        unknown_48h=u32(system_data, light_off + 0x48),
        volume_intensity=f32(system_data, light_off + 0x4C),
        volume_size_scale=f32(system_data, light_off + 0x50),
        volume_outer_color=struct.unpack_from("<3B", system_data, light_off + 0x54),
        light_hash=system_data[light_off + 0x57],
        volume_outer_intensity=f32(system_data, light_off + 0x58),
        corona_size=f32(system_data, light_off + 0x5C),
        volume_outer_exponent=f32(system_data, light_off + 0x60),
        light_fade_distance=system_data[light_off + 0x64],
        shadow_fade_distance=system_data[light_off + 0x65],
        specular_fade_distance=system_data[light_off + 0x66],
        volumetric_fade_distance=system_data[light_off + 0x67],
        shadow_near_clip=f32(system_data, light_off + 0x68),
        corona_intensity=f32(system_data, light_off + 0x6C),
        corona_z_bias=f32(system_data, light_off + 0x70),
        direction=vec3(system_data, light_off + 0x74),
        tangent=vec3(system_data, light_off + 0x80),
        cone_inner_angle=f32(system_data, light_off + 0x8C),
        cone_outer_angle=f32(system_data, light_off + 0x90),
        extent=vec3(system_data, light_off + 0x94),
        projected_texture_hash=u32(system_data, light_off + 0xA0),
        unknown_a4h=u32(system_data, light_off + 0xA4),
    )


def parse_lights(
    system_data: bytes,
    *,
    root_offset: int,
    virtual_offset: Callable[[int, bytes], int],
    u16: Callable[[bytes, int], int],
    u32: Callable[[bytes, int], int],
    u64: Callable[[bytes, int], int],
    f32: Callable[[bytes, int], float],
    vec3: Callable[[bytes, int], tuple[float, float, float]],
) -> list[YdrLight]:
    lights_off, light_count = parse_inline_simple_list(
        root_offset + 0xA0,
        system_data,
        virtual_offset=virtual_offset,
        u16=u16,
        u64=u64,
    )
    if not lights_off or light_count <= 0:
        return []
    light_stride = 0xA8
    end = lights_off + (light_count * light_stride)
    if end > len(system_data):
        raise ValueError("light list is truncated")
    return [
        parse_light(
            system_data,
            lights_off + (index * light_stride),
            u16=u16,
            u32=u32,
            f32=f32,
            vec3=vec3,
        )
        for index in range(light_count)
    ]
