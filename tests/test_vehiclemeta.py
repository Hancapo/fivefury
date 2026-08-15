from __future__ import annotations

import os
from pathlib import Path

import pytest

from fivefury.cache import GameFileCache
from fivefury.cut import CutVehicleVariationPayload
from fivefury.game_target import GameTarget
from fivefury.gamefile import GameFileType, guess_game_file_type
from fivefury.hashing import jenk_hash
from fivefury.pso import (
    PsoBlockBuilder,
    PsoHashedString,
    PsoNode,
    PsoStruct,
    build_chks_section,
    build_pmap_section,
    build_psin_section,
    finalize_sections_with_checksum,
    serialize_psch,
)
from fivefury.vehiclemeta import (
    CarHandlingData,
    HandlingDataManager,
    VehicleAppearanceSourceTier,
    VehicleCarCols,
    VehicleClass,
    VehicleInitDataList,
    VehicleMetaContentType,
    VehicleMetaFormat,
    VehicleModelInfoVariation,
    VehicleType,
    read_vehicle_meta,
)
from fivefury.vehiclemeta.resource import (
    YMT_C_VEHICLE_MODEL_INFO_VAR_GLOBAL,
    YMT_C_VEHICLE_MODEL_INFO_VARIATION,
)


def _empty_vehicle_meta_pso(root_name: str) -> bytes:
    return _empty_vehicle_meta_pso_hash(jenk_hash(root_name))


def _empty_vehicle_meta_pso_hash(root_hash: int) -> bytes:
    blocks = [PsoBlockBuilder(name_hash=root_hash)]
    return finalize_sections_with_checksum(
        [
            build_psin_section(blocks),
            build_pmap_section(blocks, root_block_id=1),
            serialize_psch(
                {root_hash: PsoStruct(name_hash=root_hash, length=0, entries=[])}
            ),
            build_chks_section(),
        ]
    )


def test_vehicle_meta_names_are_classified() -> None:
    assert guess_game_file_type("common/data/vehicles.meta") is GameFileType.VEHICLES
    assert guess_game_file_type("common/data/handling.meta") is GameFileType.HANDLING
    assert guess_game_file_type("common/data/carcols.meta") is GameFileType.CAR_COLS
    assert (
        guess_game_file_type("common/data/carmodcols.meta") is GameFileType.CAR_MOD_COLS
    )
    assert (
        guess_game_file_type("common/data/carvariations.meta")
        is GameFileType.CAR_VARIATIONS
    )
    assert guess_game_file_type("common/data/carcols.ymt") is GameFileType.CAR_COLS
    assert (
        guess_game_file_type("common/data/carvariations.ymt")
        is GameFileType.CAR_VARIATIONS
    )


def test_read_vehicle_meta_dispatches_pso_root() -> None:
    sample = _empty_vehicle_meta_pso("CVehicleModelInfo::InitDataList")
    resource = read_vehicle_meta(sample, source="vehicles.meta")

    assert resource.format is VehicleMetaFormat.PSO
    assert resource.content_type is VehicleMetaContentType.VEHICLES
    assert isinstance(resource.vehicles, VehicleInitDataList)
    assert resource.to_bytes() == sample


@pytest.mark.parametrize(
    ("root_hash", "source", "content_type"),
    [
        (
            YMT_C_VEHICLE_MODEL_INFO_VARIATION,
            "carvariations.ymt",
            VehicleMetaContentType.CAR_VARIATIONS,
        ),
        (
            YMT_C_VEHICLE_MODEL_INFO_VAR_GLOBAL,
            "carcols.ymt",
            VehicleMetaContentType.CAR_COLS,
        ),
    ],
)
def test_read_vehicle_meta_dispatches_binary_ymt_roots(
    root_hash: int,
    source: str,
    content_type: VehicleMetaContentType,
) -> None:
    resource = read_vehicle_meta(
        _empty_vehicle_meta_pso_hash(root_hash),
        source=source,
    )

    assert resource.format is VehicleMetaFormat.PSO
    assert resource.content_type is content_type


