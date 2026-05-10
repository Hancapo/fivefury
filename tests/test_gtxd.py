from __future__ import annotations

import struct
from pathlib import Path
from tempfile import TemporaryDirectory

from fivefury.cache import GameFileCache
from fivefury.common import hash_value
from fivefury.gamefile import GameFileType, guess_game_file_type
from fivefury.gtxd import read_gtxd
from fivefury.meta import Meta
from fivefury.ymt import Ymt, YmtContentType, YmtFormat, YmtScenarioPointManifest, read_ymt
from fivefury.pso import (
    PsoHashedString,
    PsoNode,
    PsoBlockBuilder,
    PsoStruct,
    build_chks_section,
    build_pmap_section,
    build_psin_section,
    finalize_sections_with_checksum,
    serialize_psch,
)

C_SCENARIO_POINT_MANIFEST = 1425675487
C_SCENARIO_POINT_REGION = 1492970064
C_PED_VARIATION_INFO = 376833625
C_PED_MODEL_INFO_INIT_DATA_LIST = 3715594014
C_STREAMING_REQUEST_RECORD = 135915278


def _rbf_open(index: int, data_type: int, name: str | None = None) -> bytes:
    payload = bytes([index, data_type])
    if name is not None:
        encoded = name.encode("ascii")
        payload += struct.pack("<h", len(encoded)) + encoded
    return payload + b"\0\0\0\0\0\0"


def _rbf_bytes(value: str) -> bytes:
    encoded = value.encode("ascii") + b"\0"
    return b"\xFD\xFF" + struct.pack("<i", len(encoded)) + encoded


def _rbf_close() -> bytes:
    return b"\xFF\xFF"


def _gtxd_rbf_sample() -> bytes:
    return b"".join(
        [
            b"RBF0",
            _rbf_open(0, 0, "CMapParentTxds"),
            _rbf_open(1, 0, "txdRelationships"),
            _rbf_open(2, 0, "item"),
            _rbf_open(3, 0, "parent"),
            _rbf_bytes("shared_parent"),
            _rbf_close(),
            _rbf_open(4, 0, "child"),
            _rbf_bytes("child_a"),
            _rbf_close(),
            _rbf_close(),
            _rbf_open(2, 0),
            _rbf_open(3, 0),
            _rbf_bytes("shared_parent"),
            _rbf_close(),
            _rbf_open(4, 0),
            _rbf_bytes("child_b"),
            _rbf_close(),
            _rbf_close(),
            _rbf_close(),
            _rbf_close(),
        ]
    )


def _scenario_manifest_pso_sample() -> bytes:
    blocks = [PsoBlockBuilder(name_hash=C_SCENARIO_POINT_MANIFEST)]
    return finalize_sections_with_checksum(
        [
            build_psin_section(blocks),
            build_pmap_section(blocks, root_block_id=1),
            serialize_psch({C_SCENARIO_POINT_MANIFEST: PsoStruct(name_hash=C_SCENARIO_POINT_MANIFEST, length=0, entries=[])}),
            build_chks_section(),
        ]
    )


def test_read_gtxd_rbf_ymt_parent_relationships() -> None:
    gtxd = read_gtxd(_gtxd_rbf_sample())

    assert gtxd.source == "rbf"
    assert gtxd.to_name_parent_map() == {
        "child_a": "shared_parent",
        "child_b": "shared_parent",
    }
    assert list(gtxd.iter_chain("child_a")) == ["child_a", "shared_parent"]


def test_gtxd_ymt_is_detected_as_ymt() -> None:
    assert guess_game_file_type("common/data/gtxd.ymt") is GameFileType.YMT


def test_read_ymt_exposes_gtxd_rbf_content() -> None:
    sample = _gtxd_rbf_sample()
    ymt = read_ymt(sample)

    assert ymt.format is YmtFormat.RBF
    assert ymt.content_type is YmtContentType.MAP_PARENT_TXDS
    assert ymt.rbf is not None
    assert ymt.gtxd is not None
    assert ymt.gtxd.parent_of("child_b") == "shared_parent"
    assert ymt.to_bytes() == sample


def test_read_ymt_exposes_scenario_manifest_pso_content() -> None:
    sample = _scenario_manifest_pso_sample()
    ymt = read_ymt(sample)

    assert ymt.format is YmtFormat.PSO
    assert ymt.content_type is YmtContentType.SCENARIO_POINT_MANIFEST
    assert ymt.pso is not None
    assert ymt.scenario_point_manifest is ymt.pso.root
    assert ymt.scenario_manifest is not None
    assert ymt.scenario_manifest.version_number == 0
    assert ymt.pso.root.type_name == "CScenarioPointManifest"
    assert ymt.to_bytes() == sample


