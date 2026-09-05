from __future__ import annotations

import dataclasses
import math
import struct
from typing import TYPE_CHECKING

from ..authoring.diagnostics import ValidationReport
from ..hashing import jenkins_hash_words
from ..vector import (
    Aabb3,
    Vector3,
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

if TYPE_CHECKING:
    from ..ytyp.base_archetype import BaseArchetypeDef

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
    archetype: BaseArchetypeDef | None = None

    def extract(self) -> list[GeneratedLodLight]:
        return extract_lod_lights(
            self.ydr,
            self.entity,
            archetype_bounds=self.archetype_bounds,
            model_name=self.model_name,
            archetype=self.archetype,
        )


def calculate_lod_light_hash(entity_bounds: Aabb3, light_index: int) -> int:
    if light_index < 0:
        raise ValueError("light_index must be non-negative")
    bounds = _validate_aabb(entity_bounds, name="entity_bounds")
    words = [
        *(_quantize_hash_bound(component) for component in bounds.minimum),
        *(_quantize_hash_bound(component) for component in bounds.maximum),
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
) -> ValidationReport:
    issues = ValidationReport()
    try:
        archetype = _validate_aabb(archetype_bounds, name="archetype_bounds")
    except ValueError as exc:
        issues.issue("ymap.lod_source.archetype_bounds.invalid", str(exc), path="archetype_bounds")
        return issues
    try:
        drawable = _validate_aabb(drawable_bounds, name="drawable_bounds")
    except ValueError as exc:
        issues.issue("ymap.lod_source.drawable_bounds.invalid", str(exc), path="drawable_bounds")
        return issues
    components = (
        ("x", drawable.minimum.x, archetype.minimum.x, drawable.maximum.x, archetype.maximum.x),
        ("y", drawable.minimum.y, archetype.minimum.y, drawable.maximum.y, archetype.maximum.y),
        ("z", drawable.minimum.z, archetype.minimum.z, drawable.maximum.z, archetype.maximum.z),
    )
    for axis, drawable_minimum, archetype_minimum, drawable_maximum, archetype_maximum in components:
        if drawable_minimum < archetype_minimum - tolerance:
            issues.issue(
                "ymap.lod_source.bounds.minimum",
                f"archetype bbMin.{axis} does not contain the drawable bounds",
                path=f"archetype_bounds.minimum.{axis}",
            )
        if drawable_maximum > archetype_maximum + tolerance:
            issues.issue(
                "ymap.lod_source.bounds.maximum",
                f"archetype bbMax.{axis} does not contain the drawable bounds",
                path=f"archetype_bounds.maximum.{axis}",
            )
    return issues


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
        offset = Vector3(radius, radius, radius)
        return Aabb3(world_position - offset, world_position + offset)
    if light.light_type == YdrLightType.CAPSULE:
        half_extent = light.extent.x * 0.5
        point_a = world_position + (world_direction * half_extent)
        point_b = world_position - (world_direction * half_extent)
        offset = Vector3(radius, radius, radius)
        return Aabb3(
            Vector3.minimum((point_a, point_b)) - offset,
            Vector3.maximum((point_a, point_b)) + offset,
        )
    if light.light_type == YdrLightType.SPOT:
        adjusted_position = world_position - (world_direction * extra_radius)
        cone_radius = radius + extra_radius
        angle = math.radians(float(light.cone_outer_angle))

        def axis_bounds(position_component: float, direction_component: float) -> tuple[float, float]:
            direction_component = max(-1.0, min(1.0, direction_component))
            direction_angle = math.acos(direction_component)
            min_angle = max(math.pi * 0.5, min(math.pi, direction_angle + angle))
            max_angle = max(0.0, min(math.pi * 0.5, direction_angle - angle))
            return (
                position_component + math.cos(min_angle) * cone_radius,
                position_component + math.cos(max_angle) * cone_radius,
            )

        x_min, x_max = axis_bounds(adjusted_position.x, world_direction.x)
        y_min, y_max = axis_bounds(adjusted_position.y, world_direction.y)
        z_min, z_max = axis_bounds(adjusted_position.z, world_direction.z)
        return Aabb3(
            Vector3(x_min, y_min, z_min),
            Vector3(x_max, y_max, z_max),
        )
    raise ValueError(f"unsupported YDR light type: {int(light.light_type)}")


def extract_lod_light(
    light: YdrLight,
    entity: EntityDef,
    *,
    entity_bounds: Aabb3,
    light_index: int,
    model_name: str = "",
    archetype: BaseArchetypeDef | None = None,
) -> GeneratedLodLight | None:
    if light.light_fade_distance > 0:
        return None

    scale = entity.world_scale(archetype)
    rotation = entity.world_rotation(archetype)
    scaled_position = Vector3(light.position.x * scale.x, light.position.y * scale.y, light.position.z * scale.z)
    world_position = rotation.rotate(scaled_position) + entity.position
    scaled_direction = Vector3(light.direction.x * scale.x, light.direction.y * scale.y, light.direction.z * scale.z)
    world_direction = rotation.rotate(scaled_direction)

    capsule_extent = light.extent.x
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
    archetype: BaseArchetypeDef | None = None,
) -> list[GeneratedLodLight]:
    if (
        not entity.flags & YmapEntityFlags.IS_FIXED
        and entity.priority_level > YmapPriorityLevel.REQUIRED
    ):
        return []
    validate_lod_light_source_bounds(
        archetype_bounds,
        Aabb3(ydr.bounding_box_min, ydr.bounding_box_max),
    ).raise_for_errors()
    entity_bounds = entity.world_bounds(archetype_bounds, archetype)
    extracted: list[GeneratedLodLight] = []
    for light_index, light in enumerate(ydr.lights):
        candidate = extract_lod_light(
            light,
            entity,
            entity_bounds=entity_bounds,
            light_index=light_index,
            model_name=model_name,
            archetype=archetype,
        )
        if candidate is not None:
            extracted.append(candidate)
    return extracted


def _validate_aabb(bounds: Aabb3, *, name: str) -> Aabb3:
    if not isinstance(bounds, Aabb3):
        raise TypeError(f"{name} must be an Aabb3")
    if not bounds.minimum.is_finite or not bounds.maximum.is_finite:
        raise ValueError(f"{name} must contain finite values")
    if any(left > right for left, right in zip(bounds.minimum, bounds.maximum, strict=True)):
        raise ValueError(f"{name} minimum must not exceed its maximum")
    return bounds


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
