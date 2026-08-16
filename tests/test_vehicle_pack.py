from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import (
    DlcDataFileType,
    GameTarget,
    HandlingData,
    HandlingDataManager,
    MetaHash,
    RpfArchive,
    Texture,
    TextureFormat,
    VehicleCarCols,
    VehicleInitData,
    VehicleInitDataList,
    VehicleModelInfoVariation,
    VehiclePackBuilder,
    VehicleVariation,
    YdrMaterialInput,
    YdrMeshInput,
    Ytd,
    create_ydr,
    create_yft,
    infer_dlc_content_from_folder,
    read_dlc_pack,
    read_vehicle_meta,
    read_yft,
    read_ytd,
)
from fivefury.authoring import ValidationError
from fivefury.vehiclemeta import VehicleColorIndices


def _fragment(name: str):
    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                indices=[0, 1, 2],
                material="body",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="body")],
        name=name,
    )
    return create_yft(drawable, name=name, version=171)


def _textures(name: str) -> Ytd:
    texture = Texture.from_raw(
        bytes(8),
        4,
        4,
        TextureFormat.BC1,
        1,
        name=f"{name}_diff",
    )
    return Ytd([texture], game=GameTarget.GTA5_ENHANCED)


def _builder(*, game: GameTarget = GameTarget.GTA5_ENHANCED) -> VehiclePackBuilder:
    vehicles = VehicleInitDataList(
        vehicles=[
            VehicleInitData(
                model_name="testcar",
                txd_name="testcar",
                handling_id="TESTCAR",
                game_name="TESTCAR",
            )
        ]
    )
    handling = HandlingDataManager(
        entries=[HandlingData(name=MetaHash("TESTCAR"), mass=1500.0)]
    )
    variations = VehicleModelInfoVariation(
        vehicles=[
            VehicleVariation(
                model_name="testcar",
                colors=[VehicleColorIndices(indices=[0, 0, 0, 0, 0, 0])],
            )
        ]
    )
    carcols = VehicleCarCols()
    carcols.ensure_color(10, 20, 30, name="TEST_COLOR")
    builder = VehiclePackBuilder(
        "testpack",
        vehicles,
        handling,
        variations,
        carcols,
        game=game,
    )
    builder.vehicle("testcar", _fragment("testcar"), textures=_textures("testcar"))
    return builder


def test_vehicle_pack_roundtrips_enhanced_metadata_and_streamed_assets(
    tmp_path,
) -> None:
    builder = _builder()
    builder.unregistered_files["common/data/_manifest.ymf"] = b"manifest"

    output = builder.save(tmp_path / "output")

    assert output.report.valid
    assert output.paths.dlc_rpf == tmp_path / "output" / "testpack" / "dlc.rpf"
    pack = read_dlc_pack(
        output.paths.dlc_rpf,
        game=GameTarget.GTA5_ENHANCED,
        load_files=True,
    )
    registrations = {
        Path(item.filename).name: str(item.file_type)
        for item in pack.content.data_files
    }
    assert registrations == {
        "vehicles.meta": DlcDataFileType.VEHICLE_METADATA,
        "handling.meta": DlcDataFileType.HANDLING,
        "carvariations.meta": DlcDataFileType.VEHICLE_VARIATION,
        "carcols.meta": DlcDataFileType.CARCOLS,
        "vehicles.rpf": DlcDataFileType.RPF,
    }
    assert not any("_manifest.ymf" in item.filename for item in pack.content.data_files)

    archive = RpfArchive.from_path(output.paths.dlc_rpf, load_nested=True)
    try:
        for path in (
            output.paths.vehicles_meta,
            output.paths.handling_meta,
            output.paths.variations_meta,
            output.paths.carcols_meta,
        ):
            entry = archive.find_entry(path)
            assert entry is not None
            assert read_vehicle_meta(entry.read()).validate().valid

        yft_entry = archive.find_entry(output.paths.streamed_rpf / "testcar.yft")
        ytd_entry = archive.find_entry(output.paths.streamed_rpf / "testcar.ytd")
        assert yft_entry is not None and yft_entry._archive is not None
        assert ytd_entry is not None and ytd_entry._archive is not None
        assert (
            read_yft(yft_entry._archive.read_entry_standalone(yft_entry)).version == 171
        )
        assert (
            read_ytd(ytd_entry._archive.read_entry_standalone(ytd_entry)).game
            == GameTarget.GTA5_ENHANCED
        )
    finally:
        archive.close()


def test_vehicle_pack_rejects_wrong_target_without_replacing_destination(
    tmp_path,
) -> None:
    builder = _builder(game=GameTarget.GTA5)
    destination = tmp_path / "dlc.rpf"
    destination.write_bytes(b"existing")

    with pytest.raises(ValidationError, match="vehicle.pack.game.invalid"):
        builder.save(destination)

    assert destination.read_bytes() == b"existing"


def test_vehicle_pack_reports_cross_file_and_stream_mismatches() -> None:
    builder = _builder()
    builder.handling_meta.entries.clear()
    builder.vehicles[0].texture_name = "different_txd"

    codes = {issue.code for issue in builder.validate()}

    assert "vehicle.handling.unresolved" in codes
    assert "vehicle.pack.metadata.txd_mismatch" in codes


def test_dlc_folder_inference_registers_vehicle_metadata(tmp_path) -> None:
    data = tmp_path / "common" / "data"
    data.mkdir(parents=True)
    for filename in (
        "vehicles.meta",
        "handling.meta",
        "carvariations.meta",
        "carcols.meta",
    ):
        (data / filename).write_bytes(b"fixture")

    content, _setup = infer_dlc_content_from_folder("cars", tmp_path)

    assert {item.file_type for item in content.data_files} == {
        DlcDataFileType.VEHICLE_METADATA,
        DlcDataFileType.HANDLING,
        DlcDataFileType.VEHICLE_VARIATION,
        DlcDataFileType.CARCOLS,
    }
