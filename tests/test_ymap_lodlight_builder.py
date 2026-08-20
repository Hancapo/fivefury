from __future__ import annotations

from fivefury import Aabb3, Quaternion, Vector3
from fivefury.ydr import Ydr, YdrLight
from fivefury.ymap import (
    EntityDef,
    GeneratedLodLight,
    LodLight,
    LodLightSourceInstance,
    YmapContentFlags,
    YmapFlags,
    YmapLodLightCategory,
    build_lod_light_maps,
    build_lod_light_maps_from_sources,
    read_ymap,
    save_lod_light_maps,
)


def _generated_light(
    light_hash: int,
    position: Vector3,
    *,
    category: YmapLodLightCategory = YmapLodLightCategory.SMALL,
    street: bool = False,
) -> GeneratedLodLight:
    light = LodLight(position=position, hash=light_hash, rgbi=0x80402010)
    light.is_street_light = street
    return GeneratedLodLight(
        light=light,
        category=category,
        physical_bounds=Aabb3(
            position - Vector3(1.0, 1.0, 1.0),
            position + Vector3(1.0, 1.0, 1.0),
        ),
        source_light_index=light_hash,
        source_model_name=f"model_{light_hash}",
    )


def test_build_lod_light_maps_creates_runtime_parent_child_pair() -> None:
    lights = [
        _generated_light(5, Vector3(10.0, 20.0, 30.0), street=True),
        _generated_light(2, Vector3(20.0, 30.0, 40.0)),
        _generated_light(3, Vector3(30.0, 40.0, 50.0), street=True),
        _generated_light(1, Vector3(40.0, 50.0, 60.0)),
    ]

    pairs = build_lod_light_maps(lights, name_prefix="custom")

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.validate().valid
    assert pair.distant.name.text == "custom_DistLODLights_small000"
    assert pair.lod.name.text == "custom_LODLights_small000"
    assert int(pair.lod.parent) == int(pair.distant.name)
    assert pair.distant.flags == YmapFlags.IS_PARENT
    assert pair.distant.content_flags == YmapContentFlags.DISTANT_LOD_LIGHTS
    assert pair.lod.content_flags == YmapContentFlags.LOD_LIGHTS
    assert pair.distant.distant_lod_lights is not None
    assert pair.distant.distant_lod_lights.num_street_lights == 2
    assert pair.lod.lod_lights is not None
    assert pair.lod.lod_lights.hash == [3, 5, 1, 2]
    assert pair.distant.entities_extents_min == Vector3(9.0, 19.0, 29.0)
    assert pair.distant.entities_extents_max == Vector3(41.0, 51.0, 61.0)
    assert pair.distant.streaming_extents_min == Vector3(-440.0, -430.0, -420.0)
    assert pair.lod.streaming_extents_max == Vector3(490.0, 500.0, 510.0)


def test_build_lod_light_maps_partitions_dense_categories() -> None:
    lights = [
        _generated_light(index + 1, Vector3(float(index), 0.0, 0.0))
        for index in range(801)
    ]

    pairs = build_lod_light_maps(lights)

    assert len(pairs) == 2
    counts = [len(pair.lod.lod_lights or ()) for pair in pairs]
    assert max(counts) <= 800
    assert sum(counts) == 801
    assert {
        light_hash
        for pair in pairs
        if pair.lod.lod_lights is not None
        for light_hash in pair.lod.lod_lights.hash
    } == set(range(1, 802))


def test_build_lod_light_maps_supports_script_controlled_groups() -> None:
    pairs = build_lod_light_maps(
        [
            _generated_light(1, Vector3()),
            _generated_light(
                2,
                Vector3(1.0, 0.0, 0.0),
                category=YmapLodLightCategory.LARGE,
            ),
        ],
        script_group_name="mission_lights",
    )

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.category == YmapLodLightCategory.MEDIUM
    assert pair.distant.name.text == "mission_lights_DistantLights"
    assert pair.lod.name.text == "mission_lights_LODLights"
    assert pair.distant.flags == YmapFlags.IS_PARENT | YmapFlags.MANUAL_STREAM_ONLY
    assert pair.lod.flags == YmapFlags.MANUAL_STREAM_ONLY


def test_build_lod_light_maps_rejects_hash_collisions() -> None:
    lights = [
        _generated_light(1, Vector3()),
        _generated_light(1, Vector3(10.0, 0.0, 0.0)),
    ]

    try:
        build_lod_light_maps(lights)
    except ValueError as exc:
        assert "hash collision 0x00000001" in str(exc)
    else:
        raise AssertionError("expected a LOD-light hash collision")


def test_generated_lod_light_maps_roundtrip_and_save(tmp_path) -> None:
    pair = build_lod_light_maps(
        [_generated_light(0x12345678, Vector3(1.0, 2.0, 3.0))]
    )[0]

    distant = read_ymap(pair.distant.to_bytes())
    lod = read_ymap(pair.lod.to_bytes())
    assert distant.distant_lod_lights is not None
    assert distant.distant_lod_lights.position == [Vector3(1.0, 2.0, 3.0)]
    assert lod.lod_lights is not None
    assert lod.lod_lights.hash == [0x12345678]

    paths = save_lod_light_maps([pair], tmp_path)
    assert {path.name for path in paths} == {
        "DistLODLights_small000.ymap",
        "LODLights_small000.ymap",
    }
    assert all(path.read_bytes().startswith(b"RSC7") for path in paths)


def test_build_lod_light_maps_from_source_instances() -> None:
    source = LodLightSourceInstance(
        ydr=Ydr(
            version=165,
            bounding_box_min=Vector3(-1.0, -1.0, -1.0),
            bounding_box_max=Vector3(1.0, 1.0, 1.0),
            lights=[YdrLight.point(intensity=1.0, falloff=2.0)],
        ),
        entity=EntityDef(position=Vector3(10.0, 20.0, 30.0), rotation=Quaternion()),
        archetype_bounds=Aabb3(Vector3(-1.0, -1.0, -1.0), Vector3(1.0, 1.0, 1.0)),
        model_name="custom_light",
    )

    pairs = build_lod_light_maps_from_sources([source], name_prefix="source")

    assert len(pairs) == 1
    assert pairs[0].lod.lod_lights is not None
    assert len(pairs[0].lod.lod_lights) == 1
