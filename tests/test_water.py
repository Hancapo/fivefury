from __future__ import annotations

import math

import pytest

from fivefury import (
    GameFileCache,
    GameFileType,
    WaterCalmingQuad,
    WaterCornerAlphas,
    WaterData,
    WaterQuad,
    WaterQuadType,
    WaterValidationError,
    WaterWaveQuad,
    create_water,
    read_water,
)
from fivefury.gamefile import guess_game_file_type

SAMPLE_WATER_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<WaterData>
  <WaterQuads>
    <Item>
      <minX value="-16" />
      <maxX value="32" />
      <minY value="64" />
      <maxY value="128" />
      <Type value="3" />
      <IsInvisible value="false" />
      <HasLimitedDepth value="true" />
      <z value="12.5" />
      <a1 value="10" />
      <a2 value="20" />
      <a3 value="30" />
      <a4 value="40" />
      <NoStencil value="true" />
    </Item>
  </WaterQuads>
  <CalmingQuads>
    <Item>
      <minX value="-8" />
      <maxX value="8" />
      <minY value="-4" />
      <maxY value="4" />
      <fDampening value="0.25" />
    </Item>
  </CalmingQuads>
  <WaveQuads>
    <Item>
      <minX value="-32" />
      <maxX value="32" />
      <minY value="-64" />
      <maxY value="64" />
      <Amplitude value="1.5" />
      <XDirection value="-0.8" />
      <YDirection value="0.6" />
    </Item>
  </WaveQuads>
