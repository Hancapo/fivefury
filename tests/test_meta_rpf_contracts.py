from __future__ import annotations

import io
import os
import struct
import tempfile
import time
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from fivefury.meta import RawStruct
from fivefury.meta.defs import meta_name
from tests.compat import PytestCompat
from tests.helpers import resolve_symbol, touch, write_bytes

_DAT_VIRTUAL_BASE = 0x50000000
_DAT_PHYSICAL_BASE = 0x60000000
_GTAV_TEX_SIZE = 0x98
_ENHANCED_TEX_SIZE = 0xA0


def _static_or_function(symbol, method_names, *args, **kwargs):
    value = symbol.value
    if callable(value) and not isinstance(value, type):
        return value(*args, **kwargs)
    for method_name in method_names:
        method = getattr(value, method_name, None)
        if callable(method):
            return method(*args, **kwargs)
    raise AssertionError(
        f"Could not resolve a callable from {symbol.module_name}.{symbol.symbol_name}"
    )


def _make_ymap(name: str = "unit_test.ymap"):
    ymap_symbol = resolve_symbol(
        ["fivefury.ymap", "fivefury"],
        ["Ymap"],
    )
    if ymap_symbol is None:
        return None
    value = ymap_symbol.value
    if isinstance(value, type):
        return value(name=name)
    if callable(value):
        return value(name)
    return None


def _make_entity(archetype_name: str = "prop_tree_pine_01", **kwargs):
    entity_symbol = resolve_symbol(
        ["fivefury.ymap", "fivefury"],
        ["Entity", "EntityDef"],
    )
    if entity_symbol is None:
        return None
    value = entity_symbol.value
    if isinstance(value, type):
        return value(archetype_name=archetype_name, **kwargs)
    if callable(value):
        return value(archetype_name=archetype_name, **kwargs)
    return None


def _try_surface_constructor(module_names, symbol_names, kwargs, fallback):
    symbol = resolve_symbol(module_names, symbol_names)
    if symbol is None:
        return fallback
    value = symbol.value
    if isinstance(value, type):
        try:
            return value(**kwargs)
        except TypeError:
            return fallback
    if callable(value):
        try:
            return value(**kwargs)
        except TypeError:
            return fallback
    return fallback


def _raw_lod_light():
    return RawStruct(meta_name("CLODLight"), bytes(136))


def _raw_distant_lod_light():
    return RawStruct(meta_name("CDistantLODLight"), bytes(48))


def _raw_box_occluder():
    return {
        "iCenterX": 0,
        "iCenterY": 0,
        "iCenterZ": 0,
        "iCosZ": 0,
        "iLength": 0,
        "iWidth": 0,
        "iHeight": 0,
        "iSinZ": 0,
        "_meta_name_hash": meta_name("BoxOccluder"),
    }


def _raw_occlude_model():
    return {
        "bmin": (0.0, 0.0, 0.0),
        "bmax": (0.0, 0.0, 0.0),
        "dataSize": 0,
        "verts": b"",
        "numVertsInBytes": 0,
        "numTris": 0,
        "flags": 0,
        "_meta_name_hash": meta_name("OccludeModel"),
    }


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _build_test_ytd_bytes(*, enhanced: bool = False) -> bytes:
    from fivefury.resource import build_rsc7
    from fivefury.texture import BCFormat, BC_TO_DX9, BC_TO_RSC8, row_pitch

    name = b"test_diffuse\x00"
    pixel_data = b"\x11\x22\x33\x44\x55\x66\x77\x88"
    count = 1
    dict_size = 0x40
    keys_offset = dict_size
    ptrs_offset = _align(keys_offset + 4 * count, 16)
    tex_size = _ENHANCED_TEX_SIZE if enhanced else _GTAV_TEX_SIZE
    textures_offset = _align(ptrs_offset + 8 * count, 16)
    name_offset = textures_offset + tex_size
    virtual_size = _align(name_offset + len(name), 16)

    vbuf = bytearray(virtual_size)
    pbuf = bytearray(pixel_data)

    vbuf[0x28:0x2A] = count.to_bytes(2, "little")
    vbuf[0x30:0x38] = (_DAT_VIRTUAL_BASE + ptrs_offset).to_bytes(8, "little")
    vbuf[keys_offset:keys_offset + 4] = (0x12345678).to_bytes(4, "little")
    vbuf[ptrs_offset:ptrs_offset + 8] = (_DAT_VIRTUAL_BASE + textures_offset).to_bytes(8, "little")
    vbuf[name_offset:name_offset + len(name)] = name

    tex_off = textures_offset
    vbuf[tex_off + 0x28:tex_off + 0x30] = (_DAT_VIRTUAL_BASE + name_offset).to_bytes(8, "little")
    if enhanced:
        vbuf[tex_off + 0x18:tex_off + 0x1A] = (4).to_bytes(2, "little")
        vbuf[tex_off + 0x1A:tex_off + 0x1C] = (4).to_bytes(2, "little")
        vbuf[tex_off + 0x1F] = int(BC_TO_RSC8[BCFormat.BC1])
        vbuf[tex_off + 0x22] = 1
        vbuf[tex_off + 0x38:tex_off + 0x40] = (_DAT_PHYSICAL_BASE).to_bytes(8, "little")
        version = 5
    else:
        vbuf[tex_off + 0x50:tex_off + 0x52] = (4).to_bytes(2, "little", signed=True)
        vbuf[tex_off + 0x52:tex_off + 0x54] = (4).to_bytes(2, "little", signed=True)
        vbuf[tex_off + 0x56:tex_off + 0x58] = row_pitch(4, BCFormat.BC1).to_bytes(2, "little")
        vbuf[tex_off + 0x58:tex_off + 0x5C] = int(BC_TO_DX9[BCFormat.BC1]).to_bytes(4, "little")
        vbuf[tex_off + 0x5D] = 1
        vbuf[tex_off + 0x70:tex_off + 0x78] = (_DAT_PHYSICAL_BASE).to_bytes(8, "little")
        version = 13

    return build_rsc7(bytes(vbuf), version=version, graphics_data=bytes(pbuf))


def _relocate_embedded_texture_dictionary(virtual_data: bytes, *, dict_offset: int, enhanced: bool) -> bytes:
    count = int.from_bytes(virtual_data[0x28:0x2A], "little")
    tex_size = _ENHANCED_TEX_SIZE if enhanced else _GTAV_TEX_SIZE
    ptrs_offset = int.from_bytes(virtual_data[0x30:0x38], "little") - _DAT_VIRTUAL_BASE
    output = bytearray(dict_offset + len(virtual_data))
    output[dict_offset : dict_offset + len(virtual_data)] = virtual_data
    delta = dict_offset

    def add_virtual_ptr(offset: int) -> None:
        value = int.from_bytes(output[dict_offset + offset : dict_offset + offset + 8], "little")
        if value:
            output[dict_offset + offset : dict_offset + offset + 8] = (value + delta).to_bytes(8, "little")

    add_virtual_ptr(0x08)
    add_virtual_ptr(0x20)
    add_virtual_ptr(0x30)

    for index in range(count):
        ptr_pos = dict_offset + ptrs_offset + (index * 8)
        tex_ptr = int.from_bytes(output[ptr_pos : ptr_pos + 8], "little")
        output[ptr_pos : ptr_pos + 8] = (tex_ptr + delta).to_bytes(8, "little")
        tex_off = int.from_bytes(
            virtual_data[ptrs_offset + (index * 8) : ptrs_offset + (index * 8) + 8],
            "little",
        ) - _DAT_VIRTUAL_BASE
        add_virtual_ptr(tex_off + 0x28)
        if enhanced:
            add_virtual_ptr(tex_off + 0x30)
    return bytes(output)


