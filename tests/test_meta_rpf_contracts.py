from __future__ import annotations

import io
import struct
import tempfile
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from fivefury import Quaternion, Vector3
from fivefury.rpf import rpf_to_zip, zip_to_rpf
from fivefury.ymap import Entity
from fivefury.ymap.surfaces import GrassBatch, InstancedData, LodLights
from fivefury.ytyp import Archetype, Room
from tests.helpers import configured_path, reference_root, touch, write_bytes

_DAT_VIRTUAL_BASE = 1342177280
_DAT_PHYSICAL_BASE = 1610612736
_GTAV_TEX_SIZE = 152
_ENHANCED_TEX_SIZE = 160


def _align(value: int, alignment: int) -> int:
    return value + alignment - 1 & ~(alignment - 1)


def _parse_meta_layout(data: bytes) -> dict[str, object]:
    from fivefury.resource import split_rsc7_sections

    header, system_data, _ = split_rsc7_sections(data)
    root = struct.unpack_from("<ihbbiiqqqqqhhhh8I", system_data, 16)
    pages_info = struct.unpack_from("<IIBBHI", system_data, 112)
    data_block_pointer = int(root[8])
    data_block_count = int(root[13])
    data_block_offset = (
        data_block_pointer - _DAT_VIRTUAL_BASE if data_block_pointer else 0
    )
    data_blocks: list[tuple[int, int, int]] = []
    for index in range(data_block_count):
        name_hash, length, pointer = struct.unpack_from(
            "<IIq", system_data, data_block_offset + index * 16
        )
        data_blocks.append((name_hash, length, pointer))
    return {
        "header": header,
        "pages_info": pages_info,
        "struct_ptr": int(root[6]),
        "enum_ptr": int(root[7]),
        "data_block_ptr": data_block_pointer,
        "data_block_count": data_block_count,
        "data_blocks": data_blocks,
    }


def _build_test_ytd_bytes(*, enhanced: bool = False) -> bytes:
    from fivefury.resource import build_rsc7
    from fivefury.texture import BC_TO_DX9, BC_TO_RSC8, BCFormat, row_pitch

    name = b"test_diffuse\x00"
    pixel_data = b'\x11"3DUfw\x88'
    count = 1
    dict_size = 64
    keys_offset = dict_size
    ptrs_offset = _align(keys_offset + 4 * count, 16)
    tex_size = _ENHANCED_TEX_SIZE if enhanced else _GTAV_TEX_SIZE
    textures_offset = _align(ptrs_offset + 8 * count, 16)
    name_offset = textures_offset + tex_size
    virtual_size = _align(name_offset + len(name), 16)
    vbuf = bytearray(virtual_size)
    pbuf = bytearray(pixel_data)
    vbuf[40:42] = count.to_bytes(2, "little")
    vbuf[48:56] = (_DAT_VIRTUAL_BASE + ptrs_offset).to_bytes(8, "little")
    vbuf[keys_offset : keys_offset + 4] = (305419896).to_bytes(4, "little")
    vbuf[ptrs_offset : ptrs_offset + 8] = (
        _DAT_VIRTUAL_BASE + textures_offset
    ).to_bytes(8, "little")
    vbuf[name_offset : name_offset + len(name)] = name
    tex_off = textures_offset
    vbuf[tex_off + 40 : tex_off + 48] = (_DAT_VIRTUAL_BASE + name_offset).to_bytes(
        8, "little"
    )
    if enhanced:
        vbuf[tex_off + 24 : tex_off + 26] = (4).to_bytes(2, "little")
        vbuf[tex_off + 26 : tex_off + 28] = (4).to_bytes(2, "little")
        vbuf[tex_off + 31] = int(BC_TO_RSC8[BCFormat.BC1])
        vbuf[tex_off + 34] = 1
        vbuf[tex_off + 56 : tex_off + 64] = _DAT_PHYSICAL_BASE.to_bytes(8, "little")
        version = 5
    else:
        vbuf[tex_off + 80 : tex_off + 82] = (4).to_bytes(2, "little", signed=True)
        vbuf[tex_off + 82 : tex_off + 84] = (4).to_bytes(2, "little", signed=True)
        vbuf[tex_off + 86 : tex_off + 88] = row_pitch(4, BCFormat.BC1).to_bytes(
            2, "little"
        )
        vbuf[tex_off + 88 : tex_off + 92] = int(BC_TO_DX9[BCFormat.BC1]).to_bytes(
            4, "little"
        )
        vbuf[tex_off + 93] = 1
        vbuf[tex_off + 112 : tex_off + 120] = _DAT_PHYSICAL_BASE.to_bytes(8, "little")
        version = 13
    return build_rsc7(bytes(vbuf), version=version, graphics_data=bytes(pbuf))


def _relocate_embedded_texture_dictionary(
    virtual_data: bytes, *, dict_offset: int, enhanced: bool
) -> bytes:
    count = int.from_bytes(virtual_data[40:42], "little")
    ptrs_offset = int.from_bytes(virtual_data[48:56], "little") - _DAT_VIRTUAL_BASE
    output = bytearray(dict_offset + len(virtual_data))
    output[dict_offset : dict_offset + len(virtual_data)] = virtual_data
    delta = dict_offset

    def add_virtual_ptr(offset: int) -> None:
        value = int.from_bytes(
            output[dict_offset + offset : dict_offset + offset + 8], "little"
        )
        if value:
            output[dict_offset + offset : dict_offset + offset + 8] = (
                value + delta
            ).to_bytes(8, "little")

    add_virtual_ptr(8)
    add_virtual_ptr(32)
    add_virtual_ptr(48)
    for index in range(count):
        ptr_pos = dict_offset + ptrs_offset + index * 8
        tex_ptr = int.from_bytes(output[ptr_pos : ptr_pos + 8], "little")
        output[ptr_pos : ptr_pos + 8] = (tex_ptr + delta).to_bytes(8, "little")
        tex_off = (
            int.from_bytes(
                virtual_data[ptrs_offset + index * 8 : ptrs_offset + index * 8 + 8],
                "little",
            )
            - _DAT_VIRTUAL_BASE
        )
        add_virtual_ptr(tex_off + 40)
        if enhanced:
            add_virtual_ptr(tex_off + 48)
    return bytes(output)


def _build_embedded_texture_resource(kind: str, *, enhanced: bool = False) -> bytes:
    from fivefury.resource import build_rsc7, split_rsc7_sections

    _, virtual_src, graphics_src = split_rsc7_sections(
        _build_test_ytd_bytes(enhanced=enhanced)
    )
    kind_lower = kind.lower()
    if kind_lower == "ydr":
        shader_group_offset = 256
        dict_offset = 512
        system_size = dict_offset + len(virtual_src)
        system_data = bytearray(system_size)
        system_data[16:24] = (_DAT_VIRTUAL_BASE + shader_group_offset).to_bytes(
            8, "little"
        )
        system_data[shader_group_offset + 8 : shader_group_offset + 16] = (
            _DAT_VIRTUAL_BASE + dict_offset
        ).to_bytes(8, "little")
        system_data[dict_offset:] = _relocate_embedded_texture_dictionary(
            virtual_src, dict_offset=dict_offset, enhanced=enhanced
        )[dict_offset:]
        version = 159 if enhanced else 165
    elif kind_lower == "ydd":
        drawables_offset = 256
        drawable_offset = 288
        shader_group_offset = 512
        dict_offset = 640
        system_size = dict_offset + len(virtual_src)
        system_data = bytearray(system_size)
        system_data[48:56] = (_DAT_VIRTUAL_BASE + drawables_offset).to_bytes(
            8, "little"
        )
        system_data[56:58] = (1).to_bytes(2, "little")
        system_data[drawables_offset : drawables_offset + 8] = (
            _DAT_VIRTUAL_BASE + drawable_offset
        ).to_bytes(8, "little")
        system_data[drawable_offset + 16 : drawable_offset + 24] = (
            _DAT_VIRTUAL_BASE + shader_group_offset
        ).to_bytes(8, "little")
        system_data[shader_group_offset + 8 : shader_group_offset + 16] = (
            _DAT_VIRTUAL_BASE + dict_offset
        ).to_bytes(8, "little")
        system_data[dict_offset:] = _relocate_embedded_texture_dictionary(
            virtual_src, dict_offset=dict_offset, enhanced=enhanced
        )[dict_offset:]
        version = 159 if enhanced else 165
    elif kind_lower == "yft":
        drawable_offset = 288
        shader_group_offset = 512
        dict_offset = 640
        system_size = dict_offset + len(virtual_src)
        system_data = bytearray(system_size)
        system_data[48:56] = (_DAT_VIRTUAL_BASE + drawable_offset).to_bytes(8, "little")
        system_data[drawable_offset + 16 : drawable_offset + 24] = (
            _DAT_VIRTUAL_BASE + shader_group_offset
        ).to_bytes(8, "little")
        system_data[shader_group_offset + 8 : shader_group_offset + 16] = (
            _DAT_VIRTUAL_BASE + dict_offset
        ).to_bytes(8, "little")
        system_data[dict_offset:] = _relocate_embedded_texture_dictionary(
            virtual_src, dict_offset=dict_offset, enhanced=enhanced
        )[dict_offset:]
        version = 171 if enhanced else 162
    elif kind_lower == "ypt":
        dict_offset = 256
        system_size = dict_offset + len(virtual_src)
        system_data = bytearray(system_size)
        system_data[32:40] = (_DAT_VIRTUAL_BASE + dict_offset).to_bytes(8, "little")
        system_data[dict_offset:] = _relocate_embedded_texture_dictionary(
            virtual_src, dict_offset=dict_offset, enhanced=enhanced
        )[dict_offset:]
        version = 71 if enhanced else 68
    else:
        raise ValueError(f"Unsupported embedded texture resource kind: {kind}")
    return build_rsc7(
        bytes(system_data), version=version, graphics_data=bytes(graphics_src)
    )


