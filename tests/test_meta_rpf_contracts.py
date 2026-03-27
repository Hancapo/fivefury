from __future__ import annotations

import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fivefury.meta import RawStruct
from fivefury.meta_defs import meta_name
from tests.helpers import resolve_symbol, touch, write_bytes


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
        ["fivefury.ymap", "fivefury.gta5.ymap", "fivefury"],
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
        ["fivefury.ymap", "fivefury.gta5.ymap", "fivefury"],
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


class MetaAndArchiveContractTests(unittest.TestCase):
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
            ["fivefury.ytyp", "fivefury.gta5.ytyp", "fivefury"],
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
            ["fivefury.ytyp", "fivefury.gta5.ytyp", "fivefury"],
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
            ["fivefury.ymap", "fivefury.gta5.ymap", "fivefury"],
            ["Ymap"],
        )
        ytyp_symbol = resolve_symbol(
            ["fivefury.ytyp", "fivefury.gta5.ytyp", "fivefury"],
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
        grass_batch_symbol = resolve_symbol(["fivefury.ymap_surfaces", "fivefury"], ["GrassBatch"])
        instanced_data_symbol = resolve_symbol(["fivefury.ymap_surfaces", "fivefury"], ["InstancedData"])
        lod_lights_symbol = resolve_symbol(["fivefury.ymap_surfaces", "fivefury"], ["LodLights"])
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
                ["fivefury.ymap", "fivefury.gta5.ymap", "fivefury"],
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
                ["fivefury.ymap", "fivefury.gta5.ymap", "fivefury"],
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
            ["fivefury.ymap", "fivefury.gta5.ymap", "fivefury"],
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
            ["fivefury.ymap", "fivefury.gta5.ymap", "fivefury"],
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
            ["fivefury.ymap", "fivefury.gta5.ymap", "fivefury"],
            ["Ymap"],
        )
        ytyp_symbol = resolve_symbol(
            ["fivefury.ytyp", "fivefury.gta5.ytyp", "fivefury"],
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
            self.assertIsNotNone(cache.find_path("update/x64/dlcpacks/mpalpha/dlc.rpf/x64/data/alpha.bin"))
            self.assertIsNone(cache.find_path("update/x64/dlcpacks/mpbeta/dlc.rpf/x64/data/beta.bin"))
            self.assertIsNone(cache.find_path("scratch/misc.rpf/scratch/hidden.bin"))

    def test_gamefilecache_reuses_persistent_index_cache_and_reports_timings(self) -> None:
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

            first = GameFileCache(root, index_cache_path=index_path)
            first.scan(use_index_cache=True)

            self.assertTrue(index_path.exists())
            self.assertIsNotNone(first.last_scan)
            self.assertFalse(first.last_scan.used_index_cache)
            self.assertTrue(first.last_scan.saved_index_cache)
            self.assertEqual(first.asset_count, 16 * 96)

            second = GameFileCache(root, index_cache_path=index_path)
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

            original = cache_module._scan_archive_source

            def delayed_scan(*args, **kwargs):
                time.sleep(0.03)
                return original(*args, **kwargs)

            with patch.object(cache_module, "_scan_archive_source", side_effect=delayed_scan):
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


if __name__ == "__main__":
    unittest.main()