def _build_embedded_texture_resource(kind: str, *, enhanced: bool = False) -> bytes:
    from fivefury.resource import build_rsc7, split_rsc7_sections

    _, virtual_src, graphics_src = split_rsc7_sections(_build_test_ytd_bytes(enhanced=enhanced))
    kind_lower = kind.lower()

    if kind_lower == "ydr":
        shader_group_offset = 0x100
        dict_offset = 0x200
        system_size = dict_offset + len(virtual_src)
        system_data = bytearray(system_size)
        system_data[0x10:0x18] = (_DAT_VIRTUAL_BASE + shader_group_offset).to_bytes(8, "little")
        system_data[shader_group_offset + 0x08 : shader_group_offset + 0x10] = (_DAT_VIRTUAL_BASE + dict_offset).to_bytes(8, "little")
        system_data[dict_offset:] = _relocate_embedded_texture_dictionary(virtual_src, dict_offset=dict_offset, enhanced=enhanced)[dict_offset:]
        version = 159 if enhanced else 165
    elif kind_lower == "ydd":
        drawables_offset = 0x100
        drawable_offset = 0x120
        shader_group_offset = 0x200
        dict_offset = 0x280
        system_size = dict_offset + len(virtual_src)
        system_data = bytearray(system_size)
        system_data[0x30:0x38] = (_DAT_VIRTUAL_BASE + drawables_offset).to_bytes(8, "little")
        system_data[0x38:0x3A] = (1).to_bytes(2, "little")
        system_data[drawables_offset : drawables_offset + 8] = (_DAT_VIRTUAL_BASE + drawable_offset).to_bytes(8, "little")
        system_data[drawable_offset + 0x10 : drawable_offset + 0x18] = (_DAT_VIRTUAL_BASE + shader_group_offset).to_bytes(8, "little")
        system_data[shader_group_offset + 0x08 : shader_group_offset + 0x10] = (_DAT_VIRTUAL_BASE + dict_offset).to_bytes(8, "little")
        system_data[dict_offset:] = _relocate_embedded_texture_dictionary(virtual_src, dict_offset=dict_offset, enhanced=enhanced)[dict_offset:]
        version = 159 if enhanced else 165
    elif kind_lower == "yft":
        drawable_offset = 0x120
        shader_group_offset = 0x200
        dict_offset = 0x280
        system_size = dict_offset + len(virtual_src)
        system_data = bytearray(system_size)
        system_data[0x30:0x38] = (_DAT_VIRTUAL_BASE + drawable_offset).to_bytes(8, "little")
        system_data[drawable_offset + 0x10 : drawable_offset + 0x18] = (_DAT_VIRTUAL_BASE + shader_group_offset).to_bytes(8, "little")
        system_data[shader_group_offset + 0x08 : shader_group_offset + 0x10] = (_DAT_VIRTUAL_BASE + dict_offset).to_bytes(8, "little")
        system_data[dict_offset:] = _relocate_embedded_texture_dictionary(virtual_src, dict_offset=dict_offset, enhanced=enhanced)[dict_offset:]
        version = 171 if enhanced else 162
    elif kind_lower == "ypt":
        dict_offset = 0x100
        system_size = dict_offset + len(virtual_src)
        system_data = bytearray(system_size)
        system_data[0x20:0x28] = (_DAT_VIRTUAL_BASE + dict_offset).to_bytes(8, "little")
        system_data[dict_offset:] = _relocate_embedded_texture_dictionary(virtual_src, dict_offset=dict_offset, enhanced=enhanced)[dict_offset:]
        version = 71 if enhanced else 68
    else:
        raise ValueError(f"Unsupported embedded texture resource kind: {kind}")

    return build_rsc7(bytes(system_data), version=version, graphics_data=bytes(graphics_src))