def test_game_file_cache_loads_vehicle_meta_model(tmp_path) -> None:
    path = tmp_path / "vehicles.meta"
    path.write_bytes(_empty_vehicle_meta_pso("CVehicleModelInfo::InitDataList"))
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)

    game_file = cache.get_file("vehicles.meta")

    assert game_file is not None
    assert game_file.kind is GameFileType.VEHICLES
    assert game_file.parsed.content_type is VehicleMetaContentType.VEHICLES
    assert isinstance(game_file.parsed.vehicles, VehicleInitDataList)


def test_vehicle_init_data_maps_core_fields_and_enums() -> None:
    root = PsoNode(
        type_name="CVehicleModelInfo::InitDataList",
        fields={
            "m_residentTxd": "vehshare",
            "m_InitDatas": [
                PsoNode(
                    type_name="CVehicleModelInfo::InitData",
                    fields={
                        "m_modelName": "adder",
                        "m_txdName": "adder",
                        "m_handlingId": "ADDER",
                        "m_layout": PsoHashedString(hash=jenk_hash("LAYOUT_STANDARD")),
                        "m_type": VehicleType.CAR,
                        "m_vehicleClass": VehicleClass.SUPER,
                        "m_lodDistances": [15.0, 30.0, 60.0, 120.0, 250.0, 500.0],
                    },
                )
            ],
        },
    )

    vehicles = VehicleInitDataList.from_value(root)

    assert vehicles.resident_txd == "vehshare"
    assert vehicles.vehicles[0].model_name == "adder"
    assert vehicles.vehicles[0].handling_id == "ADDER"
    assert vehicles.vehicles[0].vehicle_type is VehicleType.CAR
    assert vehicles.vehicles[0].vehicle_class is VehicleClass.SUPER
    assert vehicles.vehicles[0].lod_distances[-1] == 500.0
    assert vehicles.get("ADDER") is vehicles.vehicles[0]


def test_vehicle_models_resolve_unregistered_pso_field_hashes() -> None:
    model_key = f"hash_{jenk_hash('m_modelName'):08X}"
    txd_key = f"hash_{jenk_hash('m_txdName'):08X}"
    vehicle = VehicleInitDataList.from_value(
        {
            "m_InitDatas": [
                {
                    model_key: "adder",
                    txd_key: "vehshare",
                }
            ]
        }
    ).vehicles[0]

    assert vehicle.model_name == "adder"
    assert vehicle.txd_name == "vehshare"


def test_handling_maps_sub_handling_types() -> None:
    root = PsoNode(
        type_name="CHandlingDataMgr",
        fields={
            "m_HandlingData": [
                PsoNode(
                    type_name="CHandlingData",
                    fields={
                        "m_handlingName": PsoHashedString(hash=jenk_hash("ADDER")),
                        "m_fMass": 1800.0,
                        "m_vecCentreOfMassOffset": (0.0, 0.0, -0.1),
                        "m_SubHandlingData": [
                            PsoNode(
                                type_name="CCarHandlingData",
                                fields={"m_fCamberFront": -0.02},
                            )
                        ],
                    },
                )
            ]
        },
    )

    handling = HandlingDataManager.from_value(root)

    assert handling.entries[0].mass == 1800.0
    assert handling.entries[0].center_of_mass_offset == (0.0, 0.0, -0.1)
    assert isinstance(handling.entries[0].sub_handling[0], CarHandlingData)
    assert handling.entries[0].sub_handling[0].values["m_fCamberFront"] == -0.02


