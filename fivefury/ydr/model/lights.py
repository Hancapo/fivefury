from __future__ import annotations

import dataclasses
import enum

from ...colors import CssColor, parse_css_rgb
from ...vector import Vector3


class YdrLightType(enum.IntEnum):
    POINT = 1
    SPOT = 2
    CAPSULE = 4


class YdrLightFlags(enum.IntFlag):
    NONE = 0
    INTERIOR_ONLY = 1 << 0
    EXTERIOR_ONLY = 1 << 1
    DONT_USE_IN_CUTSCENE = 1 << 2
    VEHICLE = 1 << 3
    FX = 1 << 4
    TEXTURE_PROJECTION = 1 << 5
    CAST_SHADOWS = 1 << 6
    CAST_STATIC_GEOM_SHADOWS = 1 << 7
    CAST_DYNAMIC_GEOM_SHADOWS = 1 << 8
    CALC_FROM_SUN = 1 << 9
    ENABLE_BUZZING = 1 << 10
    FORCE_BUZZING = 1 << 11
    DRAW_VOLUME = 1 << 12
    NO_SPECULAR = 1 << 13
    BOTH_INTERIOR_AND_EXTERIOR = 1 << 14
    CORONA_ONLY = 1 << 15
    NOT_IN_REFLECTION = 1 << 16
    ONLY_IN_REFLECTION = 1 << 17
    USE_CULL_PLANE = 1 << 18
    USE_VOLUME_OUTER_COLOUR = 1 << 19
    CAST_HIGHER_RES_SHADOWS = 1 << 20
    CAST_ONLY_LOWRES_SHADOWS = 1 << 21
    FAR_LOD_LIGHT = 1 << 22
    DONT_LIGHT_ALPHA = 1 << 23
    CAST_SHADOWS_IF_POSSIBLE = 1 << 24
    CUTSCENE = 1 << 25
    MOVING_LIGHT_SOURCE = 1 << 26
    USE_VEHICLE_TWIN = 1 << 27
    FORCE_MEDIUM_LOD_LIGHT = 1 << 28
    CORONA_ONLY_LOD_LIGHT = 1 << 29
    DELAY_RENDER = 1 << 30
    ALREADY_TESTED_FOR_OCCLUSION = 1 << 31


@dataclasses.dataclass(slots=True)
class YdrLight:
    position: Vector3 = dataclasses.field(default_factory=Vector3)
    color: tuple[int, int, int] | CssColor = (255, 255, 255)
    flashiness: int = 0
    intensity: float = 1.0
    flags: YdrLightFlags | int = YdrLightFlags.NONE
    bone_id: int = 0
    light_type: YdrLightType = YdrLightType.POINT
    group_id: int = 0
    time_flags: int = 0
    falloff: float = 0.0
    falloff_exponent: float = 0.0
    culling_plane_normal: Vector3 = dataclasses.field(default_factory=Vector3)
    culling_plane_offset: float = 0.0
    shadow_blur: int = 0
    volume_intensity: float = 0.0
    volume_size_scale: float = 0.0
    volume_outer_color: tuple[int, int, int] | CssColor = (0, 0, 0)
    light_hash: int = 0
    volume_outer_intensity: float = 0.0
    corona_size: float = 0.0
    volume_outer_exponent: float = 0.0
    light_fade_distance: int = 0
    shadow_fade_distance: int = 0
    specular_fade_distance: int = 0
    volumetric_fade_distance: int = 0
    shadow_near_clip: float = 0.0
    corona_intensity: float = 0.0
    corona_z_bias: float = 0.0
    direction: Vector3 = dataclasses.field(
        default_factory=lambda: Vector3(0.0, 0.0, 1.0)
    )
    tangent: Vector3 = dataclasses.field(default_factory=lambda: Vector3(1.0, 0.0, 0.0))
    cone_inner_angle: float = 0.0
    cone_outer_angle: float = 0.0
    extent: Vector3 = dataclasses.field(default_factory=Vector3)
    projected_texture_hash: int = 0
    unknown_0h: int = 0
    unknown_4h: int = 0
    unknown_14h: int = 0
    unknown_45h: int = 0
    unknown_46h: int = 0
    unknown_48h: int = 0
    unknown_a4h: int = 0

    def __post_init__(self) -> None:
        for name in (
            "position",
            "culling_plane_normal",
            "direction",
            "tangent",
            "extent",
        ):
            if not isinstance(getattr(self, name), Vector3):
                raise TypeError(f"YdrLight.{name} must be a Vector3")
        self.color = parse_css_rgb(self.color)
        self.volume_outer_color = parse_css_rgb(self.volume_outer_color)
        self.flags = YdrLightFlags(int(self.flags))

    @classmethod
    def point(
        cls,
        *,
        position: Vector3 = Vector3(),
        color: tuple[int, int, int] | CssColor = (255, 255, 255),
        intensity: float = 1.0,
        falloff: float = 0.0,
        flags: int = 0,
        bone_id: int = 0,
        group_id: int = 0,
        time_flags: int = 0,
        **overrides: object,
    ) -> YdrLight:
        return cls(
            position=position,
            color=parse_css_rgb(color),
            intensity=float(intensity),
            falloff=float(falloff),
            flags=int(flags),
            bone_id=int(bone_id),
            light_type=YdrLightType.POINT,
            group_id=int(group_id),
            time_flags=int(time_flags),
            **overrides,
        )

    @classmethod
    def spot(
        cls,
        *,
        position: Vector3 = Vector3(),
        direction: Vector3 = Vector3(0.0, 0.0, -1.0),
        color: tuple[int, int, int] | CssColor = (255, 255, 255),
        intensity: float = 1.0,
        falloff: float = 0.0,
        cone_inner_angle: float = 0.0,
        cone_outer_angle: float = 0.0,
        flags: int = 0,
        bone_id: int = 0,
        group_id: int = 0,
        time_flags: int = 0,
        **overrides: object,
    ) -> YdrLight:
        return cls(
            position=position,
            direction=direction,
            color=parse_css_rgb(color),
            intensity=float(intensity),
            falloff=float(falloff),
            cone_inner_angle=float(cone_inner_angle),
            cone_outer_angle=float(cone_outer_angle),
            flags=int(flags),
            bone_id=int(bone_id),
            light_type=YdrLightType.SPOT,
            group_id=int(group_id),
            time_flags=int(time_flags),
            **overrides,
        )

    @classmethod
    def capsule(
        cls,
        *,
        position: Vector3 = Vector3(),
        extent: Vector3 = Vector3(),
        color: tuple[int, int, int] | CssColor = (255, 255, 255),
        intensity: float = 1.0,
        falloff: float = 0.0,
        flags: int = 0,
        bone_id: int = 0,
        group_id: int = 0,
        time_flags: int = 0,
        **overrides: object,
    ) -> YdrLight:
        return cls(
            position=position,
            extent=extent,
            color=parse_css_rgb(color),
            intensity=float(intensity),
            falloff=float(falloff),
            flags=int(flags),
            bone_id=int(bone_id),
            light_type=YdrLightType.CAPSULE,
            group_id=int(group_id),
            time_flags=int(time_flags),
            **overrides,
        )
