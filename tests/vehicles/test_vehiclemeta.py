from __future__ import annotations

import os
from pathlib import Path

import pytest

from fivefury.authoring import AssetSet, BuildContext
from fivefury.cache import GameFileCache
from fivefury.cut import CutTypeFileStrategy, CutVehicleVariationPayload
from fivefury.game_target import GameTarget
from fivefury.gamefile import GameFileType, guess_game_file_type
from fivefury.hashing import jenk_hash
from fivefury.metahash import MetaHash
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
    HandlingData,
    HandlingDataManager,
    HandlingFlagValue,
    VehicleAppearanceSourceTier,
    VehicleCarCols,
    VehicleClass,
    VehicleColorIndices,
    VehicleInitData,
    VehicleInitDataList,
    VehicleMetaContentType,
    VehicleMetaFormat,
    VehicleModelColor,
    VehicleModelInfoVariation,
    VehicleType,
    VehicleVariation,
    read_vehicle_meta,
    validate_vehicle_meta_xml,
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
    assert handling.entries[0].sub_handling[0].values["fCamberFront"] == -0.02


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


@pytest.mark.integration("FIVEFURY_GTA5_ENHANCED_PATH")
def test_enhanced_pro_mcs_5_resolves_vehicle_appearances() -> None:
    root = Path(os.environ["FIVEFURY_GTA5_ENHANCED_PATH"])
    cache = GameFileCache(root, game=GameTarget.GTA5_ENHANCED, load_audio=False)
    cache.scan_game()
    source = cache.find_assets("pro_mcs_5", kind=GameFileType.CUT)[0]

    bundle = cache.resolve_cutscene(source)
    assert bundle.scene.vehicles
    assert all(
        vehicle.type_file is None
        and vehicle.type_file_strategy is CutTypeFileStrategy.NONE
        for vehicle in bundle.scene.vehicles
    )
    assert {
        vehicle.fields["StreamingName"].hash for vehicle in bundle.scene.vehicles
    } == {jenk_hash("rancherxl"), jenk_hash("policeold2")}
    vehicles = {
        binding.vehicle_appearance.model_name.casefold(): binding.vehicle_appearance
        for binding in bundle.bindings.values()
        if binding.binding.role == "vehicle" and binding.vehicle_appearance is not None
    }

    assert vehicles["rancherxl"].primary_index == 0
    assert vehicles["policeold2"].primary_index == 132
    assert not vehicles["rancherxl"].diagnostics
    assert not vehicles["policeold2"].diagnostics


def _authored_vehicle_documents():
    vehicle = VehicleInitData(
        model_name="testcar",
        txd_name="testcar",
        handling_id="TESTCAR",
        game_name="TESTCAR",
        audio_name=MetaHash("ADDER_AUDIO"),
        layout=MetaHash("LAYOUT_STANDARD"),
        camera_name=MetaHash("DEFAULT_FOLLOW_VEHICLE_CAMERA"),
        vfx_info_name=MetaHash("VFXVEHICLEINFO_CAR_GENERIC"),
        lod_distances=[15.0, 30.0, 60.0, 120.0, 250.0, 500.0],
    )
    vehicles = VehicleInitDataList(resident_txd="vehshare", vehicles=[vehicle])
    handling = HandlingDataManager(
        entries=[
            HandlingData(
                name=MetaHash("TESTCAR"),
                mass=1600.0,
                center_of_mass_offset=(0.0, 0.0, -0.1),
                sub_handling=[CarHandlingData(values={"fCamberFront": -0.02})],
            )
        ]
    )
    variations = VehicleModelInfoVariation(
        vehicles=[
            VehicleVariation(
                model_name="testcar",
                colors=[VehicleColorIndices(indices=[0, 0, 0, 0, 0, 0])],
                kits=[MetaHash("0_default_modkit")],
            )
        ]
    )
    carcols = VehicleCarCols()
    assert carcols.ensure_color(12, 34, 56, name="TEST_BLUE") == 0
    return vehicles, handling, variations, carcols


def test_all_vehicle_metadata_roots_author_roundtrip_semantically() -> None:
    for document in _authored_vehicle_documents():
        encoded = document.to_bytes()
        reread = read_vehicle_meta(encoded)

        assert reread.content == document
        assert reread.to_bytes() == encoded


