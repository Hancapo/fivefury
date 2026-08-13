from __future__ import annotations

import pytest

from fivefury import DistantLodLightsSoa, LodLight, LodLightsSoa, Ymap


def _lod_light() -> LodLight:
    light = LodLight(
        position=(10.0, 20.0, 30.0),
        direction=(0.0, 0.0, -1.0),
        falloff=12.0,
        falloff_exponent=2.0,
        hash=0x12345678,
        rgbi=0xFFCC8844,
    )
    light.cone_inner_angle_degrees = 30.0
    light.cone_outer_angle_degrees = 45.0
    light.corona_intensity_value = 4.0
    return light


def test_typed_lod_light_authoring_roundtrip() -> None:
    source = Ymap(name="typed_lights")
    source.add_lod_light(_lod_light())

    parsed = Ymap.from_bytes(source.to_bytes())

    assert parsed.lod_lights is not None
    assert parsed.distant_lod_lights is not None
    assert parsed.lod_lights.direction == [(0.0, 0.0, -1.0)]
    assert parsed.lod_lights.hash == [0x12345678]
    assert parsed.distant_lod_lights.position == [(10.0, 20.0, 30.0)]
    assert parsed.distant_lod_lights.RGBI == [0xFFCC8844]


def test_official_lod_child_and_distant_parent_shapes_roundtrip() -> None:
    lod = LodLightsSoa()
    lod.append(_lod_light())
    lod_child = Ymap(name="lodlights_small000", parent="distlodlights_small000", lod_lights=lod)
    distant_parent = Ymap(
        name="distlodlights_small000",
        distant_lod_lights=DistantLodLightsSoa(
            position=[(10.0, 20.0, 30.0)],
            RGBI=[0xFFCC8844],
        ),
    )

    parsed_child = Ymap.from_bytes(lod_child.to_bytes())
    parsed_parent = Ymap.from_bytes(distant_parent.to_bytes())

    assert parsed_child.parent == "distlodlights_small000"
    assert parsed_child.lod_lights is not None
    assert parsed_child.distant_lod_lights is not None
    assert len(parsed_child.lod_lights) == 1
    assert len(parsed_child.distant_lod_lights) == 0
    assert parsed_parent.lod_lights is not None
    assert parsed_parent.distant_lod_lights is not None
    assert len(parsed_parent.lod_lights) == 0
    assert len(parsed_parent.distant_lod_lights) == 1


@pytest.mark.parametrize(
    "ymap",
    [
        Ymap(name="bad_lod", lod_lights=LodLightsSoa(direction=[(0.0, 0.0, -1.0)])),
        Ymap(
            name="bad_distant",
            distant_lod_lights=DistantLodLightsSoa(position=[(0.0, 0.0, 0.0)]),
        ),
    ],
)
def test_light_soa_length_mismatches_are_rejected(ymap: Ymap) -> None:
    with pytest.raises(ValueError, match="Invalid YMAP light arrays"):
        ymap.to_bytes()