def test_ymt_scenario_manifest_exposes_semantic_lists() -> None:
    node = PsoNode(
        type_name="CScenarioPointManifest",
        type_hash=C_SCENARIO_POINT_MANIFEST,
        fields={
            "VersionNumber": 3,
            "RegionDefs": [
                PsoNode(
                    type_name="CScenarioPointRegionDef",
                    fields={
                        "Name": PsoHashedString(hash=0x11111111),
                        "AABB": PsoNode(type_name="rage__spdAABB", fields={"min": (1.0, 2.0, 3.0, 0.0), "max": (4.0, 5.0, 6.0, 0.0)}),
                    },
                )
            ],
            "Groups": [PsoNode(type_name="CScenarioPointGroup", fields={"Name": PsoHashedString(hash=0x22222222), "EnabledByDefault": True})],
            "InteriorNames": [PsoHashedString(hash=0x33333333)],
        },
    )

    manifest = YmtScenarioPointManifest.from_pso_node(node)

    assert manifest.version_number == 3
    assert int(manifest.region_defs[0].name) == 0x11111111
    assert manifest.region_defs[0].aabb.bounds == ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
    assert int(manifest.groups[0].name) == 0x22222222
    assert manifest.groups[0].enabled_by_default is True
    assert int(manifest.interior_names[0]) == 0x33333333


def test_ymt_from_meta_exposes_scenario_region_content() -> None:
    ymt = Ymt.from_meta(Meta(Name="scenario_region", root_name_hash=C_SCENARIO_POINT_REGION, root_value={"points": []}))

    assert ymt.format is YmtFormat.RSC
    assert ymt.content_type is YmtContentType.SCENARIO_POINT_REGION
    assert ymt.scenario_point_region == {"points": []}


def test_ymt_from_meta_marks_ped_variation_root() -> None:
    root = {"availComp": []}
    ymt = Ymt.from_meta(Meta(Name="mp_f_freemode_01", root_name_hash=C_PED_VARIATION_INFO, root_value=root))

    assert ymt.content_type is YmtContentType.PED_VARIATION
    assert ymt.ped_variation is root
    assert ymt.root_type_name == "CPedVariationInfo"


def test_ymt_from_meta_exposes_streaming_request_record() -> None:
    root = {
        "Frames": [
            {
                "AddList": [0x11111111],
                "RemoveList": [0x22222222],
                "PromoteToHDList": [0x33333333],
                "CamPos": (1.0, 2.0, 3.0),
                "CamDir": (0.0, 1.0, 0.0),
                "CommonAddSets": [0, 2],
                "Flags": 7,
            }
        ],
        "CommonSets": [{"Requests": [0x44444444, 0x11111111]}],
        "NewStyle": True,
    }
    ymt = Ymt.from_meta(Meta(Name="example_srl", root_name_hash=C_STREAMING_REQUEST_RECORD, root_value=root))

    assert ymt.content_type is YmtContentType.STREAMING_REQUEST_RECORD
    assert ymt.root_type_name == "CStreamingRequestRecord"
    assert ymt.streaming_request_record is not None
    assert ymt.streaming_request_record.frame_count == 1
    assert ymt.streaming_request_record.new_style is True
    assert ymt.streaming_request_record.frames[0].camera_position == (1.0, 2.0, 3.0)
    assert ymt.streaming_request_record.frames[0].common_add_sets == [0, 2]
    assert [int(item) for item in ymt.streaming_request_record.iter_requested_hashes()] == [0x11111111, 0x33333333, 0x44444444]


def test_ymt_from_meta_exposes_ped_metadata() -> None:
    root = {
        "residentTxd": "ped_txd",
        "residentAnims": ["anim_group"],
        "InitDatas": [
            {
                "Name": "a_m_m_bevhills_01",
                "PropsName": "a_m_m_bevhills_01_p",
                "ClipDictionaryName": "move_m@generic",
                "ExpressionSetName": "expr_set_ambient_male",
                "Pedtype": "civmale",
                "MovementClipSet": "move_m@generic",
                "PedComponentSetName": "ped_component_set",
                "PedComponentClothName": "ped_cloth_set",
                "PedIKSettingsName": "ped_ik",
            }
        ],
        "txdRelationships": [{"parent": "ped_parent", "child": "ped_child"}],
        "multiTxdRelationships": [{"parent": "ped_parent", "children": ["ped_child_a", "ped_child_b"]}],
    }
    ymt = Ymt.from_meta(Meta(Name="peds", root_name_hash=C_PED_MODEL_INFO_INIT_DATA_LIST, root_value=root))

    assert ymt.content_type is YmtContentType.PED_METADATA
    assert ymt.root_type_name == "CPedModelInfo__InitDataList"
    assert ymt.ped_metadata is not None
    assert ymt.ped_metadata.resident_txd == "ped_txd"
    assert [str(item) for item in ymt.ped_metadata.ped_names] == ["a_m_m_bevhills_01"]
    assert ymt.ped_metadata.txd_relationships[0].child == "ped_child"
    assert ymt.ped_metadata.multi_txd_relationships == {"ped_parent": ["ped_child_a", "ped_child_b"]}


def test_texture_parent_dict_reads_gtxd_ymt_as_ymt() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "common" / "data" / "gtxd.ymt"
        path.parent.mkdir(parents=True)
        path.write_bytes(_gtxd_rbf_sample())

        cache = GameFileCache(root=root)
        cache._register_asset(
            path="common/data/gtxd.ymt",
            kind=GameFileType.YMT,
            size=path.stat().st_size,
            uncompressed_size=path.stat().st_size,
            loose_path=path,
        )

        assert cache.texture_parent_dict.get(hash_value("child_a")) == hash_value("shared_parent")