def test_handling_flag_tokens_use_retail_hexadecimal_dialect() -> None:
    source = b"""<?xml version="1.0" encoding="UTF-8"?>
<CHandlingDataMgr>
  <HandlingData>
    <Item type="CHandlingData">
      <handlingName>COMET5</handlingName>
      <fMass value="1600.000000" />
      <strModelFlags>440010</strModelFlags>
      <strHandlingFlags>0</strHandlingFlags>
      <strDamageFlags>80000001</strDamageFlags>
    </Item>
  </HandlingData>
</CHandlingDataMgr>
"""

    handling = read_vehicle_meta(source).handling

    assert handling is not None
    entry = handling.entries[0]
    assert entry.model_flags == HandlingFlagValue(0x00440010)
    assert entry.handling_flags == HandlingFlagValue(0)
    assert entry.damage_flags == HandlingFlagValue(0x80000001)


def test_handling_flag_authoring_canonicalizes_prefixed_hex_and_zero() -> None:
    handling = HandlingDataManager(
        entries=[
            HandlingData(
                name=MetaHash("TESTCAR"),
                mass=1600.0,
                model_flags=HandlingFlagValue("0x00440010"),
                handling_flags=HandlingFlagValue(0),
                damage_flags=HandlingFlagValue("0x80000001"),
            )
        ]
    )

    encoded = handling.to_bytes()
    reread = read_vehicle_meta(encoded).handling

    assert b"<strModelFlags>440010</strModelFlags>" in encoded
    assert b"<strHandlingFlags>0</strHandlingFlags>" in encoded
    assert b"<strDamageFlags>80000001</strDamageFlags>" in encoded
    assert reread == handling


def test_handling_flag_absence_is_distinct_from_explicit_zero() -> None:
    absent = HandlingData(name=MetaHash("ABSENT"), mass=1000.0)
    explicit = HandlingData(
        name=MetaHash("EXPLICIT"),
        mass=1000.0,
        model_flags=HandlingFlagValue(0),
        handling_flags=HandlingFlagValue(0),
        damage_flags=HandlingFlagValue(0),
    )

    encoded = HandlingDataManager(entries=[absent, explicit]).to_bytes()
    reread = read_vehicle_meta(encoded).handling

    assert reread is not None
    assert reread.entries[0].model_flags is None
    assert reread.entries[1].model_flags == HandlingFlagValue(0)
    assert encoded.count(b"<strModelFlags>0</strModelFlags>") == 1


def test_handling_flag_validation_is_typed_and_non_mutating() -> None:
    handling = HandlingData(
        name=MetaHash("INVALID"),
        mass=1000.0,
        model_flags=HandlingFlagValue(0x1_0000_0000),
        handling_flags=HandlingFlagValue("0xGG"),
        damage_flags=HandlingFlagValue("FLAG_SPECIAL"),
    )
    before = (
        handling.model_flags,
        handling.handling_flags,
        handling.damage_flags,
    )

    report = handling.validate()

    assert {issue.code for issue in report.errors} == {
        "vehicle.handling.flags.out_of_range",
        "vehicle.handling.flags.hex.malformed",
        "vehicle.handling.flags.symbolic.unsupported",
    }
    assert (
        handling.model_flags,
        handling.handling_flags,
        handling.damage_flags,
    ) == before


def test_handling_flag_xml_validation_reports_invalid_dialect_tokens() -> None:
    source = """<CHandlingDataMgr><HandlingData><Item type="CHandlingData">
<strModelFlags>0xGG</strModelFlags>
<strHandlingFlags>FLAG_SPECIAL</strHandlingFlags>
<strDamageFlags value="1" />
</Item></HandlingData></CHandlingDataMgr>"""

    handling = read_vehicle_meta(source.encode()).handling
    assert handling is not None
    report = handling.validate()
    xml_report = validate_vehicle_meta_xml(source)

    assert any(issue.code.endswith("hex.malformed") for issue in report.errors)
    assert any(issue.code.endswith("symbolic.unsupported") for issue in report.errors)
    assert any(
        issue.code.endswith("flags.shape.invalid") for issue in xml_report.errors
    )


