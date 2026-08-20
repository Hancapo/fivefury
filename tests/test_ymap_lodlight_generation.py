from __future__ import annotations

import math

import pytest

from fivefury import Aabb3, Quaternion, Vector3
from fivefury.ydr import Ydr, YdrLight, YdrLightFlags, YdrLightType
from fivefury.ymap import (
    EntityDef,
    YmapEntityFlags,
    YmapLodLightCategory,
    YmapLodLightType,
    YmapPriorityLevel,
    calculate_lod_light_category,
    calculate_lod_light_hash,
    extract_lod_lights,
    validate_lod_light_source_bounds,
)


def test_lod_light_hash_matches_runtime_vectors() -> None:
    assert calculate_lod_light_hash(Aabb3(Vector3(), Vector3(1.0, 1.0, 1.0)), 0) == 0x18FE4FFF
    assert (
        calculate_lod_light_hash(
            Aabb3(Vector3(-12.34, -0.19, 4.99), Vector3(8.01, 2.25, 10.0)),
            7,
        )
        == 0x4686CB0F
    )


def test_lod_light_category_matches_runtime_rules() -> None:
    assert (
        calculate_lod_light_category(YdrLightType.POINT, 9.99, 2.0)
        == YmapLodLightCategory.SMALL
    )
    assert (
        calculate_lod_light_category(YdrLightType.POINT, 10.0, 1.0)
        == YmapLodLightCategory.MEDIUM
    )
    assert (
        calculate_lod_light_category(YdrLightType.CAPSULE, 2.0, 1.0, 6.0)
        == YmapLodLightCategory.MEDIUM
    )
    assert (
        calculate_lod_light_category(
            YdrLightType.POINT,
            1.0,
            0.1,
            flags=YdrLightFlags.FAR_LOD_LIGHT,
        )
        == YmapLodLightCategory.LARGE
    )


def test_extract_lod_lights_transforms_and_packs_source_light() -> None:
    ydr = Ydr(
        version=165,
        bounding_box_min=Vector3(-1.0, -1.0, -1.0),
        bounding_box_max=Vector3(1.0, 1.0, 1.0),
        lights=[
            YdrLight.point(
                position=Vector3(1.0, 0.0, 0.0),
                color=(10, 20, 30),
                intensity=20.0,
                falloff=5.0,
                flags=(
                    YdrLightFlags.CORONA_ONLY
                    | YdrLightFlags.DONT_USE_IN_CUTSCENE
                ),
                time_flags=0x123456,
                corona_size=1.0,
                corona_intensity=16.0,
            )
        ],
    )
    half_turn_z = math.sqrt(0.5)
    entity = EntityDef(
        position=Vector3(10.0, 20.0, 30.0),
        rotation=Quaternion(0.0, 0.0, half_turn_z, half_turn_z),
        scale_xy=2.0,
        scale_z=3.0,
    )

    generated = extract_lod_lights(
        ydr,
        entity,
        archetype_bounds=Aabb3(Vector3(-2.0, -2.0, -2.0), Vector3(2.0, 2.0, 2.0)),
        model_name="prop_streetlight_test",
    )

    assert len(generated) == 1
    result = generated[0]
    assert result.light.position.components == pytest.approx((10.0, 22.0, 30.0))
    assert result.light.light_type == YmapLodLightType.POINT
    assert result.light.time_flags == 0x123456
    assert result.light.is_street_light
    assert result.light.is_corona_only
    assert result.light.dont_use_in_cutscene
    assert result.light.colour == (10, 20, 30)
    assert result.light.intensity == 128
    assert result.light.corona_intensity == 128
    assert result.category == YmapLodLightCategory.SMALL


def test_extract_lod_lights_skips_non_required_non_fixed_entities() -> None:
    ydr = Ydr(
        version=165,
        bounding_box_min=Vector3(-1.0, -1.0, -1.0),
        bounding_box_max=Vector3(1.0, 1.0, 1.0),
        lights=[YdrLight.point()],
    )
    entity = EntityDef(priority_level=YmapPriorityLevel.OPTIONAL_HIGH)
    assert (
        extract_lod_lights(
            ydr,
            entity,
            archetype_bounds=Aabb3(Vector3(-1.0, -1.0, -1.0), Vector3(1.0, 1.0, 1.0)),
        )
        == []
    )

    entity.flags = YmapEntityFlags.IS_FIXED
    assert len(
        extract_lod_lights(
            ydr,
            entity,
            archetype_bounds=Aabb3(Vector3(-1.0, -1.0, -1.0), Vector3(1.0, 1.0, 1.0)),
        )
    ) == 1


def test_lod_light_source_bounds_reject_smaller_archetype() -> None:
    report = validate_lod_light_source_bounds(
        Aabb3(Vector3(-1.0, -1.0, -1.0), Vector3(0.9, 1.0, 1.0)),
        Aabb3(Vector3(-1.0, -1.0, -1.0), Vector3(1.0, 1.0, 1.0)),
    )

    assert report.errors[0].code == "ymap.lod_source.bounds.maximum"
