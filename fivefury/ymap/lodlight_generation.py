from __future__ import annotations

import dataclasses
import math
import struct

from ..hashing import jenkins_hash_words
from ..vector import (
    Aabb3,
    Vector3,
    aabb_transform,
    quat_rotate_vector,
    vec_add,
    vec_scale,
    vec_sub,
)
from ..ydr.model import Ydr, YdrLight, YdrLightFlags, YdrLightType
from .entities import EntityDef
from .enums import (
    YmapEntityFlags,
    YmapLodLightCategory,
    YmapLodLightType,
    YmapPriorityLevel,
)
from .lights import (
    MAX_LOD_LIGHT_CAPSULE_EXTENT,
    MAX_LOD_LIGHT_CONE_ANGLE,
    MAX_LOD_LIGHT_CORONA_INTENSITY,
    MAX_LOD_LIGHT_INTENSITY,
    LodLight,
)
from .packing import pack_lod_light_u8, pack_rgbi

_POINT_LIGHT_EXTENSION = 0.058
_OTHER_LIGHT_EXTENSION = 0.029
_MIN_LOD_CAPSULE_EXTENT = MAX_LOD_LIGHT_CAPSULE_EXTENT / 255.0


@dataclasses.dataclass(slots=True, frozen=True)
class GeneratedLodLight:
    light: LodLight
    category: YmapLodLightCategory
    physical_bounds: Aabb3
    source_light_index: int
    source_model_name: str = ""

    @property
    def is_street_light(self) -> bool:
        return self.light.is_street_light


@dataclasses.dataclass(slots=True)
class LodLightSourceInstance:
    ydr: Ydr
    entity: EntityDef
    archetype_bounds: Aabb3
    model_name: str = ""

    def extract(self) -> list[GeneratedLodLight]:
        return extract_lod_lights(
            self.ydr,
            self.entity,
            archetype_bounds=self.archetype_bounds,
            model_name=self.model_name,
        )


def calculate_lod_light_hash(entity_bounds: Aabb3, light_index: int) -> int:
    if light_index < 0:
        raise ValueError("light_index must be non-negative")
    minimum, maximum = _validate_aabb(entity_bounds, name="entity_bounds")
    words = [
        *(_quantize_hash_bound(component) for component in minimum),
        *(_quantize_hash_bound(component) for component in maximum),
        int(light_index),
    ]
    return jenkins_hash_words(words)


def calculate_lod_light_category(
    light_type: YdrLightType | YmapLodLightType | int,
    falloff: float,
    intensity: float,
    capsule_extent: float = 0.0,
    flags: YdrLightFlags | int = YdrLightFlags.NONE,
) -> YmapLodLightCategory:
    light_flags = YdrLightFlags(int(flags))
    if light_flags & YdrLightFlags.FAR_LOD_LIGHT:
        return YmapLodLightCategory.LARGE
    length = float(falloff)
    if int(light_type) == int(YdrLightType.CAPSULE):
        length = (2.0 * float(falloff)) + float(capsule_extent)
    if light_flags & YdrLightFlags.FORCE_MEDIUM_LOD_LIGHT or (
        length >= 10.0 and float(intensity) >= 1.0
    ):
        return YmapLodLightCategory.MEDIUM
    return YmapLodLightCategory.SMALL


def validate_lod_light_source_bounds(
    archetype_bounds: Aabb3,
    drawable_bounds: Aabb3,
    *,
    tolerance: float = 1e-6,
) -> None:
    archetype_min, archetype_max = _validate_aabb(
        archetype_bounds, name="archetype_bounds"
    )
    drawable_min, drawable_max = _validate_aabb(
        drawable_bounds, name="drawable_bounds"
    )
    axes = "XYZ"
    for axis in range(3):
        if drawable_min[axis] < archetype_min[axis] - tolerance:
            raise ValueError(
                f"archetype bbMin.{axes[axis]} does not contain the drawable bounds"
            )
        if drawable_max[axis] > archetype_max[axis] + tolerance:
            raise ValueError(
                f"archetype bbMax.{axes[axis]} does not contain the drawable bounds"
            )


def calculate_light_physical_bounds(
    light: YdrLight,
    *,
    position: Vector3 | None = None,
    direction: Vector3 | None = None,
) -> Aabb3:
    world_position = light.position if position is None else position
    world_direction = light.direction if direction is None else direction
    extension = (
        _POINT_LIGHT_EXTENSION
        if light.light_type == YdrLightType.POINT
        else _OTHER_LIGHT_EXTENSION
    )
    extra_radius = float(light.falloff) * extension
    radius = float(light.falloff) + extra_radius

    if light.light_type == YdrLightType.POINT:
        offset = (radius, radius, radius)
        return vec_sub(world_position, offset), vec_add(world_position, offset)
    if light.light_type == YdrLightType.CAPSULE:
        half_extent = float(light.extent[0]) * 0.5
        point_a = vec_add(world_position, vec_scale(world_direction, half_extent))
        point_b = vec_sub(world_position, vec_scale(world_direction, half_extent))
        offset = (radius, radius, radius)
        return (
            tuple(min(point_a[i], point_b[i]) - offset[i] for i in range(3)),
            tuple(max(point_a[i], point_b[i]) + offset[i] for i in range(3)),
        )
    if light.light_type == YdrLightType.SPOT:
        adjusted_position = vec_sub(
            world_position, vec_scale(world_direction, extra_radius)
        )
        cone_radius = radius + extra_radius
        angle = math.radians(float(light.cone_outer_angle))
        minimum: list[float] = []
        maximum: list[float] = []
        for axis in range(3):
            direction_component = max(-1.0, min(1.0, world_direction[axis]))
            direction_angle = math.acos(direction_component)
            min_angle = max(math.pi * 0.5, min(math.pi, direction_angle + angle))
            max_angle = max(0.0, min(math.pi * 0.5, direction_angle - angle))
            minimum.append(adjusted_position[axis] + math.cos(min_angle) * cone_radius)
            maximum.append(adjusted_position[axis] + math.cos(max_angle) * cone_radius)
        return tuple(minimum), tuple(maximum)
    raise ValueError(f"unsupported YDR light type: {int(light.light_type)}")


