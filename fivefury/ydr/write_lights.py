from __future__ import annotations

from typing import Sequence

from .model import YdrLight


def write_lights(system, lights: Sequence[YdrLight]) -> int:
    if not lights:
        return 0
    lights_block_off = system.alloc(len(lights) * 0xA8, 16)
    for index, light in enumerate(lights):
        light_off = lights_block_off + (index * 0xA8)
        system.pack_into("I", light_off + 0x00, int(light.unknown_0h))
        system.pack_into("I", light_off + 0x04, int(light.unknown_4h))
        system.pack_into("3f", light_off + 0x08, *light.position)
        system.pack_into("I", light_off + 0x14, int(light.unknown_14h))
        system.write(light_off + 0x18, bytes((int(light.color[0]) & 0xFF, int(light.color[1]) & 0xFF, int(light.color[2]) & 0xFF)))
        system.write(light_off + 0x1B, bytes((int(light.flashiness) & 0xFF,)))
        system.pack_into("f", light_off + 0x1C, float(light.intensity))
        system.pack_into("I", light_off + 0x20, int(light.flags))
        system.pack_into("H", light_off + 0x24, int(light.bone_id) & 0xFFFF)
        system.write(light_off + 0x26, bytes((int(light.light_type) & 0xFF, int(light.group_id) & 0xFF)))
        system.pack_into("I", light_off + 0x28, int(light.time_flags))
        system.pack_into("f", light_off + 0x2C, float(light.falloff))
        system.pack_into("f", light_off + 0x30, float(light.falloff_exponent))
        system.pack_into("3f", light_off + 0x34, *light.culling_plane_normal)
        system.pack_into("f", light_off + 0x40, float(light.culling_plane_offset))
        system.write(light_off + 0x44, bytes((int(light.shadow_blur) & 0xFF, int(light.unknown_45h) & 0xFF)))
        system.pack_into("H", light_off + 0x46, int(light.unknown_46h) & 0xFFFF)
        system.pack_into("I", light_off + 0x48, int(light.unknown_48h))
        system.pack_into("f", light_off + 0x4C, float(light.volume_intensity))
        system.pack_into("f", light_off + 0x50, float(light.volume_size_scale))
        system.write(
            light_off + 0x54,
            bytes(
                (
                    int(light.volume_outer_color[0]) & 0xFF,
                    int(light.volume_outer_color[1]) & 0xFF,
                    int(light.volume_outer_color[2]) & 0xFF,
                    int(light.light_hash) & 0xFF,
                )
            ),
        )
        system.pack_into("f", light_off + 0x58, float(light.volume_outer_intensity))
        system.pack_into("f", light_off + 0x5C, float(light.corona_size))
        system.pack_into("f", light_off + 0x60, float(light.volume_outer_exponent))
        system.write(
            light_off + 0x64,
            bytes(
                (
                    int(light.light_fade_distance) & 0xFF,
                    int(light.shadow_fade_distance) & 0xFF,
                    int(light.specular_fade_distance) & 0xFF,
                    int(light.volumetric_fade_distance) & 0xFF,
                )
            ),
        )
        system.pack_into("f", light_off + 0x68, float(light.shadow_near_clip))
        system.pack_into("f", light_off + 0x6C, float(light.corona_intensity))
        system.pack_into("f", light_off + 0x70, float(light.corona_z_bias))
        system.pack_into("3f", light_off + 0x74, *light.direction)
        system.pack_into("3f", light_off + 0x80, *light.tangent)
        system.pack_into("f", light_off + 0x8C, float(light.cone_inner_angle))
        system.pack_into("f", light_off + 0x90, float(light.cone_outer_angle))
        system.pack_into("3f", light_off + 0x94, *light.extent)
        system.pack_into("I", light_off + 0xA0, int(light.projected_texture_hash))
        system.pack_into("I", light_off + 0xA4, int(light.unknown_a4h))
    return lights_block_off