@pytest.mark.integration("FIVEFURY_GTA5_ENHANCED_PATH")
def test_enhanced_comet5_handling_flags_survive_typed_clone_roundtrip() -> None:
    root = Path(os.environ["FIVEFURY_GTA5_ENHANCED_PATH"])
    with GameFileCache(
        root,
        game=GameTarget.GTA5_ENHANCED,
        load_audio=False,
    ) as cache:
        cache.scan_game()
        source = next(
            asset
            for asset in cache.find_assets(
                "handling.meta",
                kind=GameFileType.HANDLING,
            )
            if "mpchristmas2017" in asset.path.casefold()
        )
        game_file = cache.get_file(source)
        assert game_file is not None
        comet5 = game_file.parsed.handling.get("COMET5")

    assert comet5 is not None
    clone = comet5.clone_as("COMET5_COPY")
    encoded = HandlingDataManager(entries=[clone]).to_bytes()
    reread = read_vehicle_meta(encoded).handling

    assert reread is not None
    assert clone.model_flags == HandlingFlagValue(0x00440010)
    assert clone.handling_flags == HandlingFlagValue(0)
    assert clone.damage_flags == HandlingFlagValue(0)
    assert reread.entries[0] == clone


def test_vehicle_metadata_save_is_atomic_on_validation_error(tmp_path) -> None:
    duplicate = VehicleInitData(
        model_name="testcar",
        txd_name="testcar",
        handling_id="TESTCAR",
    )
    document = VehicleInitDataList(vehicles=[duplicate, duplicate])
    destination = tmp_path / "vehicles.meta"
    destination.write_bytes(b"existing")

    with pytest.raises(ValueError, match="vehicle.model_name.duplicate"):
        document.save(destination)

    assert destination.read_bytes() == b"existing"


def test_binary_vehicle_metadata_projection_is_explicitly_read_only(tmp_path) -> None:
    resource = read_vehicle_meta(
        _empty_vehicle_meta_pso("CVehicleModelInfo::InitDataList")
    )

    with pytest.raises(ValueError, match="read-only"):
        resource.save(tmp_path / "vehicles.meta")


def test_vehicle_cloning_replaces_identity_without_retaining_raw_source() -> None:
    donor = VehicleInitData(
        model_name="adder",
        txd_name="adder",
        handling_id="ADDER",
        audio_name=MetaHash("ADDER_AUDIO"),
        layout=MetaHash("LAYOUT_STANDARD"),
        camera_name=MetaHash("DEFAULT_FOLLOW_VEHICLE_CAMERA"),
        raw={"source": "donor"},
    )
    clone = donor.clone_as("testcar", handling_id="TESTCAR")
    handling = HandlingData(
        name=MetaHash("ADDER"), mass=1800.0, raw={"source": "donor"}
    ).clone_as("TESTCAR")
    variation = VehicleVariation(
        model_name="adder",
        colors=[VehicleColorIndices(indices=[0, 1, 2, 3, 4, 5])],
        raw={"source": "donor"},
    ).clone_as("testcar")

    assert clone.model_name == clone.txd_name == "testcar"
    assert clone.handling_id == "TESTCAR"
    assert clone.audio_name == donor.audio_name
    assert clone.layout == donor.layout
    assert clone.camera_name == donor.camera_name
    assert clone.raw is None
    assert handling.name == "TESTCAR" and handling.raw is None
    assert variation.model_name == "testcar" and variation.raw is None


def test_exact_vehicle_colors_allocate_deterministically() -> None:
    carcols = VehicleCarCols()

    first = carcols.ensure_color(1, 2, 3)
    repeated = carcols.ensure_color(1, 2, 3, name="IGNORED_DUPLICATE")
    second = carcols.ensure_color(4, 5, 6)

    assert (first, repeated, second) == (0, 0, 1)
    assert carcols.colors[0].rgb8 == (1, 2, 3)
    assert VehicleModelColor.from_rgb8(255, 128, 0).color == 0xFFFF8000


def test_vehicle_cross_file_validation_uses_build_context() -> None:
    vehicles, handling, variations, carcols = _authored_vehicle_documents()
    assets = AssetSet()
    assets["common/data/handling.meta"] = handling
    assets["common/data/carvariations.meta"] = variations
    assets["common/data/carcols.meta"] = carcols
    context = BuildContext(game=GameTarget.GTA5_ENHANCED, assets=assets)

    assert vehicles.validate(context=context).valid
    assert variations.validate(context=context).valid

    broken = VehicleInitDataList(
        vehicles=[
            VehicleInitData(
                model_name="missing",
                txd_name="missing",
                handling_id="MISSING",
            )
        ]
    )
    codes = {issue.code for issue in broken.validate(context=context)}
    assert "vehicle.handling.unresolved" in codes
    assert "vehicle.variation.unresolved" in codes
