from __future__ import annotations

from fivefury.cache import GameFileCache
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
    VehicleCarCols,
    VehicleClass,
    VehicleInitDataList,
    VehicleMetaContentType,
    VehicleMetaFormat,
    VehicleModelInfoVariation,
    VehicleType,
    read_vehicle_meta,
)


def _empty_vehicle_meta_pso(root_name: str) -> bytes:
    root_hash = jenk_hash(root_name)
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


def test_read_vehicle_meta_dispatches_pso_root() -> None:
    sample = _empty_vehicle_meta_pso("CVehicleModelInfo::InitDataList")
    resource = read_vehicle_meta(sample, source="vehicles.meta")

    assert resource.format is VehicleMetaFormat.PSO
    assert resource.content_type is VehicleMetaContentType.VEHICLES
    assert isinstance(resource.vehicles, VehicleInitDataList)
    assert resource.to_bytes() == sample


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