class MetaAndArchiveContractTests:
    def test_meta_builder_reuses_blocks_until_the_existing_group_reaches_the_limit(
        self,
    ) -> None:
        from fivefury.meta.builder import MetaBuilder

        builder = MetaBuilder()
        first = builder._add_block(305419896, bytes(16368), group=True)
        second = builder._add_block(305419896, bytes(48), group=True)
        assert first.block_id == second.block_id
        assert len(builder.blocks) == 1
        assert len(builder.blocks[0].data) == 16416

    def test_meta_builder_pages_info_uses_total_page_count(self) -> None:
        from fivefury.meta.builder import MetaBuilder
        from fivefury.resource import get_resource_total_page_count

        builder = MetaBuilder()
        for _ in range(3):
            builder._add_block(305419896, bytes(12288), group=False)
        system = builder._compose_system_stream(0)
        pages_info = struct.unpack_from("<IIBBHI", system, 112)
        assert builder.page_count > 1
        assert pages_info[2] == get_resource_total_page_count(builder.page_flags)

    @pytest.mark.integration
    def test_good_ymap_roundtrip_preserves_meta_layout_contract(self) -> None:
        from fivefury import read_ymap

        source = configured_path(
            "FIVEFURY_TEST_YMAP", reference_root() / "ymap/aliencity4.ymap"
        )
        if not source.exists():
            pytest.fail("Representative working YMAP fixture is not available")
        original = _parse_meta_layout(source.read_bytes())
        rebuilt = _parse_meta_layout(read_ymap(source.read_bytes()).to_bytes())
        assert rebuilt["header"].system_flags == original["header"].system_flags
        assert rebuilt["header"].system_size == original["header"].system_size
        assert rebuilt["pages_info"] == original["pages_info"]
        assert rebuilt["struct_ptr"] == original["struct_ptr"]
        assert rebuilt["enum_ptr"] == original["enum_ptr"]
        assert rebuilt["data_block_ptr"] == original["data_block_ptr"]
        assert rebuilt["data_block_count"] == original["data_block_count"]
        assert rebuilt["data_blocks"] == original["data_blocks"]

    @pytest.mark.integration
    def test_good_ytyp_roundtrip_preserves_meta_layout_contract(self) -> None:
        from fivefury import read_ytyp

        source = configured_path(
            "FIVEFURY_TEST_YTYP", reference_root() / "ytyp/alien.ytyp"
        )
        if not source.exists():
            pytest.fail("Representative working YTYP fixture is not available")
        original = _parse_meta_layout(source.read_bytes())
        rebuilt = _parse_meta_layout(read_ytyp(source.read_bytes()).to_bytes())
        assert rebuilt["header"].system_flags == original["header"].system_flags
        assert rebuilt["header"].system_size == original["header"].system_size
        assert rebuilt["pages_info"] == original["pages_info"]
        assert rebuilt["struct_ptr"] == original["struct_ptr"]
        assert rebuilt["enum_ptr"] == original["enum_ptr"]
        assert rebuilt["data_block_ptr"] == original["data_block_ptr"]
        assert rebuilt["data_block_count"] == original["data_block_count"]
        assert rebuilt["data_blocks"] == original["data_blocks"]

    def test_ymap_high_level_save(self, tmp_path):
        from fivefury import Ymap, read_ymap

        output = tmp_path / "unit_test.ymap"
        Ymap(name="unit_test").save(output)
        assert read_ymap(output.read_bytes()).name == "unit_test"

    def test_ymap_and_ytyp_high_level_factories(self):
        from fivefury import Ymap, Ytyp

        ymap, ytyp = (Ymap(name="unit_test"), Ytyp(name="unit_test"))
        entity = ymap.entity(archetype_name="prop_tree_pine_01")
        archetype = ytyp.archetype(name="prop_tree_pine_01")
        assert ymap.entities == [entity]
        assert ytyp.archetypes == [archetype]

    def test_high_level_factories_default_to_empty_internal_resource_names(self):
        from fivefury import Ymap, Ytyp

        for asset in (Ymap(name="unit_test.ymap"), Ytyp(name="unit_test.ytyp")):
            assert asset.meta_name == ""
            assert asset.resource_name == ""

    def test_models_expose_resource_name_property(self):
        from fivefury import Ymap, Ytyp

        for asset, name in (
            (Ymap(name="unit_test"), "folder/unit_test.ymap"),
            (Ytyp(name="unit_test"), "folder/unit_test.ytyp"),
        ):
            asset.resource_name = name
            assert asset.meta_name == name
            assert asset.resource_name == name

    def test_declarative_aliases_are_exposed(self) -> None:
        entity = Entity(archetype_name="prop_tree_pine_01", guid=7, lod_dist=25.0)
        archetype = Archetype(name="prop_tree_pine_01", lod_dist=60.0)
        room = Room(name="room_01")
        grass_batch = GrassBatch(archetype_name="prop_bush_lrg_04", lod_dist=80)
        instanced_data = InstancedData(grass_instance_list=[grass_batch])
        lod_lights = LodLights(direction=[], falloff=[])
        assert entity.archetype_name == "prop_tree_pine_01"
        assert archetype.name == "prop_tree_pine_01"
        assert archetype.asset_name == "prop_tree_pine_01"
        assert room.name == "room_01"
        assert len(instanced_data.grass_instance_list) == 1
        assert lod_lights.direction == []

    def test_ymap_typed_surfaces_roundtrip(self, tmp_path):
        from fivefury import (
            BoxOccluder,
            DistantLodLights,
            Entity,
            LodLights,
            OccludeModel,
            Ymap,
        )

        ymap = Ymap(name="surfaces")
        ymap.entities.append(
            Entity(
                archetype_name="prop_tree_pine_01",
                position=Vector3(1, 2, 3),
                lod_dist=25,
            )
        )
        ymap.box_occluders = [BoxOccluder()]
        ymap.occlude_models = [OccludeModel()]
        ymap.lod_lights = LodLights(
            direction=[Vector3(0, 0, -1)],
            falloff=[1],
            falloff_exponent=[1],
            time_and_state_flags=[0],
            hash=[0],
            cone_inner_angle=[0],
            cone_outer_angle_or_cap_ext=[0],
            corona_intensity=[0],
        )
        ymap.distant_lod_lights = DistantLodLights(
            position=[Vector3(1, 2, 3)], RGBI=[0]
        )
        output = tmp_path / "surfaces.ymap"
        ymap.save(output, auto_extents=True)
        parsed = Ymap.from_bytes(output.read_bytes())
        assert isinstance(parsed.box_occluders[0], BoxOccluder)
        assert isinstance(parsed.occlude_models[0], OccludeModel)
        assert parsed.lod_lights.direction == ymap.lod_lights.direction
        assert parsed.distant_lod_lights.position == ymap.distant_lod_lights.position

    def test_ymap_grass_and_extensions_roundtrip(self) -> None:
        from fivefury import (
            Aabb,
            Entity,
            GrassBatch,
            GrassInstance,
            ParticleEffectExtension,
            Ymap,
        )

        ymap = Ymap(name="typed_surfaces.ymap")
        entity = Entity(
            archetype_name="prop_tree_pine_01",
            position=Vector3(10.0, 20.0, 30.0),
            lod_dist=45.0,
        )
        entity.extensions.append(
            ParticleEffectExtension(
                name="fx_smoke",
                offset_position=Vector3(1.0, 2.0, 3.0),
                offset_rotation=Quaternion(),
                fx_name="scr_wheel_burnout",
                fx_type=2,
                bone_tag=0,
                scale=1.25,
                probability=75,
                flags=3,
                color=287454020,
            )
        )
        ymap.entities.append(entity)
        batch = GrassBatch(
            batch_aabb=Aabb(minimum=Vector3(), maximum=Vector3(20.0, 20.0, 10.0)),
            scale_range=Vector3(0.8, 1.0, 1.2),
            archetype_name="prop_grass_01",
            lod_dist=80,
            lod_fade_start_dist=40.0,
            lod_inst_fade_range=15.0,
            orient_to_terrain=1.0,
        )
        batch.instances.append(
            GrassInstance(
                position=Vector3(5.0, 6.0, 2.0),
                normal=Vector3(0.0, 0.0, 1.0),
                color=(10, 20, 30),
                scale=120,
                ao=90,
            )
        )
        ymap.ensure_instanced_data().grass_instance_list.append(batch)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "typed_surfaces.ymap"
            ymap.save(output, auto_extents=True)
            parsed = type(ymap).from_bytes(output.read_bytes())
        assert parsed.content_flags != 0
        assert len(parsed.entities) == 1
        parsed_entity = parsed.entities[0]
        assert len(parsed_entity.extensions) == 1
        particle = parsed_entity.extensions[0]
        assert particle.fx_name == "scr_wheel_burnout"
        assert particle.fx_type == 2
        assert particle.scale == pytest.approx(1.25, abs=10 ** (-3), rel=0)
        assert parsed.instanced_data is not None
        assert len(parsed.instanced_data.grass_instance_list) == 1
        parsed_batch = parsed.instanced_data.grass_instance_list[0]
        assert len(parsed_batch.instances) == 1
        parsed_instance = parsed_batch.instances[0]
        assert parsed_instance.position.x == pytest.approx(5.0, abs=10 ** (-2), rel=0)
        assert parsed_instance.position.y == pytest.approx(6.0, abs=10 ** (-2), rel=0)
        assert parsed_instance.position.z == pytest.approx(2.0, abs=10 ** (-2), rel=0)
        assert parsed_instance.color == (10, 20, 30)
        assert parsed_instance.scale == 120
        assert parsed_instance.ao == 90

    def test_ymap_known_extension_types_roundtrip_as_objects(self) -> None:
        from fivefury import (
            ClimbHandHoldExtension,
            DecalExtension,
            Entity,
            LightExtension,
            ScriptChildExtension,
            ScriptExtension,
            ScrollbarsExtension,
            SwayableEffectExtension,
            WalkDontWalkExtension,
            Ymap,
        )

        ymap = Ymap(name="complete_extensions.ymap")
        entity = Entity(
            archetype_name="prop_extension_test",
            position=Vector3(1.0, 2.0, 3.0),
            lod_dist=50.0,
        )
        entity.extensions.extend(
            [
                DecalExtension(
                    name="decal_marker",
                    offset_position=Vector3(0.1, 0.2, 0.3),
                    offset_rotation=Quaternion(),
                    decal_name="blood_entry",
                    decal_type=4,
                    bone_tag=2,
                    scale=1.5,
                    probability=80,
                    flags=7,
                ),
                LightExtension(
                    name="light_marker", offset_position=Vector3(1.0, 0.0, 0.0)
                ),
                WalkDontWalkExtension(
                    name="crossing_marker", offset_position=Vector3(2.0, 0.0, 0.0)
                ),
                ClimbHandHoldExtension(
                    name="climb_marker",
                    offset_position=Vector3(3.0, 0.0, 0.0),
                    left=Vector3(-0.5, 0.0, 1.0),
                    right=Vector3(0.5, 0.0, 1.0),
                    normal=Vector3(0.0, 1.0, 0.0),
                ),
                ScrollbarsExtension(
                    name="scroll_marker",
                    offset_position=Vector3(4.0, 0.0, 0.0),
                    height=2.0,
                    scrollbars_type=3,
                    points=[Vector3(), Vector3(1.0, 2.0, 3.0)],
                ),
                SwayableEffectExtension(
                    name="sway_marker",
                    offset_position=Vector3(5.0, 0.0, 0.0),
                    bone_tag=5,
                    low_wind_speed=1.0,
                    low_wind_amplitude=0.2,
                    high_wind_speed=6.0,
                    high_wind_amplitude=0.8,
                ),
                ScriptExtension(
                    name="script_marker",
                    offset_position=Vector3(6.0, 0.0, 0.0),
                    script_name="example_script",
                    children=[
                        ScriptChildExtension(
                            position=Vector3(7.0, 8.0, 9.0), rotation_z=1.25
                        )
                    ],
                ),
            ]
        )
        ymap.entities.append(entity)
        parsed = Ymap.from_bytes(ymap.build(auto_extents=True).to_bytes())
        parsed_extensions = parsed.entities[0].extensions
        assert [type(extension) for extension in parsed_extensions] == [
            DecalExtension,
            LightExtension,
            WalkDontWalkExtension,
            ClimbHandHoldExtension,
            ScrollbarsExtension,
            SwayableEffectExtension,
            ScriptExtension,
        ]
        assert parsed_extensions[0].decal_name == "blood_entry"
        assert parsed_extensions[4].points == [Vector3(), Vector3(1.0, 2.0, 3.0)]
        assert parsed_extensions[6].script_name == "example_script"
        assert parsed_extensions[6].children[0].position == Vector3(7.0, 8.0, 9.0)

    def test_ytyp_archetype_extensions_roundtrip(self) -> None:
        from fivefury import Archetype, ParticleEffectExtension, Ytyp

        ytyp = Ytyp(name="typed_archetypes.ytyp")
        archetype = Archetype(
            name="prop_test_arch",
            lod_dist=120.0,
            asset_type=0,
            bb_min=Vector3(-1.0, -1.0, -1.0),
            bb_max=Vector3(1.0, 1.0, 1.0),
            bs_centre=Vector3(),
            bs_radius=2.0,
        )
        archetype.extensions.append(
            ParticleEffectExtension(
                name="fx_arch",
                offset_position=Vector3(0.5, 0.0, 0.0),
                offset_rotation=Quaternion(),
                fx_name="scr_rcbarry2_sparks",
                fx_type=7,
                scale=0.75,
                probability=55,
                flags=1,
                color=1432778632,
            )
        )
        ytyp.archetypes.append(archetype)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "typed_archetypes.ytyp"
            ytyp.save(output)
            parsed = type(ytyp).from_bytes(output.read_bytes())
        assert len(parsed.archetypes) == 1
        parsed_archetype = parsed.archetypes[0]
        assert len(parsed_archetype.extensions) == 1
        particle = parsed_archetype.extensions[0]
        assert particle.fx_name == "scr_rcbarry2_sparks"
        assert particle.fx_type == 7
        assert particle.scale == pytest.approx(0.75, abs=10 ** (-3), rel=0)

    def test_rpf_archive_accepts_high_level_asset_objects(self, tmp_path):
        from fivefury import RpfArchive, Ymap, Ytyp, read_ymap, read_ytyp

        archive = RpfArchive.empty("unit_test.rpf")
        archive.file("maps/unit_test.ymap", Ymap(name="unit_test"))
        ytyp = Ytyp(name="unit_test")
        ytyp.archetype(name="prop_tree_pine_01", lod_dist=100)
        archive.file("models/unit_test.ytyp", ytyp)
        output = tmp_path / "unit_test.rpf"
        archive.save(output)
        from fivefury import GameFileCache

        with GameFileCache(use_index_cache=False) as cache:
            cache.scan(tmp_path, load_keys=False)
            assert (
                read_ymap(cache.read_bytes("unit_test.rpf/maps/unit_test.ymap")).name
                == "unit_test"
            )
            assert (
                read_ytyp(cache.read_bytes("unit_test.rpf/models/unit_test.ytyp")).name
                == "unit_test"
            )

    def test_minimal_rsc7_meta_roundtrip(self):
        from fivefury.meta import Meta
        from fivefury.resource import build_rsc7, parse_rsc7

        meta = Meta(Name="unit_test.ymap")
        payload = build_rsc7(meta)
        assert payload[:4] == b"RSC7"
        header, system = parse_rsc7(payload)
        assert header.version == meta.resource_version
        assert system

    def test_rpf_zip_roundtrip_nested_rpf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            archive = root / "out.rpf"
            roundtrip = root / "roundtrip.zip"
            write_bytes(source / "content.txt", b"hello world")
            write_bytes(source / "nested.rpf" / "inner.bin", b"\x01\x02\x03")
            touch(source / "nested.rpf" / "deeper.rpf" / "note.txt", "nested")
            zip_payload = root / "source.zip"
            with zipfile.ZipFile(
                zip_payload, "w", compression=zipfile.ZIP_DEFLATED
            ) as zf:
                for file_path in source.rglob("*"):
                    if file_path.is_file():
                        zf.write(file_path, file_path.relative_to(source).as_posix())
            produced = zip_to_rpf(zip_payload, archive)
            assert produced == archive.read_bytes()
            result = rpf_to_zip(archive, roundtrip)
            assert result == roundtrip.read_bytes()

            with zipfile.ZipFile(roundtrip) as restored:
                assert restored.read("content.txt") == b"hello world"
                assert restored.read("nested.rpf/inner.bin") == b"\x01\x02\x03"
                assert restored.read("nested.rpf/deeper.rpf/note.txt") == b"nested"

    def test_ensure_game_crypto_provides_default_instance(self) -> None:
        from fivefury import clear_game_crypto, ensure_game_crypto, get_game_crypto

        clear_game_crypto()
        crypto = ensure_game_crypto()
        assert crypto is not None
        assert crypto is get_game_crypto()

    def test_encrypted_rpf_can_auto_resolve_default_crypto(self) -> None:
        from fivefury import RpfArchive, RpfEncryption, clear_game_crypto, create_rpf

        class _FakeCrypto:
            def decrypt_archive_table(
                self, data, encryption, *, archive_name, archive_size
            ):
                return data

            def decrypt_entry_payload(
                self, data, encryption, *, entry_name, entry_length
            ):
                return data

        archive = create_rpf("auto_crypto.rpf")
        archive.file("hello.txt", b"hello")
        encrypted = bytearray(archive.to_bytes())
        struct.pack_into("<I", encrypted, 12, RpfEncryption.NG)
        clear_game_crypto()
        with patch(
            "fivefury.rpf.archive.ensure_game_crypto", return_value=_FakeCrypto()
        ) as mocked:
            parsed = RpfArchive.from_bytes(bytes(encrypted), name="auto_crypto.rpf")
        mocked.assert_called_once()
        entry = parsed.find_entry("hello.txt")
        assert entry is not None
        assert entry.read() == b"hello"

    def test_zip_to_rpf_accepts_directory_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "src"
            archive = root / "dir_source.rpf"
            roundtrip = root / "dir_source.zip"
            touch(source / "levels" / "pkg.rpf" / "nested.txt", "nested from dir")
            write_bytes(source / "levels" / "pkg.rpf" / "data.bin", b"\x10 0")
            touch(source / "levels" / "readme.txt", "hello")
            produced = zip_to_rpf(source, archive)
            assert produced == archive.read_bytes()
            result = rpf_to_zip(archive, roundtrip)
            assert result == roundtrip.read_bytes()
            with zipfile.ZipFile(roundtrip, "r") as zf:
                names = set(zf.namelist())
                assert "levels/readme.txt" in names
                assert "levels/pkg.rpf/nested.txt" in names
                assert "levels/pkg.rpf/data.bin" in names

    def test_rpf_to_folder_expands_nested_archives(self) -> None:
        from fivefury import RpfExportMode, create_rpf, rpf_to_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("root.rpf")
            archive.file("content.txt", b"hello world")
            _, nested = archive.nested_archive("nested.rpf")
            nested.file("inner.bin", b"\x01\x02\x03")
            _, deeper = nested.nested_archive("deeper.rpf")
            deeper.file("note.txt", b"nested")
            out_dir = root / "out"
            written = rpf_to_folder(archive, out_dir, mode=RpfExportMode.STANDALONE)
            assert out_dir / "content.txt" in written
            assert out_dir / "nested.rpf" / "inner.bin" in written
            assert out_dir / "nested.rpf" / "deeper.rpf" / "note.txt" in written
            assert (out_dir / "nested.rpf").is_dir()
            assert not (out_dir / "nested.rpf").is_file()
            assert (
                out_dir / "nested.rpf" / "deeper.rpf" / "note.txt"
            ).read_bytes() == b"nested"

    def test_rpf_to_folder_supports_stored_standalone_and_logical_modes(self) -> None:
        from fivefury import RpfExportMode, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("modes.rpf")
            archive.file("bin/data.bin", b"plain binary", compress_binary=True)
            archive.file("maps/example.ymap", b"logical payload")
            stored_dir = root / "stored"
            standalone_dir = root / "standalone"
            logical_dir = root / "logical"
            archive.to_folder(stored_dir, mode=RpfExportMode.STORED)
            archive.to_folder(standalone_dir, mode=RpfExportMode.STANDALONE)
            archive.to_folder(logical_dir, mode=RpfExportMode.LOGICAL)
            assert (logical_dir / "bin" / "data.bin").read_bytes() == b"plain binary"
            assert (stored_dir / "bin" / "data.bin").read_bytes() != b"plain binary"
            assert (standalone_dir / "bin" / "data.bin").read_bytes() == b"plain binary"
            assert (
                logical_dir / "maps" / "example.ymap"
            ).read_bytes() == b"logical payload"
            assert (standalone_dir / "maps" / "example.ymap").read_bytes()[
                :4
            ] == b"RSC7"
            assert (stored_dir / "maps" / "example.ymap").read_bytes()[:4] == b"RSC7"

    def test_rpf_nested_archives_load_on_demand(self) -> None:
        from fivefury import RpfArchive, create_rpf

        archive = create_rpf("root.rpf")
        _, nested = archive.nested_archive("nested.rpf")
        nested.file("inner.txt", b"lazy")
        parsed = RpfArchive.from_bytes(archive.to_bytes(), name="root.rpf")
        assert parsed.children == []
        assert parsed.find_entry("nested.rpf").name == "nested.rpf"
        assert parsed.children == []
        inner = parsed.find_entry("nested.rpf/inner.txt")
        assert inner is not None
        assert inner.read() == b"lazy"
        assert len(parsed.children) == 1

    def test_rpf_to_folder_handles_file_directory_collisions(self) -> None:
        from fivefury import RpfExtractionConflict, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            archive = create_rpf("collisions.rpf")
            archive.directory("shared")
            archive.file("shared", b"file payload")
            output = Path(tmpdir) / "suffix"
            written = archive.to_folder(output, conflict=RpfExtractionConflict.SUFFIX)
            assert (output / "shared").is_dir()
            assert (output / "shared.__file__").read_bytes() == b"file payload"
            assert output / "shared.__file__" in written
            with pytest.raises(FileExistsError):
                archive.to_folder(
                    Path(tmpdir) / "error", conflict=RpfExtractionConflict.ERROR
                )

    def test_rpf_can_stream_save_over_its_source_path(self) -> None:
        from fivefury import RpfArchive, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "in_place.rpf"
            source = create_rpf("in_place.rpf")
            source.file("original.txt", b"original")
            source.save(path)
            with RpfArchive.from_path(path) as archive:
                archive.file("added.txt", b"added")
                archive.save(path)
            with RpfArchive.from_path(path) as reread:
                assert reread.find_entry("original.txt").read() == b"original"
                assert reread.find_entry("added.txt").read() == b"added"

    def test_rpf_to_folder_defaults_to_standalone_export(self) -> None:
        from fivefury import create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("default_export.rpf")
            archive.file("maps/example.ymap", b"logical payload")
            out_dir = root / "out"
            archive.to_folder(out_dir)
            assert (out_dir / "maps" / "example.ymap").read_bytes()[:4] == b"RSC7"

    def test_rpf_export_mode_enum_exposes_descriptions(self) -> None:
        from fivefury import RpfExportMode

        assert RpfExportMode.STORED.value == "stored"
        assert "stored in the RPF" in RpfExportMode.STORED.description
        assert "RSC7" in RpfExportMode.STANDALONE.description
        assert "logical payload" in RpfExportMode.LOGICAL.description

    def test_gamefilecache_basic_indexing(self, tmp_path):
        from fivefury import GameFileCache

        write_bytes(tmp_path / "maps/example.ytyp", b"dummy")
        write_bytes(tmp_path / "maps/example.ymap", b"dummy")
        with GameFileCache(use_index_cache=False) as cache:
            cache.scan(tmp_path, load_keys=False)
            assert cache.get_asset("maps/example.ytyp") is not None
            assert cache.get_asset("maps/example.ymap") is not None

    def test_gamefilecache_exposes_type_dicts_by_short_name_hash(self) -> None:
        from fivefury import GameFileCache, create_rpf, jenk_hash

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("assets.rpf")
            archive.file("stream/alpha.ydr", b"alpha")
            archive.file("stream/bravo.ytd", b"bravo")
            archive.file("stream/collision.ybn", b"collision")
            archive.file("stream/pack.ydd", b"pack")
            archive.save(root / "assets.rpf")
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            ydr_dict = cache.YdrDict
            assert ydr_dict[jenk_hash("alpha")].path == "assets.rpf/stream/alpha.ydr"
            assert (
                cache.YtdDict[jenk_hash("bravo")].path == "assets.rpf/stream/bravo.ytd"
            )
            assert (
                cache.YbnDict[jenk_hash("collision")].path
                == "assets.rpf/stream/collision.ybn"
            )
            assert (
                cache.get_kind_dict(".ydd")[jenk_hash("pack")].path
                == "assets.rpf/stream/pack.ydd"
            )
            assert cache.kind_dict(".ydr") is cache.YdrDict
            assert len(cache.YdrDict) == 1
            write_bytes(root / "maps" / "delta.ydr", b"delta")
            cache.scan(use_index_cache=False)
            assert jenk_hash("delta") in ydr_dict
            assert ydr_dict[jenk_hash("delta")].path == "maps/delta.ydr"
            assert ydr_dict[jenk_hash("alpha")].path == "assets.rpf/stream/alpha.ydr"

    def test_gamefilecache_supports_simple_file_by_file_iteration_helpers(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("assets.rpf")
            archive.file("stream/alpha.ydr", b"alpha")
            archive.file("stream/bravo.ytd", b"bravo")
            archive.save(root / "assets.rpf")
            write_bytes(root / "maps" / "charlie.ymap", b"charlie")
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            assert len(cache) == 3
            assert [asset.path for asset in cache] == [
                "assets.rpf/stream/alpha.ydr",
                "assets.rpf/stream/bravo.ytd",
                "maps/charlie.ymap",
            ]
            assert [asset.path for asset in cache.iter_kind(".ydr")] == [
                "assets.rpf/stream/alpha.ydr"
            ]
            assert [asset.path for asset in cache.list_kind(".ytd")] == [
                "assets.rpf/stream/bravo.ytd"
            ]
            assert cache.list_kind_paths(".ymap") == ["maps/charlie.ymap"]

    def test_gamefilecache_builds_lazy_global_archetype_dict(self) -> None:
        from fivefury import Archetype, GameFileCache, Ytyp, jenk_hash

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "types").mkdir(parents=True, exist_ok=True)
            ytyp = Ytyp(name="example_types")
            ytyp.archetypes.append(Archetype(name="prop_tree_pine_01", lod_dist=100.0))
            ytyp.archetypes.append(Archetype(name="prop_sign_road_01", lod_dist=50.0))
            ytyp.save(root / "types" / "example_types.ytyp")
            cache = GameFileCache(root, use_index_cache=False, max_loaded_files=0)
            cache.scan(use_index_cache=False)
            archetype_dict = cache.archetype_dict
            assert int(
                archetype_dict[jenk_hash("prop_tree_pine_01")].name
            ) == jenk_hash("prop_tree_pine_01")
            assert int(
                cache.ArchetypeDict[jenk_hash("prop_sign_road_01")].name
            ) == jenk_hash("prop_sign_road_01")
            assert int(cache.get_archetype("prop_tree_pine_01").name) == jenk_hash(
                "prop_tree_pine_01"
            )
            assert cache.has_archetype("prop_sign_road_01")
            assert sorted(
                int(archetype.name) for archetype in cache.iter_archetypes()
            ) == sorted(
                [jenk_hash("prop_tree_pine_01"), jenk_hash("prop_sign_road_01")]
            )
            extra = Ytyp(name="more_types")
            extra.archetypes.append(Archetype(name="prop_bench_01", lod_dist=25.0))
            extra.save(root / "types" / "more_types.ytyp")
            cache.scan(use_index_cache=False)
            assert jenk_hash("prop_bench_01") in archetype_dict
            assert int(cache.find_archetype("prop_bench_01").name) == jenk_hash(
                "prop_bench_01"
            )

    def test_gamefilecache_exposes_kind_counts_and_stats(self) -> None:
        from fivefury import GameFileCache, GameFileType, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("assets.rpf")
            archive.file("stream/alpha.ydr", b"alpha")
            archive.file("stream/bravo.ytd", b"bravo")
            archive.save(root / "assets.rpf")
            write_bytes(root / "maps" / "charlie.ymap", b"charlie")
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            counts = cache.kind_counts
            assert counts[GameFileType.YDR] == 1
            assert counts[".ytd"] == 1
            assert counts["ymap"] == 1
            assert cache.stats_by_kind() == {"YDR": 1, "YMAP": 1, "YTD": 1}
            assert cache.summary()["kind_counts"] == {"YDR": 1, "YMAP": 1, "YTD": 1}
            write_bytes(root / "maps" / "delta.ymap", b"delta")
            cache.scan(use_index_cache=False)
            assert counts[GameFileType.YMAP] == 2
            assert cache.stats_by_kind()["YMAP"] == 2

    def test_gamefilecache_can_extract_assets_referenced_by_a_ymap(self) -> None:
        from fivefury import Archetype, Entity, GameFileCache, Ymap, Ytyp

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "maps").mkdir(parents=True, exist_ok=True)
            (root / "types").mkdir(parents=True, exist_ok=True)
            ymap = Ymap(name="example_map")
            ymap.entities.append(Entity(archetype_name="prop_tree_pine_01", guid=1))
            ymap.recalculate_extents()
            ymap.recalculate_flags()
            ymap.save(root / "maps" / "example_map.ymap")
            ytyp = Ytyp(name="example_types")
            ytyp.archetypes.append(
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
            assets = cache.list_ymap_entity_assets(
                "example_map", include_supporting=True
            )
            assert sorted(asset.path for asset in assets) == sorted(
                [
                    "assets/prop_tree_pine_01.ybn",
                    "assets/prop_tree_pine_01.ydr",
                    "assets/prop_tree_pine_01.ytd",
                ]
            )
            primary_only = cache.list_ymap_entity_assets(
                "example_map", include_supporting=False
            )
            assert [asset.path for asset in primary_only] == [
                "assets/prop_tree_pine_01.ydr"
            ]
            extracted = cache.extract_ymap_assets("example_map", root / "out")
            assert sorted(path.name for path in extracted) == [
                "prop_tree_pine_01.ybn",
                "prop_tree_pine_01.ydr",
                "prop_tree_pine_01.ytd",
            ]
            assert (root / "out" / "prop_tree_pine_01.ydr").read_bytes() == b"ydr"

    def test_gamefilecache_can_resolve_assets_from_an_external_loose_ymap(self) -> None:
        from fivefury import Archetype, Entity, GameFileCache, Ymap, Ytyp

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            root = tmp / "cache_root"
            external = tmp / "external"
            (root / "types").mkdir(parents=True, exist_ok=True)
            external.mkdir(parents=True, exist_ok=True)
            ymap = Ymap(name="external_map")
            ymap.entities.append(Entity(archetype_name="prop_tree_pine_01", guid=1))
            ymap.recalculate_extents()
            ymap.recalculate_flags()
            external_ymap = external / "external_map.ymap"
            ymap.save(external_ymap)
            ytyp = Ytyp(name="example_types")
            ytyp.archetypes.append(
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
            assert sorted(asset.path for asset in assets) == [
                "assets/prop_tree_pine_01.ydr",
                "assets/prop_tree_pine_01.ytd",
            ]

    def test_gamefilecache_supports_name_hash_read_and_extract_workflows(self) -> None:
        from fivefury import GameFileCache, create_rpf, jenk_hash

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive_path = root / "assets.rpf"
            archive = create_rpf("assets.rpf")
            archive.file("stream/alpha.ydr", b"alpha-bytes")
            archive.file("stream/bravo.ytd", b"bravo-bytes")
            archive.save(archive_path)
            write_bytes(root / "maps" / "charlie.ymap", b"charlie-bytes")
            cache = GameFileCache(root)
            cache.scan()
            assert cache.scan_errors == {}
            by_path = cache.find_path("assets.rpf/stream/alpha.ydr")
            assert by_path is not None
            assert by_path.path == "assets.rpf/stream/alpha.ydr"
            by_name = cache.find_name("alpha", kind=".ydr")
            assert len(by_name) == 1
            assert by_name[0].path == "assets.rpf/stream/alpha.ydr"
            by_hash = cache.find_hash(jenk_hash("alpha"), kind=".ydr")
            assert len(by_hash) == 1
            assert by_hash[0].path == "assets.rpf/stream/alpha.ydr"
            payload = cache.read_asset("assets.rpf/stream/alpha.ydr")
            assert payload == b"alpha-bytes"
            assert cache.read_bytes("alpha") == b"alpha-bytes"
            extracted = cache.extract_asset("alpha", root / "out")
            assert extracted is not None
            assert Path(extracted).read_bytes() == b"alpha-bytes"

    def test_gamefilecache_extracts_resource_assets_as_stored_bytes_by_default(
        self,
    ) -> None:
        from fivefury import GameFileCache, create_rpf
        from fivefury.resource import RSC7_MAGIC, parse_rsc7

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive_path = root / "assets.rpf"
            archive = create_rpf("assets.rpf")
            archive.file("stream/example.ymap", b"payload-bytes")
            archive.save(archive_path)
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            extracted = cache.extract_asset(
                "assets.rpf/stream/example.ymap", root / "out"
            )
            assert extracted is not None
            stored = Path(extracted).read_bytes()
            assert stored[:4] == struct.pack("<I", RSC7_MAGIC)
            assert parse_rsc7(stored)[1] == b"payload-bytes"
            logical = cache.extract_asset(
                "assets.rpf/stream/example.ymap", root / "logical.ymap", logical=True
            )
            assert logical is not None
            assert Path(logical).read_bytes() == b"payload-bytes"

    def test_gamefilecache_can_skip_audio_vehicle_and_ped_assets_during_scan(
        self,
    ) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            audio = create_rpf("audio_pack.rpf")
            audio.file("x64/audio/sfx/test.awc", b"audio")
            audio.save(root / "audio_pack.rpf")
            vehicles = create_rpf("vehicle_pack.rpf")
            vehicles.file("stream/vehicles.meta", b"vehicles")
            vehicles.save(root / "vehicle_pack.rpf")
            peds = create_rpf("ped_pack.rpf")
            peds.file("stream/peds.ymt", b"peds")
            peds.save(root / "ped_pack.rpf")
            write_bytes(root / "maps" / "example.ymap", b"map")
            cache = GameFileCache(
                root, load_audio=False, load_vehicles=False, load_peds=False
            )
            cache.scan(use_index_cache=False)
            assert cache.scan_errors == {}
            assert cache.asset_count == 1
            assert cache.find_name("test.awc") == []
            assert cache.find_name("vehicles.meta") == []
            assert cache.find_name("peds.ymt") == []
            assert cache.find_path("maps/example.ymap") is not None

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
            audio.file("sfx/test.awc", b"audio")
            audio.save(root / "x64" / "audio" / "audio_rel.rpf")
            vehicles = create_rpf("vehicles.rpf")
            vehicles.file("stream/vehicles.meta", b"vehicles")
            vehicles.save(root / "x64" / "levels" / "gta5" / "vehicles.rpf")
            peds = create_rpf("pedprops.rpf")
            peds.file("stream/peds.ymt", b"peds")
            peds.save(root / "x64" / "models" / "cdimages" / "pedprops.rpf")
            world = create_rpf("world.rpf")
            world.file("stream/keep.ydr", b"keep")
            world.save(root / "mods" / "world.rpf")
            original = cache_module._scan_archive_sources_batch
            baseline_calls: list[str] = []
            filtered_calls: list[str] = []

            def delayed_scan(
                sources, index, crypto, hash_lut, skip_mask=0, workers=0, verbose=False
            ):
                target = filtered_calls if skip_mask else baseline_calls
                target.extend((str(source_prefix) for _, source_prefix in sources))
                return original(
                    sources, index, crypto, hash_lut, skip_mask, workers, verbose
                )

            with patch.object(
                cache_module, "_scan_archive_sources_batch", side_effect=delayed_scan
            ):
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
            assert set(baseline_calls) == {
                "mods/world.rpf",
                "x64/audio/audio_rel.rpf",
                "x64/levels/gta5/vehicles.rpf",
                "x64/models/cdimages/pedprops.rpf",
            }
            assert filtered_calls == ["mods/world.rpf"]
            assert filtered.asset_count == 1

    def test_gamefilecache_supports_dlc_level_and_excluded_folders(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "update").mkdir(parents=True, exist_ok=True)
            (root / "update" / "x64" / "dlcpacks" / "mpalpha").mkdir(
                parents=True, exist_ok=True
            )
            (root / "update" / "x64" / "dlcpacks" / "mpbeta").mkdir(
                parents=True, exist_ok=True
            )
            (root / "scratch").mkdir(parents=True, exist_ok=True)
            update_archive = create_rpf("update.rpf")
            update_archive.file(
                "common/data/dlclist.xml",
                b"<SMandatoryPacksData><Paths><Item>dlcpacks:/mpalpha/</Item><Item>dlcpacks:/mpbeta/</Item></Paths></SMandatoryPacksData>",
            )
            update_archive.save(root / "update" / "update.rpf")
            alpha = create_rpf("dlc.rpf")
            alpha.file("x64/data/alpha.bin", b"alpha")
            alpha.save(root / "update" / "x64" / "dlcpacks" / "mpalpha" / "dlc.rpf")
            beta = create_rpf("dlc.rpf")
            beta.file("x64/data/beta.bin", b"beta")
            beta.save(root / "update" / "x64" / "dlcpacks" / "mpbeta" / "dlc.rpf")
            misc = create_rpf("misc.rpf")
            misc.file("scratch/hidden.bin", b"hidden")
            misc.save(root / "scratch" / "misc.rpf")
            cache = GameFileCache(root, dlc_level="mpalpha", exclude_folders="scratch")
            cache.scan()
            assert cache.dlc_names == ["mpalpha", "mpbeta"]
            assert cache.active_dlc_names == ["mpalpha"]
            assert cache.ignored_folders == ("scratch",)
            assert (
                cache.find_path(
                    "update/x64/dlcpacks/mpalpha/dlc.rpf/x64/data/alpha.bin"
                )
                is not None
            )
            assert (
                cache.find_path("update/x64/dlcpacks/mpbeta/dlc.rpf/x64/data/beta.bin")
                is None
            )
            assert cache.find_path("scratch/misc.rpf/scratch/hidden.bin") is None
            cache = GameFileCache(root)
            cache.use_dlc("mpalpha")
            cache.ignore_folders("scratch", "mods")
            assert cache.dlc_level == "mpalpha"
            assert cache.ignored_folders == ("scratch", "mods")

    def test_gamefilecache_reuses_persistent_index_cache_and_reports_timings(
        self,
    ) -> None:
        import fivefury.cache as cache_module
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index_path = root / "scan.ffindex"
            for archive_index in range(16):
                archive = create_rpf(f"pack_{archive_index}.rpf")
                for file_index in range(96):
                    archive.file(
                        f"stream/item_{archive_index}_{file_index}.ydr",
                        f"payload-{archive_index}-{file_index}".encode("ascii"),
                    )
                archive.save(root / f"pack_{archive_index}.rpf")
            original = cache_module._scan_archive_sources_batch

            def delayed_scan(
                sources, index, crypto, hash_lut, skip_mask=0, workers=0, verbose=False
            ):
                return original(
                    sources, index, crypto, hash_lut, skip_mask, workers, verbose
                )

            first = GameFileCache(root, index_cache_path=index_path, scan_workers=1)
            with patch.object(
                cache_module, "_scan_archive_sources_batch", side_effect=delayed_scan
            ):
                first.scan(use_index_cache=True)
            assert index_path.exists()
            assert first.last_scan is not None
            assert not first.last_scan.used_index_cache
            assert first.last_scan.saved_index_cache
            assert first.asset_count == 16 * 96
            second = GameFileCache(root, index_cache_path=index_path, scan_workers=1)
            with patch.object(
                cache_module,
                "_scan_archive_sources_batch",
                side_effect=AssertionError(
                    "Cached scans must not re-read archive tables"
                ),
            ):
                second.scan(use_index_cache=True)
            assert second.last_scan is not None
            assert second.last_scan.used_index_cache
            assert not second.last_scan.saved_index_cache
            assert second.asset_count == first.asset_count
            assert second.read_bytes("pack_0.rpf/stream/item_0_0.ydr") == b"payload-0-0"
            assert second.last_scan.elapsed_seconds >= 0

    def test_gamefilecache_parallel_scan_dispatches_configured_workers(
        self,
    ) -> None:
        import fivefury.cache as cache_module
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for archive_index in range(12):
                archive = create_rpf(f"pack_{archive_index}.rpf")
                for file_index in range(24):
                    archive.file(
                        f"stream/item_{archive_index}_{file_index}.ydr",
                        f"payload-{archive_index}-{file_index}".encode("ascii"),
                    )
                archive.save(root / f"pack_{archive_index}.rpf")
            original = cache_module._scan_archive_sources_batch

            worker_calls = []

            def traced_scan(
                sources, index, crypto, hash_lut, skip_mask=0, workers=0, verbose=False
            ):
                worker_calls.append(workers)
                return original(
                    sources, index, crypto, hash_lut, skip_mask, workers, verbose
                )

            with patch.object(
                cache_module, "_scan_archive_sources_batch", side_effect=traced_scan
            ):
                serial = GameFileCache(root, scan_workers=1)
                serial.scan(use_index_cache=False)
                parallel = GameFileCache(root, scan_workers=4)
                parallel.scan(use_index_cache=False)
            assert serial.asset_count == 12 * 24
            assert parallel.asset_count == serial.asset_count
            assert serial.last_scan.archive_workers == 1
            assert parallel.last_scan.archive_workers == 4
            assert worker_calls == [1, 4]

    def test_gamefilecache_scan_keeps_archive_handles_lazy_and_bounded(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for archive_index in range(4):
                archive = create_rpf(f"pack_{archive_index}.rpf")
                archive.file(
                    f"stream/item_{archive_index}.ydr",
                    f"payload-{archive_index}".encode("ascii"),
                )
                archive.save(root / f"pack_{archive_index}.rpf")
            cache = GameFileCache(
                root, use_index_cache=False, max_open_archives=2, scan_workers=2
            )
            cache.scan(use_index_cache=False)
            assert cache.open_archive_count == 0
            assert cache.archives == []
            assert cache.entries == {}
            assert all(
                record.entry is None and record.archive is None
                for record in cache.records
                if record.archive_rel
            )
            assert cache.read_bytes("pack_0.rpf/stream/item_0.ydr") == b"payload-0"
            assert cache.read_bytes("pack_1.rpf/stream/item_1.ydr") == b"payload-1"
            assert cache.read_bytes("pack_2.rpf/stream/item_2.ydr") == b"payload-2"
            assert cache.open_archive_count <= 2

    def test_gamefilecache_exposes_simple_scan_state(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.file("stream/a.ydr", b"a")
            archive.save(root / "pack.rpf")
            cache = GameFileCache(root, use_index_cache=False)
            assert not cache.scan_complete
            assert not cache.scan_ok
            assert not cache.has_assets
            assert not cache.has_scan_errors
            cache.scan(use_index_cache=False)
            summary = cache.summary()
            assert cache.scan_complete
            assert cache.scan_ok
            assert cache.has_assets
            assert not cache.has_scan_errors
            assert summary["asset_count"] == 1
            assert summary["scan_complete"]
            assert summary["scan_ok"]
            assert not summary["has_scan_errors"]
            assert summary["scan_error_count"] == 0

    def test_gamefilecache_verbose_prints_scan_and_read_activity(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.file("stream/a.ydr", b"a")
            archive.save(root / "pack.rpf")
            write_bytes(root / "maps" / "example.ymap", b"map")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cache = GameFileCache(root, use_index_cache=False, verbose=True)
                cache.scan(use_index_cache=False)
                assert cache.read_bytes("pack.rpf/stream/a.ydr") == b"a"
            output = buffer.getvalue()
            assert "[GameFileCache] scan start" in output
            assert "[GameFileCache] scan archive pack.rpf" in output
            assert "[GameFileCache] scan asset pack.rpf/stream/a.ydr" in output
            assert "[GameFileCache] scan file maps/example.ymap" in output
            assert "[GameFileCache] scan done" in output
            assert (
                "[GameFileCache] read bytes pack.rpf/stream/a.ydr logical=True"
                in output
            )

    def test_gamefilecache_uses_native_index_backend(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.file("stream/a.ydr", b"a")
            archive.file("stream/b.ydr", b"b")
            archive.save(root / "pack.rpf")
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            assert hasattr(cache, "_index")
            assert len(cache._index) == 2
            assert cache._index.get_path(0) == "pack.rpf/stream/a.ydr"
            assert cache._index.get_path(1) == "pack.rpf/stream/b.ydr"

    def test_gamefilecache_indexes_cut_and_ycd_from_rpf_as_explicit_kinds(self) -> None:
        from fivefury import GameFileCache, GameFileType, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("cuts.rpf")
            archive.file("cuts/sample.cut", b"cut")
            archive.file("cuts/sample-0.ycd", b"ycd")
            archive.save(root / "cuts.rpf")
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            cut = cache.find_path("cuts.rpf/cuts/sample.cut")
            ycd = cache.find_path("cuts.rpf/cuts/sample-0.ycd")
            assert cut is not None
            assert ycd is not None
            assert cut is not None
            assert ycd is not None
            assert cut.kind == GameFileType.CUT
            assert ycd.kind == GameFileType.YCD
            assert cache.kind_counts[GameFileType.CUT] == 1
            assert cache.kind_counts[GameFileType.YCD] == 1
            assert [record.path for record in cache.CutDict.values()] == [cut.path]
            assert [record.path for record in cache.YcdDict.values()] == [ycd.path]

    def test_gamefilecache_indexes_ynd_and_ynv_from_rpf_as_explicit_kinds(self) -> None:
        from fivefury import GameFileCache, GameFileType, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("nav.rpf")
            archive.file("nav/roads.YND", b"ynd")
            archive.file("nav/mesh.YNV", b"ynv")
            archive.save(root / "nav.rpf")
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            ynd = cache.find_path("nav.rpf/nav/roads.ynd")
            ynv = cache.find_path("nav.rpf/nav/mesh.ynv")
            assert ynd is not None
            assert ynv is not None
            assert ynd is not None
            assert ynv is not None
            assert ynd.kind == GameFileType.YND
            assert ynv.kind == GameFileType.YNV
            assert cache.kind_counts[GameFileType.YND] == 1
            assert cache.kind_counts[GameFileType.YNV] == 1
            assert [record.path for record in cache.YndDict.values()] == [ynd.path]
            assert [record.path for record in cache.YnvDict.values()] == [ynv.path]

    def test_gamefilecache_bounds_loaded_file_cache(self) -> None:
        from fivefury import GameFileCache, create_rpf

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.file("stream/a.ydr", b"a")
            archive.file("stream/b.ydr", b"b")
            archive.file("stream/c.ydr", b"c")
            archive.save(root / "pack.rpf")
            cache = GameFileCache(root, use_index_cache=False, max_loaded_files=2)
            cache.scan(use_index_cache=False)
            assert cache.get_file("pack.rpf/stream/a.ydr") is not None
            assert cache.get_file("pack.rpf/stream/b.ydr") is not None
            assert cache.open_file_count == 2
            assert "pack.rpf/stream/a.ydr" in cache.files
            assert "pack.rpf/stream/b.ydr" in cache.files
            assert cache.get_file("pack.rpf/stream/c.ydr") is not None
            assert cache.open_file_count == 2
            assert "pack.rpf/stream/a.ydr" not in cache.files
            assert "pack.rpf/stream/b.ydr" in cache.files
            assert "pack.rpf/stream/c.ydr" in cache.files

    def test_gamefilecache_reads_archive_assets_without_opening_archives(self) -> None:
        from fivefury import GameFileCache, create_rpf
        from fivefury._native import read_rpf_entry_variants
        from fivefury.hashing import _get_lut

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = create_rpf("pack.rpf")
            archive.file(
                "stream/sample.bin", b"hello native cache", compress_binary=True
            )
            archive.file("stream/test_dict.ytd", _build_test_ytd_bytes(enhanced=False))
            archive.save(root / "pack.rpf")
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            assert cache.open_archive_count == 0
            stored_native, standalone_native = read_rpf_entry_variants(
                root / "pack.rpf", "stream/test_dict.ytd", _get_lut()
            )
            assert stored_native
            assert standalone_native.startswith(b"RSC7")
            assert (
                cache.read_bytes("pack.rpf/stream/sample.bin", logical=True)
                == b"hello native cache"
            )
            assert cache.open_archive_count == 0
            game_file = cache.get_file("pack.rpf/stream/test_dict.ytd")
            assert game_file is not None
            assert type(game_file.parsed).__name__ == "Ytd"
            assert cache.open_archive_count == 0
            extracted = cache.extract_asset(
                "pack.rpf/stream/test_dict.ytd", root / "out"
            )
            assert extracted is not None
            assert extracted is not None
            assert extracted.read_bytes()[:4] == b"RSC7"
            assert cache.open_archive_count == 0

    def test_ytd_reader_parses_legacy_and_enhanced_dictionaries(self) -> None:
        from fivefury import read_ytd

        legacy = read_ytd(_build_test_ytd_bytes(enhanced=False))
        enhanced = read_ytd(_build_test_ytd_bytes(enhanced=True))
        assert len(legacy.textures) == 1
        assert len(enhanced.textures) == 1
        assert legacy.textures[0].name == "test_diffuse"
        assert enhanced.textures[0].name == "test_diffuse"
        assert legacy.textures[0].width == 4
        assert enhanced.textures[0].height == 4
        assert legacy.textures[0].mip_count == 1
        assert enhanced.textures[0].mip_count == 1

    def test_ytd_texture_usage_survives_a_round_trip(self) -> None:
        from fivefury.texture import (
            BCFormat,
            Texture,
            TextureUsage,
            total_mip_data_size,
        )
        from fivefury.ytd.model import Ytd

        data = bytes(total_mip_data_size(64, 64, BCFormat.BC1, 1))
        for game in ("gta5", "gta5_enhanced"):
            ytd = Ytd(
                textures=[
                    Texture.from_raw(
                        data,
                        64,
                        64,
                        BCFormat.BC1,
                        1,
                        name="spec_map",
                        usage=TextureUsage.SPECULAR,
                        usage_flags=16782720,
                    )
                ],
                game=game,
            )
            rebuilt = Ytd.from_bytes(ytd.to_bytes())
            assert rebuilt.textures[0].usage == TextureUsage.SPECULAR
            assert rebuilt.textures[0].usage_flags == 16782720

    def test_legacy_ytd_stores_usage_data_rather_than_a_byte_size(self) -> None:
        """The 0x40 word is UsageData, not a payload size.

        Shipped dictionaries keep the texture usage in its low 5 bits and streaming flags
        above them; writing a mip byte size there leaves an UNKNOWN usage and junk flags.
        """
        import struct

        from fivefury.resource import split_rsc7_sections
        from fivefury.texture import (
            BCFormat,
            Texture,
            TextureUsage,
            total_mip_data_size,
        )
        from fivefury.ytd.defs import DAT_VIRTUAL_BASE
        from fivefury.ytd.model import Ytd

        data = bytes(total_mip_data_size(2048, 2048, BCFormat.BC1, 1))
        ytd = Ytd(
            textures=[
                Texture.from_raw(
                    data,
                    2048,
                    2048,
                    BCFormat.BC1,
                    1,
                    name="big_diffuse",
                    usage=TextureUsage.DIFFUSE,
                )
            ],
            game="gta5",
        )
        _header, virtual_data, _physical = split_rsc7_sections(ytd.to_bytes())
        items_ptr = struct.unpack_from("<Q", virtual_data, 48)[0]
        tex_ptr = struct.unpack_from("<Q", virtual_data, items_ptr - DAT_VIRTUAL_BASE)[
            0
        ]
        usage_data = struct.unpack_from(
            "<I", virtual_data, tex_ptr - DAT_VIRTUAL_BASE + 64
        )[0]
        assert usage_data & 31 == int(TextureUsage.DIFFUSE)
        assert usage_data != len(data)

    def test_build_rsc7_adapts_page_size_for_large_graphics_sections(self) -> None:
        from fivefury.resource import (
            get_resource_flags_from_size_adaptive,
            get_resource_size_from_flags,
        )

        size = 3488920
        flags = get_resource_flags_from_size_adaptive(size, 13)
        assert get_resource_size_from_flags(flags) == _align(size, 1024)
        assert flags & 15 > 0

    def test_legacy_ytd_save_supports_large_graphics_payloads(self) -> None:
        from fivefury import read_ytd
        from fivefury.resource import parse_rsc7
        from fivefury.texture import BCFormat, Texture, total_mip_data_size
        from fivefury.ytd.model import Ytd

        width = 3072
        height = 2048
        mip_count = 1
        data = bytes(total_mip_data_size(width, height, BCFormat.BC1, mip_count))
        ytd = Ytd(
            textures=[
                Texture.from_raw(
                    data, width, height, BCFormat.BC1, mip_count, name="large_diffuse"
                )
            ],
            game="gta5",
        )
        built = ytd.to_bytes()
        header, payload = parse_rsc7(built)
        reread = read_ytd(built)
        assert len(reread.textures) == 1
        assert reread.textures[0].name == "large_diffuse"
        assert reread.textures[0].width == width
        assert reread.textures[0].height == height
        assert reread.textures[0].mip_count == mip_count
        assert header.graphics_flags & 15 > 0
        assert len(payload) <= header.system_size + header.graphics_size
        assert header.graphics_size >= len(data)

    def test_rpf_writer_supports_large_resource_entries(self) -> None:
        from fivefury.rpf import RpfArchive
        from fivefury.rpf.entries import RpfResourceFileEntry
        from fivefury.rpf.utils import RSC7_MAGIC

        stored_size = 16777216
        resource = struct.pack("<IIII", RSC7_MAGIC, 0, 0, 0) + bytes(stored_size - 16)
        archive = RpfArchive.empty("large_resources.rpf")
        archive.file("stream/large.ytd", resource)
        packed = archive.to_bytes()
        reread = RpfArchive.from_bytes(packed, name="large_resources.rpf")
        entry = reread.find_entry("stream/large.ytd")
        assert isinstance(entry, RpfResourceFileEntry)
        assert isinstance(entry, RpfResourceFileEntry)
        assert entry.file_size == stored_size
        raw = reread.read_entry_raw(entry)
        assert len(raw) == stored_size
        assert raw[7] << 0 | raw[14] << 8 | raw[5] << 16 | raw[2] << 24 == stored_size
        assert reread.read_entry_standalone(entry)[:4] == b"RSC7"

    def test_ytd_reader_can_export_dds(self) -> None:
        from fivefury import read_ytd

        ytd = read_ytd(_build_test_ytd_bytes(enhanced=False))
        texture = ytd.textures[0]
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test_diffuse.dds"
            texture.save_dds(output)
            assert output.exists()
            assert output.read_bytes()[:4] == b"DDS "

    def test_gamefilecache_parses_ytd_and_extracts_ytd_textures(self) -> None:
        from fivefury import GameFileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_bytes(
                root / "stream" / "test_dict.ytd", _build_test_ytd_bytes(enhanced=False)
            )
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            game_file = cache.get_file("stream/test_dict.ytd")
            assert game_file is not None
            assert type(game_file.parsed).__name__ == "Ytd"
            assert len(cache.list_ytd_textures("test_dict")) == 1
            extracted = cache.extract_ytd_textures("test_dict", root / "out")
            assert len(extracted) == 1
            assert extracted[0].suffix.lower() == ".dds"
            assert extracted[0].read_bytes()[:4] == b"DDS "

    def test_gamefilecache_extracts_asset_textures_via_archetype_texture_dictionary(
        self,
    ) -> None:
        from fivefury import Archetype, GameFileCache, Ytyp

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_bytes(root / "stream" / "prop_tree_pine_01.ydr", b"RSC7fake")
            write_bytes(
                root / "stream" / "test_dict.ytd", _build_test_ytd_bytes(enhanced=False)
            )
            ytyp = Ytyp(name="types.ytyp")
            ytyp.archetypes.append(
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
            extracted = cache.extract_asset_textures(
                "prop_tree_pine_01.ydr", root / "textures_out"
            )
            assert len(extracted) == 1
            assert extracted[0].name == "test_diffuse.dds"
            assert extracted[0].parent.name == "test_dict"
            assert extracted[0].read_bytes()[:4] == b"DDS "

    def test_gamefilecache_extracts_asset_textures_from_external_ymap_and_parent_txd_chain(
        self,
    ) -> None:
        from fivefury import (
            Archetype,
            Entity,
            GameFileCache,
            GameFileType,
            Gtxd,
            Ymap,
            Ytyp,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "game"
            root.mkdir(parents=True, exist_ok=True)
            write_bytes(root / "stream" / "prop_tree_pine_01.ydr", b"RSC7fake")
            write_bytes(
                root / "stream" / "child_dict.ytd",
                _build_test_ytd_bytes(enhanced=False),
            )
            write_bytes(
                root / "stream" / "parent_dict.ytd",
                _build_test_ytd_bytes(enhanced=True),
            )
            Gtxd.from_mapping({"child_dict": "parent_dict"}).save(
                root / "common" / "data" / "gtxd.meta"
            )
            ytyp = Ytyp(name="types.ytyp")
            ytyp.archetypes.append(
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
            ymap.entities.append(
                Entity(
                    archetype_name="prop_tree_pine_01",
                    position=Vector3(),
                    lod_dist=50.0,
                )
            )
            ymap.save(external / "external_map.ymap", auto_extents=True)
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            gtxd_file = cache.get_file("common/data/gtxd.meta")
            assert gtxd_file.kind == GameFileType.GTXD
            assert isinstance(gtxd_file.parsed, Gtxd)
            assert gtxd_file.parsed.parent_of("child_dict") == "parent_dict"
            dictionaries = cache.list_texture_dictionaries(
                external / "external_map.ymap"
            )
            assert {asset.stem for asset in dictionaries} == {
                "child_dict",
                "parent_dict",
            }
            texture_refs = cache.list_asset_textures(external / "external_map.ymap")
            assert {(ref.container_name, ref.parent_depth) for ref in texture_refs} == {
                ("child_dict", 0),
                ("parent_dict", 1),
            }
            extracted = cache.extract_asset_textures(
                external / "external_map.ymap", root / "textures_out"
            )
            assert len(extracted) == 2
            assert {path.parent.name for path in extracted} == {
                "child_dict",
                "parent_dict",
            }
            assert all(path.read_bytes()[:4] == b"DDS " for path in extracted)

    def test_gtxd_roundtrip_and_parent_chain_helpers(self) -> None:
        from fivefury import create_gtxd, read_gtxd

        gtxd = create_gtxd(
            {"child_dict.ytd": "parent_dict.ytd"}, grandchild_dict="child_dict"
        )
        xml = gtxd.to_bytes()
        parsed = read_gtxd(xml)
        assert parsed.parent_of("child_dict") == "parent_dict"
        assert parsed.parent_of("grandchild_dict") == "child_dict"
        assert list(parsed.iter_chain("grandchild_dict")) == [
            "grandchild_dict",
            "child_dict",
            "parent_dict",
        ]
        assert b"<CMapParentTxds>" in xml

    def test_gamefilecache_extracts_embedded_textures_from_supported_resource_assets(
        self,
    ) -> None:
        from fivefury import GameFileCache

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_bytes(
                root / "stream" / "embedded.ydr",
                _build_embedded_texture_resource("ydr", enhanced=False),
            )
            write_bytes(
                root / "stream" / "embedded.ydd",
                _build_embedded_texture_resource("ydd", enhanced=False),
            )
            write_bytes(
                root / "stream" / "embedded.yft",
                _build_embedded_texture_resource("yft", enhanced=False),
            )
            write_bytes(
                root / "stream" / "embedded.ypt",
                _build_embedded_texture_resource("ypt", enhanced=False),
            )
            write_bytes(
                root / "stream" / "embedded_gen9.ypt",
                _build_embedded_texture_resource("ypt", enhanced=True),
            )
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
                assert len(refs) == 1, relative_path
                assert refs[0].origin == "embedded"
                extracted = cache.extract_asset_textures(
                    relative_path, root / "textures_out" / Path(relative_path).stem
                )
                assert len(extracted) == 1, relative_path
                assert extracted[0].name == "test_diffuse.dds"
                assert extracted[0].read_bytes()[:4] == b"DDS "

    def test_gamefilecache_extracts_embedded_textures_from_external_ymap_primary_assets(
        self,
    ) -> None:
        from fivefury import Archetype, Entity, GameFileCache, Ymap, Ytyp

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "game"
            root.mkdir(parents=True, exist_ok=True)
            write_bytes(
                root / "stream" / "embedded_tree.ydr",
                _build_embedded_texture_resource("ydr", enhanced=False),
            )
            ytyp = Ytyp(name="types.ytyp")
            ytyp.archetypes.append(
                Archetype(
                    name="embedded_tree", asset_name="embedded_tree", asset_type=2
                )
            )
            ytyp.save(root / "stream" / "types.ytyp")
            external = Path(tmpdir) / "external"
            external.mkdir(parents=True, exist_ok=True)
            ymap = Ymap(name="external_map.ymap")
            ymap.entities.append(
                Entity(
                    archetype_name="embedded_tree", position=Vector3(), lod_dist=50.0
                )
            )
            ymap.save(external / "external_map.ymap", auto_extents=True)
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            refs = cache.list_asset_textures(external / "external_map.ymap")
            assert len(refs) == 1
            assert refs[0].origin == "embedded"
            extracted = cache.extract_asset_textures(
                external / "external_map.ymap", root / "textures_out"
            )
            assert len(extracted) == 1
            assert extracted[0].name == "test_diffuse.dds"
            assert extracted[0].read_bytes()[:4] == b"DDS "

    def test_open_resource_texture_asset_returns_typed_classes(self) -> None:
        from fivefury import (
            YddAsset,
            YdrAsset,
            YftAsset,
            YptAsset,
            open_resource_texture_asset,
        )

        for kind, asset_type in (
            ("ydr", YdrAsset),
            ("ydd", YddAsset),
            ("yft", YftAsset),
            ("ypt", YptAsset),
        ):
            asset = open_resource_texture_asset(
                _build_embedded_texture_resource(kind, enhanced=False), kind=f".{kind}"
            )
            assert asset is not None
            assert isinstance(asset, asset_type)
            dictionaries = asset.list_embedded_texture_dictionaries()
            assert len(dictionaries) == 1
            assert dictionaries[0].ytd.textures[0].name == "test_diffuse"

    def test_gamefilecache_opens_typed_resource_texture_assets(self) -> None:
        from fivefury import GameFileCache, YftAsset

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_bytes(
                root / "stream" / "embedded.yft",
                _build_embedded_texture_resource("yft", enhanced=False),
            )
            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False)
            asset = cache.get_resource_asset("stream/embedded.yft")
            assert asset is not None
            assert isinstance(asset, YftAsset)
            dictionaries = asset.list_embedded_texture_dictionaries()
            assert len(dictionaries) == 1
            assert dictionaries[0].ytd.textures[0].name == "test_diffuse"

    def test_resource_asset_modules_export_individual_format_classes(self) -> None:
        from fivefury.assets.ydd import YddAsset
        from fivefury.assets.ydr import YdrAsset
        from fivefury.assets.yft import YftAsset
        from fivefury.assets.ypt import YptAsset

        assert YdrAsset.kind.name == "YDR"
        assert YddAsset.kind.name == "YDD"
        assert YftAsset.kind.name == "YFT"
        assert YptAsset.kind.name == "YPT"