</WaterData>
"""


def test_read_water_maps_every_game_field() -> None:
    water = read_water(SAMPLE_WATER_XML)

    assert len(water.water_quads) == 1
    assert len(water.calming_quads) == 1
    assert len(water.wave_quads) == 1

    surface = water.water_quads[0]
    assert surface.type is WaterQuadType.TRIANGLE_C
    assert surface.has_limited_depth
    assert surface.no_stencil
    assert surface.z == 12.5
    assert surface.alphas == (10, 20, 30, 40)
    assert surface.alpha_ne == 30
    assert surface.alpha_nw == 40
    assert surface.corners() == (
        (32.0, 64.0, 12.5),
        (32.0, 128.0, 12.5),
        (-16.0, 128.0, 12.5),
    )

    assert water.calming_quads[0].dampening == 0.25
    assert water.wave_quads[0].direction == (-0.8, 0.6)
    assert water.validate() == []


def test_water_xml_semantic_roundtrip() -> None:
    original = read_water(SAMPLE_WATER_XML)
    rebuilt = read_water(original.to_xml_bytes())

    assert rebuilt == original


def test_water_declarative_components_and_generic_add() -> None:
    surface = WaterQuad(
        min_x=0,
        min_y=0,
        max_x=100,
        max_y=50,
        z=4.0,
        type=WaterQuadType.RECTANGLE,
        alpha_sw=26,
        alpha_se=26,
        alpha_nw=26,
        alpha_ne=26,
    )
    calming = WaterCalmingQuad(
        min_x=10,
        min_y=10,
        max_x=90,
        max_y=40,
        dampening=0.2,
    )
    wave = WaterWaveQuad.from_angle(
        bounds=(0, 0, 100, 50),
        amplitude=1.0,
        degrees=90.0,
    )
    water = create_water(surface)

    water.calming_quads.append(calming)
    water.wave_quads.append(wave)
    assert water.quads is water.water_quads
    assert surface.area == 5000.0
    assert math.isclose(wave.direction_x, 0.0, abs_tol=1e-12)
    assert math.isclose(wave.direction_y, 1.0, abs_tol=1e-12)
    rebuilt = read_water(water.to_bytes())
    assert rebuilt.water_quads == water.water_quads
    assert rebuilt.calming_quads == water.calming_quads
    assert rebuilt.wave_quads[0].amplitude == wave.amplitude
    assert math.isclose(
        rebuilt.wave_quads[0].direction_x,
        wave.direction_x,
        abs_tol=1e-12,
    )
    assert math.isclose(
        rebuilt.wave_quads[0].direction_y,
        wave.direction_y,
        abs_tol=1e-12,
    )


def test_water_geometry_helpers_create_and_query_real_shapes() -> None:
    rectangle = WaterQuad.rectangle(
        center=(100.0, 200.0, 12.5),
        size=(80.0, 40.0),
        alpha=32,
        limited_depth=True,
    )
    triangle = WaterQuad.triangle(
        center=(100.0, 200.0, 15.0),
        size=(80.0, 40.0),
        shape=WaterQuadType.TRIANGLE_A,
        alpha=WaterCornerAlphas(
            southwest=10,
            southeast=20,
            northeast=30,
            northwest=40,
        ),
    )
    hidden = WaterQuad.rectangle(
        center=(100.0, 200.0, 20.0),
        size=(10.0, 10.0),
        invisible=True,
    )
    water = WaterData().extend((rectangle, triangle, hidden))

    assert rectangle.alphas == (32, 32, 32, 32)
    assert rectangle.has_limited_depth
    assert rectangle.center == (100.0, 200.0, 12.5)
    assert triangle.alphas == (10, 20, 30, 40)
    assert triangle.contains_xy(70.0, 190.0)
    assert not triangle.contains_xy(130.0, 210.0)
    assert water.bounds == (60, 180, 140, 220)
    assert water.surfaces_at(100.0, 200.0) == [
        rectangle,
        triangle,
        hidden,
    ]
    assert water.surfaces_at(
        100.0,
        200.0,
        include_invisible=False,
    ) == [rectangle, triangle]


@pytest.mark.parametrize(
    ("shape", "inside", "outside"),
    [
        (WaterQuadType.TRIANGLE_A, (1.0, 1.0), (9.0, 9.0)),
        (WaterQuadType.TRIANGLE_B, (1.0, 9.0), (9.0, 1.0)),
        (WaterQuadType.TRIANGLE_C, (9.0, 9.0), (1.0, 1.0)),
        (WaterQuadType.TRIANGLE_D, (9.0, 1.0), (1.0, 9.0)),
    ],
)
def test_water_triangle_queries_follow_the_selected_corner(
    shape: WaterQuadType,
    inside: tuple[float, float],
    outside: tuple[float, float],
) -> None:
    triangle = WaterQuad.triangle(
        center=(5.0, 5.0, 0.0),
        size=(10.0, 10.0),
        shape=shape,
    )

    assert triangle.contains_xy(*inside)
    assert not triangle.contains_xy(*outside)


def test_water_region_helpers_and_translation() -> None:
    calming = WaterCalmingQuad.rectangle(
        center=(0.0, 0.0),
        size=(20.0, 10.0),
        dampening=0.25,
    )
    wave = WaterWaveQuad.from_center(
        center=(0.0, 0.0),
        size=(20.0, 10.0),
        amplitude=2.0,
        degrees=180.0,
    )
    water = create_water(calming, wave).translate(x=50, y=-25, z=100.0)

    assert water.bounds == (40, -30, 60, -20)
    assert (calming.min_x, calming.min_y) == (40, -30)
    assert (wave.max_x, wave.max_y) == (60, -20)
    assert wave.direction_x == pytest.approx(-1.0)
    assert wave.direction_y == pytest.approx(0.0, abs=1e-12)


def test_centered_water_helpers_reject_fractional_game_bounds() -> None:
    with pytest.raises(
        ValueError,
        match="must produce integer water bounds",
    ):
        WaterQuad.rectangle(
            center=(0.25, 0.0, 0.0),
            size=(10.0, 10.0),
        )

    with pytest.raises(ValueError, match="x translation"):
        WaterData().translate(x=0.5)


def test_water_writer_reports_actionable_validation_errors() -> None:
    water = WaterData(
        water_quads=[
            WaterQuad(
                min_x=20,
                min_y=0,
                max_x=10,
                max_y=10,
                z=1e100,
                type=9,
                alpha_sw=300,
            )
        ],
        calming_quads=[
            WaterCalmingQuad(
                min_x=0,
                min_y=0,
                max_x=10,
                max_y=10,
                dampening=1.0,
            )
        ],
    )

    with pytest.raises(WaterValidationError) as exc_info:
        water.to_xml_bytes()

    message = str(exc_info.value)
    assert "water_quads[0].min_x must be lower than max_x" in message
    assert "water_quads[0].z must fit a finite 32-bit float" in message
    assert "water_quads[0].type must be between 0 and 4" in message
    assert "water_quads[0].alpha_sw must be between 0 and 255" in message
    assert "calming_quads[0].dampening" in message


def test_water_requires_the_native_root_name() -> None:
    with pytest.raises(ValueError, match="Expected WaterData"):
        read_water(b"<NotWater />")


def test_empty_stripped_water_item_is_semantically_ignored() -> None:
    water = read_water(b"<WaterData><WaterQuads><Item /></WaterQuads></WaterData>")

    assert water.water_quads == []
    assert read_water(water.to_xml_bytes()) == water


def test_water_xml_is_classified_without_claiming_waterheight_dat() -> None:
    assert (
        guess_game_file_type("common/data/levels/gta5/water.xml") is GameFileType.WATER
    )
    assert guess_game_file_type("waterheight.dat") is GameFileType.UNKNOWN


def test_game_file_cache_loads_loose_water_xml(tmp_path) -> None:
    path = tmp_path / "common" / "data" / "levels" / "custom" / "water.xml"
    path.parent.mkdir(parents=True)
    path.write_bytes(SAMPLE_WATER_XML)
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)

    game_file = cache.get_file("common/data/levels/custom/water.xml")

    assert game_file is not None
    assert game_file.kind is GameFileType.WATER
    assert isinstance(game_file.parsed, WaterData)
    assert cache.kind_counts[GameFileType.WATER] == 1
    assert len(cache.WaterDict) == 1