class MetaAndArchiveContractTests(PytestCompat):
    def test_ymap_high_level_save_helper_if_available(self) -> None:
        ymap = _make_ymap("unit_test.ymap")
        if ymap is None:
            self.skipTest("Ymap API not available")

        helper = None
        for method_name in ("save", "save_ymap", "write", "write_ymap"):
            method = getattr(ymap, method_name, None)
            if callable(method):
                helper = method
                break
        if helper is None:
            self.skipTest("No save-like Ymap helper is implemented yet")

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "unit_test.ymap"
            result = helper(output)
            if isinstance(result, (str, os.PathLike)):
                output = Path(result)
            elif isinstance(result, (bytes, bytearray)):
                output.write_bytes(result)
            self.assertTrue(output.exists(), "save helper did not create a YMAP file")
            self.assertGreater(output.stat().st_size, 0, "saved YMAP file was empty")
            from fivefury.resource import parse_rsc7

            header, _ = parse_rsc7(output.read_bytes())
            self.assertEqual(header.version, 2)

    def test_ymap_and_ytyp_support_high_level_construction_helpers_if_available(self) -> None:
        ymap = _make_ymap("unit_test.ymap")
        ytyp_symbol = resolve_symbol(
            ["fivefury.ytyp", "fivefury"],
            ["Ytyp"],
        )
        if ymap is None or ytyp_symbol is None:
            self.skipTest("High-level constructors not available")

        ytyp_value = ytyp_symbol.value
        if isinstance(ytyp_value, type):
            ytyp = ytyp_value(name="unit_test.ytyp")
        elif callable(ytyp_value):
            ytyp = ytyp_value("unit_test.ytyp")
        else:
            ytyp = None

        if ymap is None and ytyp is None:
            self.skipTest("No class constructors were exposed")

        ymap_entity_helper = None
        if ymap is not None:
            for method_name in ("entity", "create_entity", "add_entity"):
                method = getattr(ymap, method_name, None)
                if callable(method):
                    ymap_entity_helper = method
                    break

        ytyp_archetype_helper = None
        if ytyp is not None:
            for method_name in ("archetype", "create_archetype", "add_archetype"):
                method = getattr(ytyp, method_name, None)
                if callable(method):
                    ytyp_archetype_helper = method
                    break

        if ymap_entity_helper is None and ytyp_archetype_helper is None:
            self.skipTest("No high-level entity/archetype builders are implemented yet")

        if ymap_entity_helper is not None:
            try:
                result = ymap_entity_helper(archetype_name="prop_tree_pine_01")
            except TypeError:
                if ymap_entity_helper.__name__ == "add_entity":
                    self.skipTest("Ymap.add_entity does not build entities yet")
                result = ymap_entity_helper()
            self.assertIsNotNone(result)

    def test_high_level_factories_default_to_empty_internal_resource_names(self) -> None:
        ymap = _make_ymap("unit_test.ymap")
        ytyp_symbol = resolve_symbol(
            ["fivefury.ytyp", "fivefury"],
            ["Ytyp"],
        )
        if ymap is None or ytyp_symbol is None:
            self.skipTest("High-level constructors not available")

        ytyp_value = ytyp_symbol.value
        if isinstance(ytyp_value, type):
            ytyp = ytyp_value(name="unit_test.ytyp")
        elif callable(ytyp_value):
            ytyp = ytyp_value("unit_test.ytyp")
        else:
            self.skipTest("Ytyp constructor is not callable")

        self.assertEqual(getattr(ymap, "meta_name", ""), "")
        self.assertEqual(getattr(ytyp, "meta_name", ""), "")
        self.assertEqual(getattr(ymap, "resource_name", ""), "")
        self.assertEqual(getattr(ytyp, "resource_name", ""), "")

    def test_models_expose_resource_name_property(self) -> None:
        ymap_symbol = resolve_symbol(
            ["fivefury.ymap", "fivefury"],
            ["Ymap"],
        )
        ytyp_symbol = resolve_symbol(
            ["fivefury.ytyp", "fivefury"],
            ["Ytyp"],
        )
        if ymap_symbol is None or ytyp_symbol is None:
            self.skipTest("Model constructors not available")

        ymap_type = ymap_symbol.value
        ytyp_type = ytyp_symbol.value
        if not isinstance(ymap_type, type) or not isinstance(ytyp_type, type):
            self.skipTest("Model constructors are not exposed as classes")

        ymap = ymap_type(name="unit_test.ymap")
        ytyp = ytyp_type(name="unit_test.ytyp")
        ymap.resource_name = "folder/unit_test.ymap"
        ytyp.resource_name = "folder/unit_test.ytyp"

        self.assertEqual(getattr(ymap, "meta_name", ""), "folder/unit_test.ymap")
        self.assertEqual(getattr(ytyp, "meta_name", ""), "folder/unit_test.ytyp")
        self.assertEqual(getattr(ymap, "resource_name", ""), "folder/unit_test.ymap")
        self.assertEqual(getattr(ytyp, "resource_name", ""), "folder/unit_test.ytyp")

    def test_declarative_aliases_are_exposed(self) -> None:
        entity_symbol = resolve_symbol(["fivefury.ymap", "fivefury"], ["Entity"])
        archetype_symbol = resolve_symbol(["fivefury.ytyp", "fivefury"], ["Archetype"])
        room_symbol = resolve_symbol(["fivefury.ytyp", "fivefury"], ["Room"])
        grass_batch_symbol = resolve_symbol(["fivefury.ymap.surfaces", "fivefury"], ["GrassBatch"])
        instanced_data_symbol = resolve_symbol(["fivefury.ymap.surfaces", "fivefury"], ["InstancedData"])
        lod_lights_symbol = resolve_symbol(["fivefury.ymap.surfaces", "fivefury"], ["LodLights"])
        if None in (
            entity_symbol,
            archetype_symbol,
            room_symbol,
            grass_batch_symbol,
            instanced_data_symbol,
            lod_lights_symbol,
        ):
            self.skipTest("Declarative aliases are not fully exposed")

        entity = entity_symbol.value(archetype_name="prop_tree_pine_01", guid=7, lod_dist=25.0)
        archetype = archetype_symbol.value(name="prop_tree_pine_01", lod_dist=60.0)
        room = room_symbol.value(name="room_01")
        grass_batch = grass_batch_symbol.value(archetype_name="prop_bush_lrg_04", lod_dist=80)
        instanced_data = instanced_data_symbol.value(grass_instance_list=[grass_batch])
        lod_lights = lod_lights_symbol.value(direction=[], falloff=[])

        self.assertEqual(getattr(entity, "archetype_name", None), "prop_tree_pine_01")
        self.assertEqual(getattr(archetype, "name", None), "prop_tree_pine_01")
        self.assertEqual(getattr(archetype, "asset_name", None), "prop_tree_pine_01")
        self.assertEqual(getattr(room, "name", None), "room_01")
        self.assertEqual(len(getattr(instanced_data, "grass_instance_list", [])), 1)
        self.assertEqual(getattr(lod_lights, "direction", None), [])

    def test_ymap_high_level_surfaces_roundtrip_if_available(self) -> None:
        ymap = _make_ymap("unit_test.ymap")
        if ymap is None:
            self.skipTest("Ymap API not available")

        entity = _make_entity("prop_tree_pine_01", position=(1.0, 2.0, 3.0), lod_dist=25.0)
        if entity is None:
            self.skipTest("Entity constructor not available")
        ymap.add_entity(entity)

        ymap.box_occluders = [
            _try_surface_constructor(
                ["fivefury.ymap", "fivefury"],
                ["BoxOccluder", "YmapBoxOccluder"],
                {
                    "iCenterX": 0,
                    "iCenterY": 0,
                    "iCenterZ": 0,
                    "iCosZ": 0,
                    "iLength": 0,
                    "iWidth": 0,
                    "iHeight": 0,
                    "iSinZ": 0,
                },
                _raw_box_occluder(),
            )
        ]
        ymap.occlude_models = [
            _try_surface_constructor(
                ["fivefury.ymap", "fivefury"],
                ["OccludeModel", "YmapOccludeModel"],
                {
                    "bmin": (0.0, 0.0, 0.0),
                    "bmax": (0.0, 0.0, 0.0),
                    "dataSize": 0,
                    "verts": b"",
                    "numVertsInBytes": 0,
                    "numTris": 0,
                    "flags": 0,
                },
                _raw_occlude_model(),
            )
        ]
        ymap.lod_lights = _try_surface_constructor(
            ["fivefury.ymap", "fivefury"],
            ["LodLights", "LodLightsSoa", "YmapLODLight"],
            {
                "direction": [(0.0, 0.0, -1.0)],
                "falloff": [1.0],
                "falloffExponent": [1.0],
                "timeAndStateFlags": [0],
                "hash": [0],
                "coneInnerAngle": [0],
                "coneOuterAngleOrCapExt": [0],
                "coronaIntensity": [0],
            },
            _raw_lod_light(),
        )
        ymap.distant_lod_lights = _try_surface_constructor(
            ["fivefury.ymap", "fivefury"],
            ["DistantLodLights", "DistantLodLightsSoa", "YmapDistantLODLight"],
            {
                "position": [(1.0, 2.0, 3.0)],
                "RGBI": [0],
                "numStreetLights": 0,
                "category": 0,
            },
            _raw_distant_lod_light(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "surfaces.ymap"
            saved = ymap.save(output, auto_extents=True)
            if isinstance(saved, (str, os.PathLike)):
                output = Path(saved)
            self.assertTrue(output.exists(), "YMAP with surfaces was not saved")

            parsed = type(ymap).from_bytes(output.read_bytes())
            self.assertEqual(len(parsed.box_occluders), 1)
            self.assertEqual(len(parsed.occlude_models), 1)
            self.assertIsNotNone(parsed.lod_lights)
            self.assertIsNotNone(parsed.distant_lod_lights)

    def test_ymap_grass_and_extensions_roundtrip(self) -> None:
        from fivefury import Aabb, Entity, GrassBatch, GrassInstance, ParticleEffectExtension, Ymap

        ymap = Ymap(name="typed_surfaces.ymap")
        entity = Entity(archetype_name="prop_tree_pine_01", position=(10.0, 20.0, 30.0), lod_dist=45.0)
        entity.add_extension(
            ParticleEffectExtension(
                name="fx_smoke",
                offset_position=(1.0, 2.0, 3.0),
                offset_rotation=(0.0, 0.0, 0.0, 1.0),
                fx_name="scr_wheel_burnout",
                fx_type=2,
                bone_tag=0,
                scale=1.25,
                probability=75,
                flags=3,
                color=0x11223344,
            )
        )
        ymap.add_entity(entity)

        batch = GrassBatch(
            batch_aabb=Aabb(minimum=(0.0, 0.0, 0.0), maximum=(20.0, 20.0, 10.0)),
            scale_range=(0.8, 1.0, 1.2),
            archetype_name="prop_grass_01",
            lod_dist=80,
            lod_fade_start_dist=40.0,
            lod_inst_fade_range=15.0,
            orient_to_terrain=1.0,
        )
        batch.add_instance(
            GrassInstance(
                position=(5.0, 6.0, 2.0),
                normal=(0.0, 0.0, 1.0),
                color=(10, 20, 30),
                scale=120,
                ao=90,
            )
        )
        ymap.add_grass_batch(batch)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "typed_surfaces.ymap"
            ymap.save(output, auto_extents=True)
            parsed = type(ymap).from_bytes(output.read_bytes())

        self.assertNotEqual(parsed.content_flags, 0)
        self.assertEqual(len(parsed.entities), 1)
        parsed_entity = parsed.entities[0]
        self.assertEqual(len(parsed_entity.extensions), 1)
        particle = parsed_entity.extensions[0]
        self.assertEqual(getattr(particle, "fx_name", None), "scr_wheel_burnout")
        self.assertEqual(getattr(particle, "fx_type", None), 2)
        self.assertAlmostEqual(getattr(particle, "scale", 0.0), 1.25, places=3)

        self.assertIsNotNone(parsed.instanced_data)
        self.assertEqual(len(parsed.instanced_data.grass_instance_list), 1)
        parsed_batch = parsed.instanced_data.grass_instance_list[0]
        self.assertEqual(len(parsed_batch.instances), 1)
        parsed_instance = parsed_batch.instances[0]
        self.assertAlmostEqual(parsed_instance.position[0], 5.0, places=2)
        self.assertAlmostEqual(parsed_instance.position[1], 6.0, places=2)
        self.assertAlmostEqual(parsed_instance.position[2], 2.0, places=2)
        self.assertEqual(parsed_instance.color, (10, 20, 30))
        self.assertEqual(parsed_instance.scale, 120)
        self.assertEqual(parsed_instance.ao, 90)

    def test_ytyp_archetype_extensions_roundtrip(self) -> None:
        from fivefury import Archetype, ParticleEffectExtension, Ytyp

        ytyp = Ytyp(name="typed_archetypes.ytyp")
        archetype = Archetype(
            name="prop_test_arch",
            lod_dist=120.0,
            asset_type=0,
            bb_min=(-1.0, -1.0, -1.0),
            bb_max=(1.0, 1.0, 1.0),
            bs_centre=(0.0, 0.0, 0.0),
            bs_radius=2.0,
        )
        archetype.add_extension(
            ParticleEffectExtension(
                name="fx_arch",
                offset_position=(0.5, 0.0, 0.0),
                offset_rotation=(0.0, 0.0, 0.0, 1.0),
                fx_name="scr_rcbarry2_sparks",
                fx_type=7,
                scale=0.75,
                probability=55,
                flags=1,
                color=0x55667788,
            )
        )
        ytyp.add_archetype(archetype)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "typed_archetypes.ytyp"
            ytyp.save(output)
            parsed = type(ytyp).from_bytes(output.read_bytes())

        self.assertEqual(len(parsed.archetypes), 1)
        parsed_archetype = parsed.archetypes[0]
        self.assertEqual(len(parsed_archetype.extensions), 1)
        particle = parsed_archetype.extensions[0]
        self.assertEqual(getattr(particle, "fx_name", None), "scr_rcbarry2_sparks")
        self.assertEqual(getattr(particle, "fx_type", None), 7)
        self.assertAlmostEqual(getattr(particle, "scale", 0.0), 0.75, places=3)

    def test_rpf_archive_accepts_high_level_asset_objects_if_available(self) -> None:
        rpf_symbol = resolve_symbol(
            ["fivefury.rpf", "fivefury.gta5.rpf", "fivefury"],
            ["RpfArchive", "create_rpf"],
        )
        ymap_symbol = resolve_symbol(
            ["fivefury.ymap", "fivefury"],
            ["Ymap"],
        )
        ytyp_symbol = resolve_symbol(
            ["fivefury.ytyp", "fivefury"],
            ["Ytyp"],
        )
        if rpf_symbol is None:
            self.skipTest("RpfArchive API not available")

        rpf_cls = rpf_symbol.value if isinstance(rpf_symbol.value, type) else None
        if rpf_cls is None:
            self.skipTest("No RpfArchive class available")

        ymap = ymap_symbol.value(name="unit_test.ymap") if ymap_symbol and isinstance(ymap_symbol.value, type) else None
        ytyp = ytyp_symbol.value(name="unit_test.ytyp") if ytyp_symbol and isinstance(ytyp_symbol.value, type) else None
        if ymap is None and ytyp is None:
            self.skipTest("No high-level YMAP/YTYP objects were available")

        archive = rpf_cls.empty("unit_test.rpf") if hasattr(rpf_cls, "empty") else rpf_cls()

        add_helper = None
        for method_name in ("add_game_file", "add_asset", "add", "add_ymap", "add_ytyp"):
            method = getattr(archive, method_name, None)
            if callable(method):
                add_helper = method
                break
        if add_helper is None:
            self.skipTest("No archive add helper is implemented yet")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            if ymap is not None:
                try:
                    result = add_helper("maps/unit_test.ymap", ymap)
                except TypeError as exc:
                    self.skipTest(f"Archive helper does not accept Ymap objects yet: {exc}")
                self.assertIsNotNone(result)
            if ytyp is not None:
                try:
                    result = add_helper("models/unit_test.ytyp", ytyp)
                except TypeError as exc:
                    self.skipTest(f"Archive helper does not accept Ytyp objects yet: {exc}")
                self.assertIsNotNone(result)
            output = root / "unit_test.rpf"
            archive.save(output)
            self.assertTrue(output.exists(), "archive save did not write a file")

    def test_minimal_rsc7_meta_roundtrip(self) -> None:
        meta_symbol = resolve_symbol(
            ["fivefury.meta", "fivefury.gta5.meta", "fivefury"],
            ["Meta", "meta"],
        )
        build_symbol = resolve_symbol(
            ["fivefury.resource", "fivefury.gta5.resource", "fivefury.rsc7", "fivefury"],
            ["build_rsc7", "Build", "build_resource", "build", "ResourceBuilder"],
        )
        parse_symbol = resolve_symbol(
            ["fivefury.resource", "fivefury.gta5.resource", "fivefury.rsc7", "fivefury"],
            ["read_rsc7", "parse_rsc7", "load_rsc7", "open_rsc7", "read_resource", "ResourceBuilder"],
        )
        if meta_symbol is None or build_symbol is None:
            self.skipTest("META/RSC7 API not implemented yet")

        meta_cls = meta_symbol.value
        meta = meta_cls()

        for attr_name in ("Name", "name"):
            if hasattr(meta, attr_name):
                setattr(meta, attr_name, "unit_test.ymap")
                break

        try:
            payload = _static_or_function(build_symbol, ["Build", "build", "build_resource"], meta)
        except TypeError:
            payload = _static_or_function(build_symbol, ["Build", "build", "build_resource"], meta, 0)

        self.assertIsInstance(payload, (bytes, bytearray))
        self.assertGreaterEqual(len(payload), 16)
        self.assertEqual(bytes(payload[:4]), b"RSC7")

        if parse_symbol is not None:
            try:
                parsed = _static_or_function(parse_symbol, ["Read", "read", "parse_rsc7", "load_rsc7"], payload)
            except TypeError:
                parsed = _static_or_function(parse_symbol, ["Read", "read", "parse_rsc7", "load_rsc7"], payload, 0)

            self.assertIsNotNone(parsed)
            for attr_name in ("Name", "name"):
                if hasattr(parsed, attr_name):
                    self.assertEqual(getattr(parsed, attr_name), "unit_test.ymap")
                    break

    def test_rpf_zip_roundtrip_nested_rpf(self) -> None:
        zip_to_rpf = resolve_symbol(
            ["fivefury.rpf", "fivefury.gta5.rpf", "fivefury"],
            ["zip_to_rpf", "zip2rpf", "create_rpf_from_zip", "RpfFile"],
        )
        rpf_to_zip = resolve_symbol(
            ["fivefury.rpf", "fivefury.gta5.rpf", "fivefury"],
            ["rpf_to_zip", "rpf2zip", "extract_rpf_to_zip", "RpfFile"],
        )
        if zip_to_rpf is None or rpf_to_zip is None:
            self.skipTest("RPF<->ZIP API not implemented yet")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            archive = root / "out.rpf"
            roundtrip = root / "roundtrip.zip"

            write_bytes(source / "content.txt", b"hello world")
            write_bytes(source / "nested.rpf" / "inner.bin", b"\x01\x02\x03")
            touch(source / "nested.rpf" / "deeper.rpf" / "note.txt", "nested")

            try:
                zip_payload = root / "source.zip"
                with zipfile.ZipFile(zip_payload, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for file_path in source.rglob("*"):
                        if file_path.is_file():
                            zf.write(file_path, file_path.relative_to(source).as_posix())

                produced = _static_or_function(zip_to_rpf, ["zip_to_rpf", "zip2rpf", "create_rpf_from_zip"], zip_payload, archive)
            except TypeError:
                produced = _static_or_function(zip_to_rpf, ["zip_to_rpf", "zip2rpf", "create_rpf_from_zip"], source, archive)

            if isinstance(produced, (str, os.PathLike)):
                archive = Path(produced)
            elif isinstance(produced, (bytes, bytearray)):
                archive.write_bytes(produced)

            self.assertTrue(archive.exists(), "RPF output was not created")

            try:
                result = _static_or_function(rpf_to_zip, ["rpf_to_zip", "rpf2zip", "extract_rpf_to_zip"], archive, roundtrip)
            except TypeError:
                result = _static_or_function(rpf_to_zip, ["rpf_to_zip", "rpf2zip", "extract_rpf_to_zip"], archive)

            if isinstance(result, (str, os.PathLike)):
                roundtrip = Path(result)
            elif isinstance(result, (bytes, bytearray)):
                roundtrip.write_bytes(result)

            self.assertTrue(roundtrip.exists(), "ZIP output was not created")

    def test_zip_to_rpf_accepts_directory_source(self) -> None:
        zip_to_rpf = resolve_symbol(
            ["fivefury.rpf", "fivefury.gta5.rpf", "fivefury"],
            ["zip_to_rpf", "zip2rpf", "create_rpf_from_zip", "RpfFile"],
        )
        rpf_to_zip = resolve_symbol(
            ["fivefury.rpf", "fivefury.gta5.rpf", "fivefury"],
            ["rpf_to_zip", "rpf2zip", "extract_rpf_to_zip", "RpfFile"],
        )
        if zip_to_rpf is None or rpf_to_zip is None:
            self.skipTest("RPF<->ZIP API not implemented yet")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "src"
            archive = root / "dir_source.rpf"
            roundtrip = root / "dir_source.zip"

            touch(source / "levels" / "pkg.rpf" / "nested.txt", "nested from dir")
            write_bytes(source / "levels" / "pkg.rpf" / "data.bin", b"\x10\x20\x30")
            touch(source / "levels" / "readme.txt", "hello")

            produced = _static_or_function(
                zip_to_rpf,
                ["zip_to_rpf", "zip2rpf", "create_rpf_from_zip"],
                source,
                archive,
            )

            if isinstance(produced, (str, os.PathLike)):
                archive = Path(produced)
            elif isinstance(produced, (bytes, bytearray)):
                archive.write_bytes(produced)

            self.assertTrue(archive.exists(), "RPF output from directory was not created")

            result = _static_or_function(
                rpf_to_zip,
                ["rpf_to_zip", "rpf2zip", "extract_rpf_to_zip"],
                archive,
                roundtrip,
            )

            if isinstance(result, (str, os.PathLike)):
                roundtrip = Path(result)
            elif isinstance(result, (bytes, bytearray)):
                roundtrip.write_bytes(result)

            self.assertTrue(roundtrip.exists(), "ZIP output from directory source was not created")
            with zipfile.ZipFile(roundtrip, "r") as zf:
                names = set(zf.namelist())
                self.assertIn("levels/readme.txt", names)
                self.assertIn("levels/pkg.rpf/nested.txt", names)
                self.assertIn("levels/pkg.rpf/data.bin", names)

    def test_gamefilecache_basic_indexing(self) -> None:
        cache_symbol = resolve_symbol(
            ["fivefury.cache", "fivefury.gta5.cache", "fivefury"],
            ["GameFileCache", "game_file_cache"],
        )
        if cache_symbol is None:
            self.skipTest("GameFileCache API not implemented yet")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_bytes(root / "maps" / "example.ytyp", b"dummy")
            write_bytes(root / "maps" / "example.ymap", b"dummy")
            write_bytes(root / "nested.rpf" / "inner.ymap", b"dummy")

            cache_cls = cache_symbol.value
            try:
                cache = cache_cls(root)
            except TypeError:
                cache = cache_cls()
                for method_name in ("set_root", "set_root_path", "attach_root"):
                    method = getattr(cache, method_name, None)
                    if callable(method):
                        method(root)
                        break

            indexed = False
            for method_name in ("scan", "build", "index", "refresh", "load"):
                method = getattr(cache, method_name, None)
                if callable(method):
                    try:
                        method(root)
                    except TypeError:
                        method()
                    indexed = True
                    break

            self.assertTrue(indexed, "No cache indexing method was available")

            found = None
            for method_name in ("get", "find", "get_file", "get_entry", "lookup"):
                method = getattr(cache, method_name, None)
                if callable(method):
                    try:
                        found = method("maps/example.ytyp")
                    except TypeError:
                        found = method(root / "maps" / "example.ytyp")
                    break
            self.assertIsNotNone(found, "Cache did not resolve a known file path")

    def test_gamefilecache_exposes_type_dicts_by_short_name_hash(self) -> None:
        from fivefury import GameFileCache, create_rpf, jenk_hash

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("assets.rpf")
            archive.add("stream/alpha.ydr", b"alpha")
            archive.add("stream/bravo.ytd", b"bravo")
            archive.add("stream/collision.ybn", b"collision")
            archive.add("stream/pack.ydd", b"pack")
            archive.save(root / "assets.rpf")

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            ydr_dict = cache.YdrDict
            self.assertEqual(ydr_dict[jenk_hash("alpha")].path, "assets.rpf/stream/alpha.ydr")
            self.assertEqual(cache.YtdDict[jenk_hash("bravo")].path, "assets.rpf/stream/bravo.ytd")
            self.assertEqual(cache.YbnDict[jenk_hash("collision")].path, "assets.rpf/stream/collision.ybn")
            self.assertEqual(cache.get_kind_dict(".ydd")[jenk_hash("pack")].path, "assets.rpf/stream/pack.ydd")
            self.assertTrue(cache.kind_dict(".ydr") is cache.YdrDict)
            self.assertEqual(len(cache.YdrDict), 1)

            write_bytes(root / "maps" / "delta.ydr", b"delta")
            cache.scan(use_index_cache=False)

            self.assertIn(jenk_hash("delta"), ydr_dict)
            self.assertEqual(ydr_dict[jenk_hash("delta")].path, "maps/delta.ydr")
            self.assertEqual(ydr_dict[jenk_hash("alpha")].path, "assets.rpf/stream/alpha.ydr")

    def test_gamefilecache_supports_simple_file_by_file_iteration_helpers(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("assets.rpf")
            archive.add("stream/alpha.ydr", b"alpha")
            archive.add("stream/bravo.ytd", b"bravo")
            archive.save(root / "assets.rpf")
            write_bytes(root / "maps" / "charlie.ymap", b"charlie")

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            self.assertEqual(len(cache), 3)
            self.assertEqual(
                [asset.path for asset in cache],
                [
                    "assets.rpf/stream/alpha.ydr",
                    "assets.rpf/stream/bravo.ytd",
                    "maps/charlie.ymap",
                ],
            )
            self.assertEqual(
                [asset.path for asset in cache.iter_kind(".ydr")],
                ["assets.rpf/stream/alpha.ydr"],
            )
            self.assertEqual(
                [asset.path for asset in cache.list_kind(".ytd")],
                ["assets.rpf/stream/bravo.ytd"],
            )
            self.assertEqual(cache.list_kind_paths(".ymap"), ["maps/charlie.ymap"])

    def test_gamefilecache_builds_lazy_global_archetype_dict(self) -> None:
        from fivefury import Archetype, GameFileCache, Ytyp, jenk_hash

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "types").mkdir(parents=True, exist_ok=True)
            ytyp = Ytyp(name="example_types")
            ytyp.add_archetype(Archetype(name="prop_tree_pine_01", lod_dist=100.0))
            ytyp.add_archetype(Archetype(name="prop_sign_road_01", lod_dist=50.0))
            ytyp.save(root / "types" / "example_types.ytyp")

            cache = GameFileCache(root, use_index_cache=False, max_loaded_files=0)
            cache.scan(use_index_cache=False)

            archetype_dict = cache.archetype_dict
            self.assertEqual(
                int(archetype_dict[jenk_hash("prop_tree_pine_01")].name),
                jenk_hash("prop_tree_pine_01"),
            )
            self.assertEqual(
                int(cache.ArchetypeDict[jenk_hash("prop_sign_road_01")].name),
                jenk_hash("prop_sign_road_01"),
            )
            self.assertEqual(
                int(cache.get_archetype("prop_tree_pine_01").name),
                jenk_hash("prop_tree_pine_01"),
            )
            self.assertTrue(cache.has_archetype("prop_sign_road_01"))
            self.assertEqual(
                sorted(int(archetype.name) for archetype in cache.iter_archetypes()),
                sorted([jenk_hash("prop_tree_pine_01"), jenk_hash("prop_sign_road_01")]),
            )

            extra = Ytyp(name="more_types")
            extra.add_archetype(Archetype(name="prop_bench_01", lod_dist=25.0))
            extra.save(root / "types" / "more_types.ytyp")
            cache.scan(use_index_cache=False)

            self.assertIn(jenk_hash("prop_bench_01"), archetype_dict)
            self.assertEqual(
                int(cache.find_archetype("prop_bench_01").name),
                jenk_hash("prop_bench_01"),
            )

    def test_gamefilecache_exposes_kind_counts_and_stats(self) -> None:
        from fivefury import GameFileCache, GameFileType, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("assets.rpf")
            archive.add("stream/alpha.ydr", b"alpha")
            archive.add("stream/bravo.ytd", b"bravo")
            archive.save(root / "assets.rpf")
            write_bytes(root / "maps" / "charlie.ymap", b"charlie")

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            counts = cache.kind_counts
            self.assertEqual(counts[GameFileType.YDR], 1)
            self.assertEqual(counts[".ytd"], 1)
            self.assertEqual(counts["ymap"], 1)
            self.assertEqual(cache.stats_by_kind(), {"YDR": 1, "YMAP": 1, "YTD": 1})
            self.assertEqual(cache.summary()["kind_counts"], {"YDR": 1, "YMAP": 1, "YTD": 1})

            write_bytes(root / "maps" / "delta.ymap", b"delta")
            cache.scan(use_index_cache=False)

            self.assertEqual(counts[GameFileType.YMAP], 2)
            self.assertEqual(cache.stats_by_kind()["YMAP"], 2)

    def test_gamefilecache_can_extract_assets_referenced_by_a_ymap(self) -> None:
        from fivefury import Archetype, Entity, GameFileCache, Ymap, Ytyp

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "maps").mkdir(parents=True, exist_ok=True)
            (root / "types").mkdir(parents=True, exist_ok=True)
            ymap = Ymap(name="example_map")
            ymap.add_entity(Entity(archetype_name="prop_tree_pine_01", guid=1))
            ymap.recalculate_extents()
            ymap.recalculate_flags()
            ymap.save(root / "maps" / "example_map.ymap")

            ytyp = Ytyp(name="example_types")
            ytyp.add_archetype(
                Archetype(
                    name="prop_tree_pine_01",
                    asset_name="prop_tree_pine_01",
                    asset_type=2,
                    texture_dictionary="prop_tree_pine_01",
                    physics_dictionary="prop_tree_pine_01",
                )
            )
            ytyp.save(root / "types" / "example_types.ytyp")

            write_bytes(root / "assets" / "prop_tree_pine_01.ydr", b"ydr")
            write_bytes(root / "assets" / "prop_tree_pine_01.ytd", b"ytd")
            write_bytes(root / "assets" / "prop_tree_pine_01.ybn", b"ybn")

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            assets = cache.list_ymap_entity_assets("example_map", include_supporting=True)
            self.assertEqual(
                sorted(asset.path for asset in assets),
                sorted(
                    [
                        "assets/prop_tree_pine_01.ybn",
                        "assets/prop_tree_pine_01.ydr",
                        "assets/prop_tree_pine_01.ytd",
                    ]
                ),
            )

            primary_only = cache.list_ymap_entity_assets("example_map", include_supporting=False)
            self.assertEqual([asset.path for asset in primary_only], ["assets/prop_tree_pine_01.ydr"])

            extracted = cache.extract_ymap_assets("example_map", root / "out")
            self.assertEqual(
                sorted(path.name for path in extracted),
                ["prop_tree_pine_01.ybn", "prop_tree_pine_01.ydr", "prop_tree_pine_01.ytd"],
            )
            self.assertEqual((root / "out" / "prop_tree_pine_01.ydr").read_bytes(), b"ydr")

    def test_gamefilecache_can_resolve_assets_from_an_external_loose_ymap(self) -> None:
        from fivefury import Archetype, Entity, GameFileCache, Ymap, Ytyp

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            root = tmp / "cache_root"
            external = tmp / "external"
            (root / "types").mkdir(parents=True, exist_ok=True)
            external.mkdir(parents=True, exist_ok=True)

            ymap = Ymap(name="external_map")
            ymap.add_entity(Entity(archetype_name="prop_tree_pine_01", guid=1))
            ymap.recalculate_extents()
            ymap.recalculate_flags()
            external_ymap = external / "external_map.ymap"
            ymap.save(external_ymap)

            ytyp = Ytyp(name="example_types")
            ytyp.add_archetype(
                Archetype(
                    name="prop_tree_pine_01",
                    asset_name="prop_tree_pine_01",
                    asset_type=2,
                    texture_dictionary="prop_tree_pine_01",
                )
            )
            ytyp.save(root / "types" / "example_types.ytyp")

            write_bytes(root / "assets" / "prop_tree_pine_01.ydr", b"ydr")
            write_bytes(root / "assets" / "prop_tree_pine_01.ytd", b"ytd")

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            assets = cache.list_ymap_entity_assets(external_ymap)
            self.assertEqual(
                sorted(asset.path for asset in assets),
                ["assets/prop_tree_pine_01.ydr", "assets/prop_tree_pine_01.ytd"],
            )

    def test_gamefilecache_supports_name_hash_read_and_extract_workflows(self) -> None:
        from fivefury import GameFileCache, create_rpf, jenk_hash

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive_path = root / "assets.rpf"
            archive = create_rpf("assets.rpf")
            archive.add("stream/alpha.ydr", b"alpha-bytes")
            archive.add("stream/bravo.ytd", b"bravo-bytes")
            archive.save(archive_path)
            write_bytes(root / "maps" / "charlie.ymap", b"charlie-bytes")

            cache = GameFileCache(root)
            cache.scan()
            self.assertEqual(cache.scan_errors, {})

            by_path = cache.find_path("assets.rpf/stream/alpha.ydr")
            self.assertIsNotNone(by_path)
            self.assertEqual(by_path.path, "assets.rpf/stream/alpha.ydr")

            by_name = cache.find_name("alpha", kind=".ydr")
            self.assertEqual(len(by_name), 1)
            self.assertEqual(by_name[0].path, "assets.rpf/stream/alpha.ydr")

            by_hash = cache.find_hash(jenk_hash("alpha"), kind=".ydr")
            self.assertEqual(len(by_hash), 1)
            self.assertEqual(by_hash[0].path, "assets.rpf/stream/alpha.ydr")

            payload = cache.read_asset("assets.rpf/stream/alpha.ydr")
            self.assertEqual(payload, b"alpha-bytes")
            self.assertEqual(cache.read_bytes("alpha"), b"alpha-bytes")

            extracted = cache.extract_asset("alpha", root / "out")
            self.assertIsNotNone(extracted)
            self.assertEqual(Path(extracted).read_bytes(), b"alpha-bytes")

    def test_gamefilecache_extracts_resource_assets_as_stored_bytes_by_default(self) -> None:
        from fivefury import GameFileCache, create_rpf
        from fivefury.resource import RSC7_MAGIC, parse_rsc7

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive_path = root / "assets.rpf"
            archive = create_rpf("assets.rpf")
            archive.add("stream/example.ymap", b"payload-bytes")
            archive.save(archive_path)

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            extracted = cache.extract_asset("assets.rpf/stream/example.ymap", root / "out")
            self.assertIsNotNone(extracted)

            stored = Path(extracted).read_bytes()
            self.assertEqual(stored[:4], struct.pack("<I", RSC7_MAGIC))
            self.assertEqual(parse_rsc7(stored)[1], b"payload-bytes")

            logical = cache.extract_asset(
                "assets.rpf/stream/example.ymap",
                root / "logical.ymap",
                logical=True,
            )
            self.assertIsNotNone(logical)
            self.assertEqual(Path(logical).read_bytes(), b"payload-bytes")

    def test_gamefilecache_can_skip_audio_vehicle_and_ped_assets_during_scan(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            audio = create_rpf("audio_pack.rpf")
            audio.add("x64/audio/sfx/test.awc", b"audio")
            audio.save(root / "audio_pack.rpf")

            vehicles = create_rpf("vehicle_pack.rpf")
            vehicles.add("stream/vehicles.meta", b"vehicles")
            vehicles.save(root / "vehicle_pack.rpf")

            peds = create_rpf("ped_pack.rpf")
            peds.add("stream/peds.ymt", b"peds")
            peds.save(root / "ped_pack.rpf")

            write_bytes(root / "maps" / "example.ymap", b"map")

            cache = GameFileCache(root, load_audio=False, load_vehicles=False, load_peds=False)
            cache.scan(use_index_cache=False)

            self.assertEqual(cache.scan_errors, {})
            self.assertEqual(cache.asset_count, 1)
            self.assertEqual(cache.find_name("test.awc"), [])
            self.assertEqual(cache.find_name("vehicles.meta"), [])
            self.assertEqual(cache.find_name("peds.ymt"), [])
            self.assertIsNotNone(cache.find_path("maps/example.ymap"))

    def test_gamefilecache_skips_matching_sources_before_scanning_them(self) -> None:
        import fivefury.cache as cache_module
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "x64" / "audio").mkdir(parents=True, exist_ok=True)
            (root / "x64" / "levels" / "gta5").mkdir(parents=True, exist_ok=True)
            (root / "x64" / "models" / "cdimages").mkdir(parents=True, exist_ok=True)
            (root / "mods").mkdir(parents=True, exist_ok=True)

            audio = create_rpf("audio_rel.rpf")
            audio.add("sfx/test.awc", b"audio")
            audio.save(root / "x64" / "audio" / "audio_rel.rpf")

            vehicles = create_rpf("vehicles.rpf")
            vehicles.add("stream/vehicles.meta", b"vehicles")
            vehicles.save(root / "x64" / "levels" / "gta5" / "vehicles.rpf")

            peds = create_rpf("pedprops.rpf")
            peds.add("stream/peds.ymt", b"peds")
            peds.save(root / "x64" / "models" / "cdimages" / "pedprops.rpf")

            world = create_rpf("world.rpf")
            world.add("stream/keep.ydr", b"keep")
            world.save(root / "mods" / "world.rpf")

            original = cache_module._scan_archive_sources_batch

            baseline_calls: list[str] = []
            filtered_calls: list[str] = []

            def delayed_scan(sources, index, crypto, hash_lut, skip_mask=0, workers=0, verbose=False):
                target = filtered_calls if skip_mask else baseline_calls
                target.extend(str(source_prefix) for _, source_prefix in sources)
                time.sleep(0.03 * len(sources))
                return original(sources, index, crypto, hash_lut, skip_mask, workers, verbose)

            with patch.object(cache_module, "_scan_archive_sources_batch", side_effect=delayed_scan):
                baseline = GameFileCache(root, use_index_cache=False, scan_workers=1)
                baseline.scan(use_index_cache=False)

                filtered = GameFileCache(
                    root,
                    use_index_cache=False,
                    scan_workers=1,
                    load_audio=False,
                    load_vehicles=False,
                    load_peds=False,
                )
                filtered.scan(use_index_cache=False)

            self.assertEqual(set(baseline_calls), {
                "mods/world.rpf",
                "x64/audio/audio_rel.rpf",
                "x64/levels/gta5/vehicles.rpf",
                "x64/models/cdimages/pedprops.rpf",
            })
            self.assertEqual(filtered_calls, ["mods/world.rpf"])
            self.assertEqual(filtered.asset_count, 1)
            self.assertLess(filtered.last_scan.elapsed_seconds, baseline.last_scan.elapsed_seconds * 0.6)

    def test_gamefilecache_supports_dlc_level_and_excluded_folders(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "update").mkdir(parents=True, exist_ok=True)
            (root / "update" / "x64" / "dlcpacks" / "mpalpha").mkdir(parents=True, exist_ok=True)
            (root / "update" / "x64" / "dlcpacks" / "mpbeta").mkdir(parents=True, exist_ok=True)
            (root / "scratch").mkdir(parents=True, exist_ok=True)

            update_archive = create_rpf("update.rpf")
            update_archive.add(
                "common/data/dlclist.xml",
                (
                    b"<SMandatoryPacksData><Paths>"
                    b"<Item>dlcpacks:/mpalpha/</Item>"
                    b"<Item>dlcpacks:/mpbeta/</Item>"
                    b"</Paths></SMandatoryPacksData>"
                ),
            )
            update_archive.save(root / "update" / "update.rpf")

            alpha = create_rpf("dlc.rpf")
            alpha.add("x64/data/alpha.bin", b"alpha")
            alpha.save(root / "update" / "x64" / "dlcpacks" / "mpalpha" / "dlc.rpf")

            beta = create_rpf("dlc.rpf")
            beta.add("x64/data/beta.bin", b"beta")
            beta.save(root / "update" / "x64" / "dlcpacks" / "mpbeta" / "dlc.rpf")

            misc = create_rpf("misc.rpf")
            misc.add("scratch/hidden.bin", b"hidden")
            misc.save(root / "scratch" / "misc.rpf")

            cache = GameFileCache(root, dlc_level="mpalpha", exclude_folders="scratch")
            cache.scan()

            self.assertEqual(cache.dlc_names, ["mpalpha", "mpbeta"])
            self.assertEqual(cache.active_dlc_names, ["mpalpha"])
            self.assertEqual(cache.ignored_folders, ("scratch",))
            self.assertIsNotNone(cache.find_path("update/x64/dlcpacks/mpalpha/dlc.rpf/x64/data/alpha.bin"))
            self.assertIsNone(cache.find_path("update/x64/dlcpacks/mpbeta/dlc.rpf/x64/data/beta.bin"))
            self.assertIsNone(cache.find_path("scratch/misc.rpf/scratch/hidden.bin"))

            cache = GameFileCache(root)
            cache.use_dlc("mpalpha")
            cache.ignore_folders("scratch", "mods")
            self.assertEqual(cache.dlc_level, "mpalpha")
            self.assertEqual(cache.ignored_folders, ("scratch", "mods"))

    def test_gamefilecache_reuses_persistent_index_cache_and_reports_timings(self) -> None:
        import fivefury.cache as cache_module
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index_path = root / "scan.ffindex"

            for archive_index in range(16):
                archive = create_rpf(f"pack_{archive_index}.rpf")
                for file_index in range(96):
                    archive.add(
                        f"stream/item_{archive_index}_{file_index}.ydr",
                        f"payload-{archive_index}-{file_index}".encode("ascii"),
                    )
                archive.save(root / f"pack_{archive_index}.rpf")

            original = cache_module._scan_archive_sources_batch

            def delayed_scan(sources, index, crypto, hash_lut, skip_mask=0, workers=0, verbose=False):
                time.sleep(0.01 * len(sources))
                return original(sources, index, crypto, hash_lut, skip_mask, workers, verbose)

            first = GameFileCache(root, index_cache_path=index_path, scan_workers=1)
            with patch.object(cache_module, "_scan_archive_sources_batch", side_effect=delayed_scan):
                first.scan(use_index_cache=True)

            self.assertTrue(index_path.exists())
            self.assertIsNotNone(first.last_scan)
            self.assertFalse(first.last_scan.used_index_cache)
            self.assertTrue(first.last_scan.saved_index_cache)
            self.assertEqual(first.asset_count, 16 * 96)

            second = GameFileCache(root, index_cache_path=index_path, scan_workers=1)
            second.scan(use_index_cache=True)

            self.assertIsNotNone(second.last_scan)
            self.assertTrue(second.last_scan.used_index_cache)
            self.assertFalse(second.last_scan.saved_index_cache)
            self.assertEqual(second.asset_count, first.asset_count)
            self.assertEqual(
                second.read_bytes("pack_0.rpf/stream/item_0_0.ydr"),
                b"payload-0-0",
            )
            self.assertLess(second.last_scan.elapsed_seconds, first.last_scan.elapsed_seconds)

    def test_gamefilecache_parallel_scan_reduces_elapsed_time_for_many_archives(self) -> None:
        import fivefury.cache as cache_module
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for archive_index in range(12):
                archive = create_rpf(f"pack_{archive_index}.rpf")
                for file_index in range(24):
                    archive.add(
                        f"stream/item_{archive_index}_{file_index}.ydr",
                        f"payload-{archive_index}-{file_index}".encode("ascii"),
                    )
                archive.save(root / f"pack_{archive_index}.rpf")

            original = cache_module._scan_archive_sources_batch

            def delayed_scan(sources, index, crypto, hash_lut, skip_mask=0, workers=0, verbose=False):
                time.sleep((0.03 * len(sources)) / max(int(workers or 1), 1))
                return original(sources, index, crypto, hash_lut, skip_mask, workers, verbose)

            with patch.object(cache_module, "_scan_archive_sources_batch", side_effect=delayed_scan):
                serial = GameFileCache(root, scan_workers=1)
                serial.scan(use_index_cache=False)

                parallel = GameFileCache(root, scan_workers=4)
                parallel.scan(use_index_cache=False)

            self.assertEqual(serial.asset_count, 12 * 24)
            self.assertEqual(parallel.asset_count, serial.asset_count)
            self.assertEqual(serial.last_scan.archive_workers, 1)
            self.assertEqual(parallel.last_scan.archive_workers, 4)
            self.assertLess(parallel.last_scan.elapsed_seconds, serial.last_scan.elapsed_seconds * 0.8)

    def test_gamefilecache_scan_keeps_archive_handles_lazy_and_bounded(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for archive_index in range(4):
                archive = create_rpf(f"pack_{archive_index}.rpf")
                archive.add(f"stream/item_{archive_index}.ydr", f"payload-{archive_index}".encode("ascii"))
                archive.save(root / f"pack_{archive_index}.rpf")

            cache = GameFileCache(root, use_index_cache=False, max_open_archives=2, scan_workers=2)
            cache.scan(use_index_cache=False)

            self.assertEqual(cache.open_archive_count, 0)
            self.assertEqual(cache.archives, [])
            self.assertEqual(cache.entries, {})
            self.assertTrue(
                all(record.entry is None and record.archive is None for record in cache.records if record.archive_rel),
            )

            self.assertEqual(cache.read_bytes("pack_0.rpf/stream/item_0.ydr"), b"payload-0")
            self.assertEqual(cache.read_bytes("pack_1.rpf/stream/item_1.ydr"), b"payload-1")
            self.assertEqual(cache.read_bytes("pack_2.rpf/stream/item_2.ydr"), b"payload-2")
            self.assertLessEqual(cache.open_archive_count, 2)

    def test_gamefilecache_exposes_simple_scan_state(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.add("stream/a.ydr", b"a")
            archive.save(root / "pack.rpf")

            cache = GameFileCache(root, use_index_cache=False)
            self.assertFalse(cache.scan_complete)
            self.assertFalse(cache.scan_ok)
            self.assertFalse(cache.has_assets)
            self.assertFalse(cache.has_scan_errors)

            cache.scan(use_index_cache=False)
            summary = cache.summary()

            self.assertTrue(cache.scan_complete)
            self.assertTrue(cache.scan_ok)
            self.assertTrue(cache.has_assets)
            self.assertFalse(cache.has_scan_errors)
            self.assertEqual(summary["asset_count"], 1)
            self.assertTrue(summary["scan_complete"])
            self.assertTrue(summary["scan_ok"])
            self.assertFalse(summary["has_scan_errors"])
            self.assertEqual(summary["scan_error_count"], 0)

    def test_gamefilecache_verbose_prints_scan_and_read_activity(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.add("stream/a.ydr", b"a")
            archive.save(root / "pack.rpf")
            write_bytes(root / "maps" / "example.ymap", b"map")

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cache = GameFileCache(root, use_index_cache=False, verbose=True)
                cache.scan(use_index_cache=False)
                self.assertEqual(cache.read_bytes("pack.rpf/stream/a.ydr"), b"a")

            output = buffer.getvalue()
            self.assertIn("[GameFileCache] scan start", output)
            self.assertIn("[GameFileCache] scan archive pack.rpf", output)
            self.assertIn("[GameFileCache] scan asset pack.rpf/stream/a.ydr", output)
            self.assertIn("[GameFileCache] scan file maps/example.ymap", output)
            self.assertIn("[GameFileCache] scan done", output)
            self.assertIn("[GameFileCache] read bytes pack.rpf/stream/a.ydr logical=True", output)

    def test_gamefilecache_uses_native_index_backend(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.add("stream/a.ydr", b"a")
            archive.add("stream/b.ydr", b"b")
            archive.save(root / "pack.rpf")

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            self.assertTrue(hasattr(cache, "_index"))
            self.assertEqual(len(cache._index), 2)
            self.assertEqual(cache._index.get_path(0), "pack.rpf/stream/a.ydr")
            self.assertEqual(cache._index.get_path(1), "pack.rpf/stream/b.ydr")

    def test_gamefilecache_bounds_loaded_file_cache(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.add("stream/a.ydr", b"a")
            archive.add("stream/b.ydr", b"b")
            archive.add("stream/c.ydr", b"c")
            archive.save(root / "pack.rpf")

            cache = GameFileCache(root, use_index_cache=False, max_loaded_files=2)
            cache.scan(use_index_cache=False)

            self.assertIsNotNone(cache.get_file("pack.rpf/stream/a.ydr"))
            self.assertIsNotNone(cache.get_file("pack.rpf/stream/b.ydr"))
            self.assertEqual(cache.open_file_count, 2)
            self.assertIn("pack.rpf/stream/a.ydr", cache.files)
            self.assertIn("pack.rpf/stream/b.ydr", cache.files)

            self.assertIsNotNone(cache.get_file("pack.rpf/stream/c.ydr"))
            self.assertEqual(cache.open_file_count, 2)
            self.assertNotIn("pack.rpf/stream/a.ydr", cache.files)
            self.assertIn("pack.rpf/stream/b.ydr", cache.files)
            self.assertIn("pack.rpf/stream/c.ydr", cache.files)

    def test_gamefilecache_reads_archive_assets_without_opening_archives(self) -> None:
        from fivefury import GameFileCache, create_rpf
        from fivefury._native import read_rpf_entry_variants
        from fivefury.hashing import _get_lut

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.add("stream/sample.bin", b"hello native cache", compress_binary=True)
            archive.add("stream/test_dict.ytd", _build_test_ytd_bytes(enhanced=False))
            archive.save(root / "pack.rpf")

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            self.assertEqual(cache.open_archive_count, 0)
            stored_native, standalone_native = read_rpf_entry_variants(
                root / "pack.rpf",
                "stream/test_dict.ytd",
                _get_lut(),
            )
            self.assertTrue(stored_native)
            self.assertTrue(standalone_native.startswith(b"RSC7"))
            self.assertEqual(
                cache.read_bytes("pack.rpf/stream/sample.bin", logical=True),
                b"hello native cache",
            )
            self.assertEqual(cache.open_archive_count, 0)

            game_file = cache.get_file("pack.rpf/stream/test_dict.ytd")
            self.assertIsNotNone(game_file)
            self.assertEqual(type(game_file.parsed).__name__, "Ytd")
            self.assertEqual(cache.open_archive_count, 0)

            extracted = cache.extract_asset("pack.rpf/stream/test_dict.ytd", root / "out")
            self.assertIsNotNone(extracted)
            assert extracted is not None
            self.assertEqual(extracted.read_bytes()[:4], b"RSC7")
            self.assertEqual(cache.open_archive_count, 0)

    def test_ytd_reader_parses_legacy_and_enhanced_dictionaries(self) -> None:
        from fivefury import read_ytd

        legacy = read_ytd(_build_test_ytd_bytes(enhanced=False))
        enhanced = read_ytd(_build_test_ytd_bytes(enhanced=True))

        self.assertEqual(len(legacy.textures), 1)
        self.assertEqual(len(enhanced.textures), 1)
        self.assertEqual(legacy.textures[0].name, "test_diffuse")
        self.assertEqual(enhanced.textures[0].name, "test_diffuse")
        self.assertEqual(legacy.textures[0].width, 4)
        self.assertEqual(enhanced.textures[0].height, 4)
        self.assertEqual(legacy.textures[0].mip_count, 1)
        self.assertEqual(enhanced.textures[0].mip_count, 1)

    def test_ytd_reader_can_export_dds(self) -> None:
        from fivefury import read_ytd

        ytd = read_ytd(_build_test_ytd_bytes(enhanced=False))
        texture = ytd.textures[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test_diffuse.dds"
            texture.save_dds(output)
            self.assertTrue(output.exists())
            self.assertEqual(output.read_bytes()[:4], b"DDS ")

    def test_gamefilecache_parses_ytd_and_extracts_ytd_textures(self) -> None:
        from fivefury import GameFileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_bytes(root / "stream" / "test_dict.ytd", _build_test_ytd_bytes(enhanced=False))

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            game_file = cache.get_file("stream/test_dict.ytd")
            self.assertIsNotNone(game_file)
            self.assertEqual(type(game_file.parsed).__name__, "Ytd")
            self.assertEqual(len(cache.list_ytd_textures("test_dict")), 1)

            extracted = cache.extract_ytd_textures("test_dict", root / "out")
            self.assertEqual(len(extracted), 1)
            self.assertEqual(extracted[0].suffix.lower(), ".dds")
            self.assertEqual(extracted[0].read_bytes()[:4], b"DDS ")

    def test_gamefilecache_extracts_asset_textures_via_archetype_texture_dictionary(self) -> None:
        from fivefury import Archetype, GameFileCache, Ytyp

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_bytes(root / "stream" / "prop_tree_pine_01.ydr", b"RSC7fake")
            write_bytes(root / "stream" / "test_dict.ytd", _build_test_ytd_bytes(enhanced=False))

            ytyp = Ytyp(name="types.ytyp")
            ytyp.add_archetype(
                Archetype(
                    name="prop_tree_pine_01",
                    asset_name="prop_tree_pine_01",
                    texture_dictionary="test_dict",
                    asset_type=2,
                )
            )
            ytyp.save(root / "stream" / "types.ytyp")

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            extracted = cache.extract_asset_textures("prop_tree_pine_01.ydr", root / "textures_out")
            self.assertEqual(len(extracted), 1)
            self.assertEqual(extracted[0].name, "test_diffuse.dds")
            self.assertEqual(extracted[0].parent.name, "test_dict")
            self.assertEqual(extracted[0].read_bytes()[:4], b"DDS ")

    def test_gamefilecache_extracts_asset_textures_from_external_ymap_and_parent_txd_chain(self) -> None:
        from fivefury import Archetype, Entity, GameFileCache, Ymap, Ytyp

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "game"
            root.mkdir(parents=True, exist_ok=True)
            write_bytes(root / "stream" / "prop_tree_pine_01.ydr", b"RSC7fake")
            write_bytes(root / "stream" / "child_dict.ytd", _build_test_ytd_bytes(enhanced=False))
            write_bytes(root / "stream" / "parent_dict.ytd", _build_test_ytd_bytes(enhanced=True))
            write_bytes(
                root / "common" / "data" / "gtxd.meta",
                (
                    "<CMapParentTxds><txdRelationships>"
                    "<Item><parent>parent_dict</parent><child>child_dict</child></Item>"
                    "</txdRelationships></CMapParentTxds>"
                ).encode("utf-8"),
            )

            ytyp = Ytyp(name="types.ytyp")
            ytyp.add_archetype(
                Archetype(
                    name="prop_tree_pine_01",
                    asset_name="prop_tree_pine_01",
                    texture_dictionary="child_dict",
                    asset_type=2,
                )
            )
            ytyp.save(root / "stream" / "types.ytyp")

            external = Path(tmpdir) / "external"
            external.mkdir(parents=True, exist_ok=True)
            ymap = Ymap(name="external_map.ymap")
            ymap.add_entity(Entity(archetype_name="prop_tree_pine_01", position=(0.0, 0.0, 0.0), lod_dist=50.0))
            ymap.save(external / "external_map.ymap", auto_extents=True)

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            dictionaries = cache.list_texture_dictionaries(external / "external_map.ymap")
            self.assertEqual({asset.stem for asset in dictionaries}, {"child_dict", "parent_dict"})

            extracted = cache.extract_asset_textures(external / "external_map.ymap", root / "textures_out")
            self.assertEqual(len(extracted), 2)
            self.assertEqual({path.parent.name for path in extracted}, {"child_dict", "parent_dict"})
            self.assertTrue(all(path.read_bytes()[:4] == b"DDS " for path in extracted))

    def test_gamefilecache_extracts_embedded_textures_from_supported_resource_assets(self) -> None:
        from fivefury import GameFileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_bytes(root / "stream" / "embedded.ydr", _build_embedded_texture_resource("ydr", enhanced=False))
            write_bytes(root / "stream" / "embedded.ydd", _build_embedded_texture_resource("ydd", enhanced=False))
            write_bytes(root / "stream" / "embedded.yft", _build_embedded_texture_resource("yft", enhanced=False))
            write_bytes(root / "stream" / "embedded.ypt", _build_embedded_texture_resource("ypt", enhanced=False))
            write_bytes(root / "stream" / "embedded_gen9.ypt", _build_embedded_texture_resource("ypt", enhanced=True))

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            for relative_path in (
                "stream/embedded.ydr",
                "stream/embedded.ydd",
                "stream/embedded.yft",
                "stream/embedded.ypt",
                "stream/embedded_gen9.ypt",
            ):
                refs = cache.list_asset_textures(relative_path)
                self.assertEqual(len(refs), 1, relative_path)
                self.assertEqual(refs[0].origin, "embedded")
                extracted = cache.extract_asset_textures(relative_path, root / "textures_out" / Path(relative_path).stem)
                self.assertEqual(len(extracted), 1, relative_path)
                self.assertEqual(extracted[0].name, "test_diffuse.dds")
                self.assertEqual(extracted[0].read_bytes()[:4], b"DDS ")

    def test_gamefilecache_extracts_embedded_textures_from_external_ymap_primary_assets(self) -> None:
        from fivefury import Archetype, Entity, GameFileCache, Ymap, Ytyp

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "game"
            root.mkdir(parents=True, exist_ok=True)
            write_bytes(root / "stream" / "embedded_tree.ydr", _build_embedded_texture_resource("ydr", enhanced=False))

            ytyp = Ytyp(name="types.ytyp")
            ytyp.add_archetype(
                Archetype(
                    name="embedded_tree",
                    asset_name="embedded_tree",
                    asset_type=2,
                )
            )
            ytyp.save(root / "stream" / "types.ytyp")

            external = Path(tmpdir) / "external"
            external.mkdir(parents=True, exist_ok=True)
            ymap = Ymap(name="external_map.ymap")
            ymap.add_entity(Entity(archetype_name="embedded_tree", position=(0.0, 0.0, 0.0), lod_dist=50.0))
            ymap.save(external / "external_map.ymap", auto_extents=True)

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            refs = cache.list_asset_textures(external / "external_map.ymap")
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0].origin, "embedded")

            extracted = cache.extract_asset_textures(external / "external_map.ymap", root / "textures_out")
            self.assertEqual(len(extracted), 1)
            self.assertEqual(extracted[0].name, "test_diffuse.dds")
            self.assertEqual(extracted[0].read_bytes()[:4], b"DDS ")

    def test_open_resource_texture_asset_returns_typed_classes(self) -> None:
        from fivefury import YddAsset, YdrAsset, YftAsset, YptAsset, open_resource_texture_asset

        for kind, asset_type in (
            ("ydr", YdrAsset),
            ("ydd", YddAsset),
            ("yft", YftAsset),
            ("ypt", YptAsset),
        ):
            asset = open_resource_texture_asset(_build_embedded_texture_resource(kind, enhanced=False), kind=f".{kind}")
            self.assertIsNotNone(asset)
            self.assertTrue(isinstance(asset, asset_type))
            dictionaries = asset.list_embedded_texture_dictionaries()
            self.assertEqual(len(dictionaries), 1)
            self.assertEqual(dictionaries[0].ytd.textures[0].name, "test_diffuse")

    def test_gamefilecache_opens_typed_resource_texture_assets(self) -> None:
        from fivefury import GameFileCache, YftAsset

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_bytes(root / "stream" / "embedded.yft", _build_embedded_texture_resource("yft", enhanced=False))

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)

            asset = cache.get_resource_asset("stream/embedded.yft")
            self.assertIsNotNone(asset)
            self.assertTrue(isinstance(asset, YftAsset))
            dictionaries = asset.list_embedded_texture_dictionaries()
            self.assertEqual(len(dictionaries), 1)
            self.assertEqual(dictionaries[0].ytd.textures[0].name, "test_diffuse")

    def test_resource_asset_modules_export_individual_format_classes(self) -> None:
        from fivefury.assets.ydd import YddAsset
        from fivefury.assets.ydr import YdrAsset
        from fivefury.assets.yft import YftAsset
        from fivefury.assets.ypt import YptAsset

        self.assertEqual(YdrAsset.kind.name, "YDR")
        self.assertEqual(YddAsset.kind.name, "YDD")
        self.assertEqual(YftAsset.kind.name, "YFT")
        self.assertEqual(YptAsset.kind.name, "YPT")


if __name__ == "__main__":
    unittest.main()







