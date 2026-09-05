import struct

import pytest

from fivefury import BuildContext, GameTarget, YmapEntityFlags
from fivefury.meta.defs import meta_name
from fivefury.resource import split_rsc7_sections
from fivefury.ymap import EntityDef, MloInstanceDef, Ymap
from tests.test_meta_rpf_contracts import _parse_meta_layout


@pytest.mark.parametrize(
    "name,value",
    [
        ("FULLMATRIX", 0x1),
        ("STREAM_LOWPRIORITY", 0x2),
        ("DONT_INSTANCE_COLLISION", 0x4),
        ("LOD_IS_IN_PARENT_MAPDATA", 0x8),
        ("LOD_ADOPTME", 0x10),
        ("IS_FIXED", 0x20),
        ("IS_INTERIOR_LOD", 0x40),
        ("IPL_LIGHTS_CAST_STATIC_SHADOWS", 0x80),
        ("IPL_LIGHTS_CAST_DYNAMIC_SHADOWS", 0x100),
        ("IPL_LIGHTS_IGNORE_DAY_NIGHT_SETTINGS", 0x200),
        ("DRAWABLELODUSEALTFADE", 0x8000),
        ("UNUSED", 0x10000),
        ("DOESNOTTOUCHWATER", 0x20000),
        ("DOESNOTSPAWNPEDS", 0x40000),
        ("LIGHTS_CAST_STATIC_SHADOWS", 0x80000),
        ("LIGHTS_CAST_DYNAMIC_SHADOWS", 0x100000),
        ("LIGHTS_IGNORE_DAY_NIGHT_SETTINGS", 0x200000),
        ("DONT_RENDER_IN_SHADOWS", 0x400000),
        ("ONLY_RENDER_IN_SHADOWS", 0x800000),
        ("DONT_RENDER_IN_REFLECTIONS", 0x1000000),
        ("ONLY_RENDER_IN_REFLECTIONS", 0x2000000),
        ("DONT_RENDER_IN_WATER_REFLECTIONS", 0x4000000),
        ("ONLY_RENDER_IN_WATER_REFLECTIONS", 0x8000000),
        ("DONT_RENDER_IN_MIRROR_REFLECTIONS", 0x10000000),
        ("ONLY_RENDER_IN_MIRROR_REFLECTIONS", 0x20000000),
    ],
)
def test_entity_flag_numeric_layout(name, value):
    assert int(YmapEntityFlags[name]) == value


def test_numeric_shadow_flags_are_not_reflection_only():
    flags = YmapEntityFlags(1572864)
    assert flags == (
        YmapEntityFlags.LIGHTS_CAST_STATIC_SHADOWS
        | YmapEntityFlags.LIGHTS_CAST_DYNAMIC_SHADOWS
    )
    assert not flags & YmapEntityFlags.ONLY_RENDER_IN_WATER_REFLECTIONS
    assert not flags & YmapEntityFlags.IPL_LIGHTS_CAST_STATIC_SHADOWS


@pytest.mark.parametrize(
    "entity_type,meta_type",
    [(EntityDef, "CEntityDef"), (MloInstanceDef, "CMloInstanceDef")],
)
@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize("raw", [0x180000, 0x180, 0x8000000, 0xC0007C00, 0xFFFFFFFF])
def test_raw_flags_survive_binary_serialization(entity_type, meta_type, game, raw):
    asset = Ymap(
        name="flag_roundtrip", entities=[entity_type(archetype_name="model", flags=raw)]
    )
    data = asset.to_bytes(context=BuildContext(game=game), validate=False)
    layout = _parse_meta_layout(data)
    _, system, _ = split_rsc7_sections(data)
    pointer = next(
        pointer
        for name, _, pointer in layout["data_blocks"]
        if name == meta_name(meta_type)
    )
    assert struct.unpack_from("<I", system, pointer - 0x50000000 + 12)[0] == raw
    restored = Ymap.from_bytes(data)
    assert int(restored.entities[0].flags) == raw
    assert int(entity_type.from_meta(restored.entities[0].to_meta()).flags) == raw
