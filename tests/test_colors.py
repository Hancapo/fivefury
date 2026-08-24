from __future__ import annotations

import pytest

from fivefury import (
    CutDecalPayload,
    CutScreenFadePayload,
    GrassInstance,
    LightAttrDef,
    LodLight,
    Vector3,
    YdrLight,
    parse_bound_material_names,
    parse_css_argb,
    parse_css_rgb,
    parse_css_rgb_unit,
    parse_css_rgba,
)
from fivefury.ydr import YdrMeshInput, paint_mesh


def test_css_color_values_work_across_high_level_apis() -> None:
    assert parse_css_rgb("#f80") == (255, 136, 0)
    assert parse_css_rgba("#ff880080") == (255, 136, 0, 128)
    assert parse_css_rgb("rgb(255 128 0)") == (255, 128, 0)
    assert parse_css_rgb("rgba(100%, 50%, 0%, 0.5)") == (255, 128, 0)
    assert parse_css_rgb("hsl(30 100% 50%)") == (255, 128, 0)
    assert parse_css_argb("rgba(255 0 0 / 50%)") == 0x80FF0000
    assert parse_css_rgb_unit("#808000") == pytest.approx(
        (128 / 255.0, 128 / 255.0, 0.0)
    )

    assert (
        CutScreenFadePayload(1.0, color="rgba(0 0 0 / 50%)").to_fields()[
            "color"
        ]
        == 0x80000000
    )
    assert (
        CutDecalPayload(position=Vector3(), colour="#ff8800").to_fields()["Colour"]
        == 0xFFFF8800
    )
    assert YdrLight.point(color="orange").color == (255, 165, 0)
    assert GrassInstance(color="lime").color == (0, 255, 0)

    lod = LodLight()
    lod.colour = "hsl(240 100% 50%)"
    assert lod.colour == (0, 0, 255)

    light_attr = LightAttrDef(colour="#010203", vol_outer_colour="rgb(4 5 6)")
    assert light_attr.colour == (1, 2, 3)
    assert light_attr.vol_outer_colour == (4, 5, 6)

    library = parse_bound_material_names("DEFAULT | hotpink\nROCK | #123\n")
    assert library.get_color(0) == (255, 105, 180)
    assert library.get_color(1) == (17, 34, 51)

    mesh = YdrMeshInput(material="mat", positions=[Vector3()], indices=[0])
    paint_mesh(mesh, "rgba(255 128 0 / 25%)")
    assert mesh.colours0[0] == pytest.approx(
        (1.0, 128 / 255.0, 0.0, 64 / 255.0)
    )