def test_car_variations_map_by_model_name() -> None:
    root = {
        "m_variationData": [
            {
                "m_modelName": "adder",
                "m_colors": [
                    {"m_indices": [0, 1, 2, 3, 4, 5], "m_liveries": [True, False]}
                ],
                "m_kits": [PsoHashedString(hash=jenk_hash("0_default_modkit"))],
                "m_lightSettings": 4,
                "m_sirenSettings": 0xFF,
            }
        ]
    }

    variations = VehicleModelInfoVariation.from_value(root)

    assert variations.get("ADDER") is variations.vehicles[0]
    assert variations.vehicles[0].colors[0].indices == [0, 1, 2, 3, 4, 5]
    assert variations.vehicles[0].light_settings == 4


def test_carcols_maps_nested_lights_kits_and_sirens() -> None:
    root = {
        "m_Lights": [
            {
                "id": 3,
                "name": "xenon",
                "headLight": {
                    "intensity": 2.5,
                    "textureName": PsoHashedString(hash=0x1234),
                },
                "headLightCorona": {"size": 1.5, "numCoronas": 2},
            }
        ],
        "m_Sirens": [
            {
                "id": 7,
                "name": "police",
                "sequencerBpm": 120,
                "sirens": [{"intensity": 3.0, "castShadows": True}],
            }
        ],
        "m_Kits": [
            {
                "m_kitName": PsoHashedString(hash=jenk_hash("0_default_modkit")),
                "m_id": 17,
                "m_visibleMods": [
                    {
                        "m_modelName": PsoHashedString(
                            hash=jenk_hash("adder_spoiler_1")
                        ),
                        "m_type": 0,
                        "m_cameraPos": 1,
                    }
                ],
            }
        ],
    }

    carcols = VehicleCarCols.from_value(root)

    assert carcols.lights[0].head_light is not None
    assert carcols.lights[0].head_light.intensity == 2.5
    assert carcols.lights[0].head_light_corona is not None
    assert carcols.lights[0].head_light_corona.count == 2
    assert carcols.sirens[0].sequencer_bpm == 120
    assert carcols.sirens[0].sirens[0].cast_shadows is True
    assert carcols.kits[0].id == 17
    assert carcols.kits[0].visible_mods[0].camera_position.value == 1


def test_vehicle_meta_reads_xml_char_arrays() -> None:
    resource = read_vehicle_meta(
        b"""<?xml version="1.0"?>
<CVehicleModelInfoVariation>
  <variationData><Item>
    <modelName>testcar</modelName>
    <colors><Item>
      <indices content="char_array">0 41 3 156 8 9</indices>
      <liveries><Item value="true"/><Item value="false"/></liveries>
    </Item></colors>
  </Item></variationData>
</CVehicleModelInfoVariation>""",
        source="vehicles.meta",
    )

    assert resource.format is VehicleMetaFormat.XML
    assert resource.variations is not None
    entry = resource.variations.get("TESTCAR")
    assert entry is not None
    assert entry.colors[0].indices == [0, 41, 3, 156, 8, 9]
    assert entry.colors[0].liveries == [True, False]


def _write_vehicle_appearance_metadata(root, variation_indices: list[int]) -> None:
    data = root / "common" / "data"
    data.mkdir(parents=True, exist_ok=True)
    colors = "".join(
        f'<Item><color value="{0xFF000000 | (index << 16) | (index << 8) | index}"/>'
        f'<metallicID value="{index}"/><colorName>COLOR_{index}</colorName></Item>'
        for index in range(6)
    )
    data.joinpath("carcols.meta").write_text(
        f"<CVehicleModelInfoVarGlobal><Colors>{colors}</Colors></CVehicleModelInfoVarGlobal>",
        encoding="utf-8",
    )
    indices = " ".join(str(value) for value in variation_indices)
    data.joinpath("carvariations.meta").write_text(
        "<CVehicleModelInfoVariation><variationData><Item>"
        "<modelName>testcar</modelName><colors><Item>"
        f'<indices content="char_array">{indices}</indices><liveries/>'
        "</Item></colors></Item></variationData></CVehicleModelInfoVariation>",
        encoding="utf-8",
    )