def extract_lod_light(
    light: YdrLight,
    entity: EntityDef,
    *,
    entity_bounds: Aabb3,
    light_index: int,
    model_name: str = "",
) -> GeneratedLodLight | None:
    if light.light_fade_distance > 0:
        return None

    scale = (float(entity.scale_xy), float(entity.scale_xy), float(entity.scale_z))
    scaled_position = tuple(light.position[i] * scale[i] for i in range(3))
    world_position = vec_add(
        quat_rotate_vector(entity.rotation, scaled_position), entity.position
    )
    scaled_direction = tuple(light.direction[i] * scale[i] for i in range(3))
    world_direction = quat_rotate_vector(entity.rotation, scaled_direction)

    capsule_extent = float(light.extent[0])
    effective_type = light.light_type
    if (
        effective_type == YdrLightType.CAPSULE
        and capsule_extent < _MIN_LOD_CAPSULE_EXTENT
    ):
        effective_type = YdrLightType.POINT

    lod_light = LodLight(
        position=world_position,
        direction=world_direction,
        falloff=float(light.falloff),
        falloff_exponent=float(light.falloff_exponent),
        hash=calculate_lod_light_hash(entity_bounds, light_index),
        rgbi=pack_rgbi(
            light.color,
            pack_lod_light_u8(light.intensity, MAX_LOD_LIGHT_INTENSITY),
        ),
    )
    lod_light.time_flags = int(light.time_flags)
    lod_light.light_type = YmapLodLightType(int(light.light_type))
    lower_name = model_name.lower()
    lod_light.is_street_light = "streetlight" in lower_name or "street_light" in lower_name
    lod_light.is_corona_only = bool(
        light.flags
        & (YdrLightFlags.CORONA_ONLY | YdrLightFlags.CORONA_ONLY_LOD_LIGHT)
    )
    lod_light.dont_use_in_cutscene = bool(
        light.flags & YdrLightFlags.DONT_USE_IN_CUTSCENE
    )
    lod_light.cone_inner_angle = pack_lod_light_u8(
        light.cone_inner_angle, MAX_LOD_LIGHT_CONE_ANGLE
    )
    if effective_type == YdrLightType.CAPSULE:
        lod_light.cone_outer_angle_or_cap_ext = pack_lod_light_u8(
            capsule_extent, MAX_LOD_LIGHT_CAPSULE_EXTENT
        )
    else:
        lod_light.cone_outer_angle_or_cap_ext = pack_lod_light_u8(
            light.cone_outer_angle, MAX_LOD_LIGHT_CONE_ANGLE
        )
    corona_intensity = 0.0 if light.corona_size < 0.05 else light.corona_intensity
    lod_light.corona_intensity = pack_lod_light_u8(
        corona_intensity, MAX_LOD_LIGHT_CORONA_INTENSITY
    )

    return GeneratedLodLight(
        light=lod_light,
        category=calculate_lod_light_category(
            effective_type,
            light.falloff,
            light.intensity,
            capsule_extent,
            light.flags,
        ),
        physical_bounds=calculate_light_physical_bounds(
            light, position=world_position, direction=world_direction
        ),
        source_light_index=light_index,
        source_model_name=model_name,
    )


def extract_lod_lights(
    ydr: Ydr,
    entity: EntityDef,
    *,
    archetype_bounds: Aabb3,
    model_name: str = "",
) -> list[GeneratedLodLight]:
    if (
        not entity.flags & YmapEntityFlags.IS_FIXED
        and entity.priority_level > YmapPriorityLevel.REQUIRED
    ):
        return []
    validate_lod_light_source_bounds(
        archetype_bounds,
        (ydr.bounding_box_min, ydr.bounding_box_max),
    )
    entity_bounds = aabb_transform(
        archetype_bounds,
        translation=entity.position,
        rotation=entity.rotation,
        scale=(entity.scale_xy, entity.scale_xy, entity.scale_z),
    )
    extracted: list[GeneratedLodLight] = []
    for light_index, light in enumerate(ydr.lights):
        candidate = extract_lod_light(
            light,
            entity,
            entity_bounds=entity_bounds,
            light_index=light_index,
            model_name=model_name,
        )
        if candidate is not None:
            extracted.append(candidate)
    return extracted


def _validate_aabb(bounds: Aabb3, *, name: str) -> Aabb3:
    minimum = tuple(float(value) for value in bounds[0])
    maximum = tuple(float(value) for value in bounds[1])
    if not all(math.isfinite(value) for value in (*minimum, *maximum)):
        raise ValueError(f"{name} must contain finite values")
    if any(minimum[axis] > maximum[axis] for axis in range(3)):
        raise ValueError(f"{name} minimum must not exceed its maximum")
    return minimum, maximum


def _quantize_hash_bound(value: float) -> int:
    component = struct.unpack("<f", struct.pack("<f", float(value)))[0]
    scaled = struct.unpack("<f", struct.pack("<f", component * 10.0))[0]
    return int(scaled)


__all__ = [
    "GeneratedLodLight",
    "LodLightSourceInstance",
    "calculate_light_physical_bounds",
    "calculate_lod_light_category",
    "calculate_lod_light_hash",
    "extract_lod_light",
    "extract_lod_lights",
    "validate_lod_light_source_bounds",
]