def test_vehicle_appearance_merges_precedence_and_cut_override(tmp_path) -> None:
    _write_vehicle_appearance_metadata(tmp_path, [0, 1, 2, 3, 4, 5])
    _write_vehicle_appearance_metadata(tmp_path / "mods", [5, 4, 3, 2, 1, 0])
    cache = GameFileCache(
        tmp_path,
        game=GameTarget.GTA5_ENHANCED,
        use_index_cache=False,
    )
    cache.scan(use_index_cache=False)

    default = cache.resolve_vehicle_appearance("testcar")
    assert default.primary_index == 5
    assert default.secondary_index == 4
    assert default.body_6_index == 0
    assert default.primary is not None
    assert default.primary.srgb == (5, 5, 5, 255)
    assert default.sources[0].tier is VehicleAppearanceSourceTier.MODS

    explicit = cache.resolve_vehicle_appearance(
        "testcar",
        variation=CutVehicleVariationPayload(
            object_id=7,
            main_body_colour=1,
            second_body_colour=2,
            specular_colour=3,
            wheel_trim_colour=4,
            body_colour_5=5,
            livery=6,
            livery_2=7,
            dirt_level=0.25,
        ),
    )
    assert explicit.primary_index == 1
    assert explicit.secondary_index == 2
    assert explicit.specular_index == 3
    assert explicit.wheel_trim_index == 4
    assert explicit.body_5_index == 5
    assert explicit.body_6_index == 0
    assert explicit.livery_index == 6
    assert explicit.secondary_livery_index == 7
    assert explicit.dirt_level == 0.25


def test_vehicle_appearance_dlc_overrides_base(tmp_path) -> None:
    _write_vehicle_appearance_metadata(tmp_path, [0, 1, 2, 3, 4, 5])
    _write_vehicle_appearance_metadata(
        tmp_path / "update" / "x64" / "dlcpacks" / "testdlc",
        [4, 3, 2, 1, 0, 5],
    )
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)

    appearance = cache.resolve_vehicle_appearance("testcar")

    assert appearance.primary_index == 4
    assert appearance.sources[0].tier is VehicleAppearanceSourceTier.DLC


def test_vehicle_appearance_reports_missing_and_invalid_references(tmp_path) -> None:
    _write_vehicle_appearance_metadata(tmp_path, [99, 1, 2, 3, 4, 5])
    cache = GameFileCache(tmp_path, game=GameTarget.GTA5, use_index_cache=False)
    cache.scan(use_index_cache=False)

    invalid = cache.resolve_vehicle_appearance("testcar")
    missing = cache.resolve_vehicle_appearance("absentcar")

    assert invalid.primary is None
    assert any(
        issue.code == "vehicle.appearance.color_index_invalid"
        for issue in invalid.diagnostics
    )
    assert any(
        issue.code == "vehicle.appearance.variation_missing"
        for issue in missing.diagnostics
    )


@pytest.mark.skipif(
    not os.environ.get("FIVEFURY_GTA5_ENHANCED_PATH"),
    reason="set FIVEFURY_GTA5_ENHANCED_PATH to run the retail CUT regression",
)
def test_enhanced_pro_mcs_5_resolves_vehicle_appearances() -> None:
    root = Path(os.environ["FIVEFURY_GTA5_ENHANCED_PATH"])
    cache = GameFileCache(root, game=GameTarget.GTA5_ENHANCED, load_audio=False)
    cache.scan_game()
    source = cache.find_assets("pro_mcs_5", kind=GameFileType.CUT)[0]

    bundle = cache.resolve_cutscene(source)
    vehicles = {
        binding.vehicle_appearance.model_name.casefold(): binding.vehicle_appearance
        for binding in bundle.bindings.values()
        if binding.binding.role == "vehicle" and binding.vehicle_appearance is not None
    }

    assert vehicles["rancherxl"].primary_index == 0
    assert vehicles["policeold2"].primary_index == 132
    assert not vehicles["rancherxl"].diagnostics
    assert not vehicles["policeold2"].diagnostics
