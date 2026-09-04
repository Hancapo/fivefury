from __future__ import annotations

import dataclasses
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fivefury import (
    BoundBox,
    BoundChild,
    BoundComposite,
    DlcDataFileContents,
    DlcDataFileType,
    DlcSetupData,
    GameFileCache,
    GameFileType,
    GameTarget,
    HandlingData,
    HandlingDataManager,
    MetaHash,
    RpfArchive,
    Texture,
    TextureFormat,
    Vector2,
    Vector3,
    VehicleCarCols,
    VehicleInitData,
    VehicleInitDataList,
    VehicleModelInfoVariation,
    VehiclePackBuilder,
    VehicleVariation,
    YdrBone,
    YdrLod,
    YdrMaterialInput,
    YdrMeshInput,
    YdrSkeleton,
    YftFragmentDrawableBuild,
    YftFragmentDrawableName,
    YftPhysicsChild,
    YftPhysicsLod,
    YftVehicleGlassWindows,
    Ytd,
    build_yft_bytes,
    create_ydr,
    create_yft,
    infer_dlc_content_from_folder,
    read_dlc_pack,
    read_vehicle_meta,
    read_yft,
    read_ytd,
    validate_enhanced_vehicle_pack_layout,
    validate_vehicle_meta_xml,
    validate_vehicle_yft_pair,
)
from fivefury.authoring import ValidationError
from fivefury.vehiclemeta import VehicleColorIndices

_ENHANCED_ROOT_VALUE = os.environ.get("FIVEFURY_GTA5_ENHANCED_PATH")
_ENHANCED_ROOT = Path(_ENHANCED_ROOT_VALUE) if _ENHANCED_ROOT_VALUE else None


def _mesh() -> YdrMeshInput:
    return YdrMeshInput(
        positions=[Vector3(), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0)],
        indices=[0, 1, 2],
        material="body",
        texcoords=[[Vector2(), Vector2(1.0, 0.0), Vector2(0.0, 1.0)]],
    )


def _skinned_mesh(*, vertex_buffer_flags: int = 0x00580409) -> YdrMeshInput:
    return YdrMeshInput(
        positions=[Vector3(), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0)],
        indices=[0, 1, 2],
        material="body",
        texcoords=[[Vector2(), Vector2(1.0, 0.0), Vector2(0.0, 1.0)]],
        blend_weights=[
            (1.0, 0.0, 0.0, 0.0),
            (0.5, 0.5, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
        ],
        blend_indices=[(0, 0, 0, 0), (0, 1, 0, 0), (1, 0, 0, 0)],
        bone_ids=[0, 1],
        vertex_buffer_flags=vertex_buffer_flags,
    )


def _skinned_fragment(name: str, *, high_detail: bool = False):
    skeleton = YdrSkeleton()
    root = skeleton.bone("root", tag=0)
    skeleton.bone("child", parent=root, tag=1)
    drawable = create_ydr(
        meshes=[_skinned_mesh()],
        materials=[YdrMaterialInput(name="body")],
        skeleton=skeleton.build(),
        name=name,
        version=159,
    )
    if not high_detail:
        for lod in (YdrLod.MEDIUM, YdrLod.LOW, YdrLod.VERY_LOW):
            drawable.model([_skinned_mesh()], lod=lod)
    fragment = create_yft(drawable, name=name, version=171)
    fragment.tune_name = f"pack:/{name}"
    return fragment


def _vertex_buffer_flags(fragment) -> list[int]:
    return [int(mesh.vertex_buffer_flags) for mesh in fragment.iter_meshes()]


def _fragment(name: str, *, high_detail: bool = False):
    drawable = create_ydr(
        meshes=[_mesh()],
        materials=[YdrMaterialInput(name="body")],
        name=name,
    )
    if not high_detail:
        for lod in ("medium", "low", "very_low"):
            drawable.model([_mesh()], lod=lod)
    fragment = create_yft(drawable, name=name, version=171)
    fragment.tune_name = f"pack:/{name}"
    return fragment


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
        DlcSetupData.compat_pack(
            "testpack",
            order=60,
            time_stamp=datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC),
        ),
        game=game,
    )
    builder.vehicle(
        "testcar",
        _fragment("testcar"),
        high_fragment=_fragment("testcar_hi", high_detail=True),
        textures=_textures("testcar"),
    )
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
    assert pack.setup is not None
    assert pack.setup.order == 60
    assert pack.setup.time_stamp == "16/08/2026 12:00:00"
    stream_registration = next(
        item
        for item in pack.content.data_files
        if item.file_type == DlcDataFileType.RPF
    )
    assert stream_registration.filename == (
        "dlc_testpack:/%PLATFORM%/levels/gta5/vehicles/vehicles.rpf"
    )
    assert stream_registration.disabled is True
    assert stream_registration.persistent is True
    assert stream_registration.contents is None
    startup = pack.content.content_change_sets[0]
    assert startup.requires_loading_screen is False
    assert {path.casefold() for path in startup.files_to_enable} == {
        item.filename.casefold() for item in pack.content.data_files
    }
    assert pack.setup.content_change_set_groups[0].name == "GROUP_STARTUP"
    assert not any("_manifest.ymf" in item.filename for item in pack.content.data_files)

    archive = RpfArchive.from_path(output.paths.dlc_rpf, load_nested=True)
    try:
        assert archive.find_entry("x64/levels/gta5/vehicles/vehicles.rpf") is not None
        assert (
            archive.find_entry("%PLATFORM%/levels/gta5/vehicles/vehicles.rpf") is None
        )
        for path in (
            output.paths.vehicles_meta,
            output.paths.handling_meta,
            output.paths.variations_meta,
            output.paths.carcols_meta,
        ):
            entry = archive.find_entry(path)
            assert entry is not None
            assert validate_vehicle_meta_xml(entry.read()).valid
            assert read_vehicle_meta(entry.read()).validate().valid
        vehicles_entry = archive.find_entry(output.paths.vehicles_meta)
        assert vehicles_entry is not None
        vehicle_document = read_vehicle_meta(vehicles_entry.read()).content
        assert [vehicle.model_name for vehicle in vehicle_document.vehicles] == [
            "testcar"
        ]

        yft_entry = archive.find_entry(output.paths.streamed_rpf / "testcar.yft")
        high_yft_entry = archive.find_entry(
            output.paths.streamed_rpf / "testcar_hi.yft"
        )
        ytd_entry = archive.find_entry(output.paths.streamed_rpf / "testcar.ytd")
        assert yft_entry is not None and yft_entry._archive is not None
        assert high_yft_entry is not None and high_yft_entry._archive is not None
        assert ytd_entry is not None and ytd_entry._archive is not None
        assert (
            read_yft(yft_entry._archive.read_entry_standalone(yft_entry)).version == 171
        )
        assert (
            read_yft(
                high_yft_entry._archive.read_entry_standalone(high_yft_entry)
            ).version
            == 171
        )
        assert (
            read_ytd(ytd_entry._archive.read_entry_standalone(ytd_entry)).game
            == GameTarget.GTA5_ENHANCED
        )
    finally:
        archive.close()


def test_vehicle_pack_rejects_legacy_literal_platform_layout() -> None:
    builder = _builder()
    pack = builder.build()
    stream = next(
        item
        for item in pack.content.data_files
        if item.file_type == DlcDataFileType.RPF
    )
    old_path = "x64/levels/gta5/vehicles/vehicles.rpf"
    payload = pack.files.pop(str(builder.STREAMED_RPF))
    pack.files[old_path] = payload
    stream.filename = pack.path(old_path)
    stream.contents = DlcDataFileContents.VEHICLES

    report = validate_enhanced_vehicle_pack_layout(pack)

    assert not report.valid
    assert {
        "vehicle.pack.layout.registrations.invalid",
        "vehicle.pack.layout.stream.contents.invalid",
        "vehicle.pack.layout.stream.mount.invalid",
    }.issubset({issue.code for issue in report})


def test_vehicle_pack_rejects_virtual_macro_as_physical_payload_path() -> None:
    builder = _builder()
    pack = builder.build()
    payload = pack.files.pop(str(builder.STREAMED_RPF))
    pack.files["%PLATFORM%/levels/gta5/vehicles/vehicles.rpf"] = payload

    report = validate_enhanced_vehicle_pack_layout(pack)

    assert {
        "vehicle.pack.layout.stream.file_macro.invalid",
        "vehicle.pack.layout.stream.file_missing",
    }.issubset({issue.code for issue in report})


def test_vehicle_pack_requires_explicit_timestamp_and_load_order() -> None:
    builder = _builder()
    builder.setup = DlcSetupData.compat_pack("testpack")

    report = builder.validate()

    assert {
        "vehicle.pack.layout.timestamp.required",
        "vehicle.pack.layout.order.invalid",
    }.issubset({issue.code for issue in report})


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


def test_vehicle_pack_rejects_missing_high_detail_companion() -> None:
    builder = _builder()
    builder.vehicles[0].high_fragment = None

    codes = {issue.code for issue in builder.validate()}

    assert "vehicle.yft_pair.high_fragment.required" in codes


def test_vehicle_pair_accepts_typed_and_binary_inputs() -> None:
    fragment = _fragment("testcar")
    high_fragment = _fragment("testcar_hi", high_detail=True)

    assert validate_vehicle_yft_pair("testcar", fragment, high_fragment).valid
    assert validate_vehicle_yft_pair(
        "testcar",
        build_yft_bytes(fragment),
        build_yft_bytes(high_fragment),
    ).valid


def test_gen9_vehicle_pair_preserves_explicit_vertex_buffer_flags() -> None:
    fragment = _skinned_fragment("flagcar")
    high_fragment = _skinned_fragment("flagcar_hi", high_detail=True)

    rebuilt_fragment = read_yft(build_yft_bytes(fragment))
    rebuilt_high_fragment = read_yft(build_yft_bytes(high_fragment))

    assert _vertex_buffer_flags(rebuilt_fragment) == [0x00580409] * 4
    assert _vertex_buffer_flags(rebuilt_high_fragment) == [0x00580409]
    assert validate_vehicle_yft_pair(
        "flagcar",
        rebuilt_fragment,
        rebuilt_high_fragment,
    ).valid


def test_vehicle_pack_roundtrips_binary_fragment_inputs(tmp_path) -> None:
    builder = _builder()
    asset = builder.vehicles[0]
    asset.fragment = build_yft_bytes(asset.fragment)
    asset.high_fragment = build_yft_bytes(asset.high_fragment)

    output = builder.save(tmp_path / "binary_inputs")

    assert output.report.valid


def test_vehicle_pair_rejects_invalid_high_detail_binary() -> None:
    builder = _builder()
    builder.vehicles[0].high_fragment = b"not a YFT"

    codes = {issue.code for issue in builder.validate()}

    assert "vehicle.yft_pair.high_fragment.invalid" in codes


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda _base, high: setattr(high, "version", 162),
            "vehicle.yft_pair.high_fragment.target_invalid",
        ),
        (
            lambda base, _high: setattr(
                base,
                "main_drawable",
                _fragment("replacement", high_detail=True).main_drawable,
            ),
            "vehicle.yft_pair.fragment.lod_chain_invalid",
        ),
        (
            lambda _base, high: high.main_drawable.model([_mesh()], lod="medium"),
            "vehicle.yft_pair.high_fragment.lod_chain_invalid",
        ),
        (
            lambda _base, high: setattr(high, "tune_name", "pack:/wrong"),
            "vehicle.yft_pair.high_fragment.tune_name_invalid",
        ),
    ],
)
def test_vehicle_pair_rejects_target_lod_and_tune_mismatches(
    mutate,
    expected: str,
) -> None:
    fragment = _fragment("testcar")
    high_fragment = _fragment("testcar_hi", high_detail=True)
    mutate(fragment, high_fragment)

    codes = {
        issue.code
        for issue in validate_vehicle_yft_pair("testcar", fragment, high_fragment)
    }

    assert expected in codes


def test_vehicle_pair_rejects_skeleton_and_physics_mismatches() -> None:
    fragment = _fragment("testcar")
    high_fragment = _fragment("testcar_hi", high_detail=True)
    fragment.main_drawable.skeleton = YdrSkeleton(bones=[YdrBone(name="root", tag=0)])
    high_fragment.main_drawable.skeleton = YdrSkeleton(
        bones=[YdrBone(name="root", tag=1)]
    )
    fragment.physics_lod_details = [
        YftPhysicsLod(
            "high",
            num_children=1,
            children=(YftPhysicsChild(owner_group_name="chassis"),),
        )
    ]
    high_fragment.physics_lod_details = [
        YftPhysicsLod(
            "high",
            num_children=2,
            children=(
                YftPhysicsChild(owner_group_name="chassis"),
                YftPhysicsChild(owner_group_name="door", bone_id=1),
            ),
        )
    ]

    codes = {
        issue.code
        for issue in validate_vehicle_yft_pair("testcar", fragment, high_fragment)
    }

    assert "vehicle.yft_pair.skeleton.tag_mismatch" in codes
    assert "vehicle.yft_pair.physics.child_count_mismatch" in codes


def test_vehicle_pair_rejects_composite_bound_slot_mismatch() -> None:
    fragment = _fragment("testcar")
    high_fragment = _fragment("testcar_hi", high_detail=True)
    box = BoundBox.from_bounds(Vector3(-1.0, -1.0, -1.0), Vector3(1.0, 1.0, 1.0))

    def composite(child: BoundChild) -> BoundComposite:
        return BoundComposite(
            bound_type=10,
            sphere_radius=0.0,
            box_max=Vector3(),
            margin=0.0,
            box_min=Vector3(),
            box_center=Vector3(),
            sphere_center=Vector3(),
            children=[child],
        )

    fragment.physics_lod_details = [
        YftPhysicsLod("high", composite_bound=composite(BoundChild(box)))
    ]
    high_fragment.physics_lod_details = [
        YftPhysicsLod("high", composite_bound=composite(BoundChild(None)))
    ]

    codes = {
        issue.code
        for issue in validate_vehicle_yft_pair("testcar", fragment, high_fragment)
    }

    assert "vehicle.yft_pair.physics.bound_topology_mismatch" in codes


def test_vehicle_pack_rejects_orphan_high_detail_name() -> None:
    builder = _builder()
    builder.vehicles[0].name = "testcar_hi"

    codes = {issue.code for issue in builder.validate()}

    assert "vehicle.yft_pair.name.high_detail" in codes


def test_vehicle_pair_rejects_glass_window_ownership_in_high_detail() -> None:
    fragment = _fragment("testcar")
    high_fragment = _fragment("testcar_hi", high_detail=True)
    high_fragment.vehicle_glass_windows = YftVehicleGlassWindows()

    codes = {
        issue.code
        for issue in validate_vehicle_yft_pair("testcar", fragment, high_fragment)
    }

    assert "vehicle.yft_pair.high_fragment.vehicle_glass_invalid" in codes


@pytest.mark.integration("FIVEFURY_GTA5_ENHANCED_PATH")
def test_retail_enhanced_jester_uses_paired_vehicle_fragments() -> None:
    assert _ENHANCED_ROOT is not None
    with GameFileCache(
        _ENHANCED_ROOT,
        game=GameTarget.GTA5_ENHANCED,
        load_audio=False,
        load_peds=False,
        use_index_cache=True,
    ) as cache:
        cache.scan_game(gen9=True)
        fragments = []
        sizes = []
        for name in ("jester", "jester_hi"):
            asset = cache.get_asset(name, kind=GameFileType.YFT)
            assert asset is not None
            payload = cache.read_bytes(asset)
            game_file = cache.load_asset(asset)
            assert payload is not None and game_file is not None
            sizes.append(asset.size)
            fragments.append(game_file.parsed)

    fragment, high_fragment = fragments
    assert sizes == [739_991, 1_079_294]
    assert fragment.version == high_fragment.version == 171
    assert fragment.tune_name == "pack:/jester"
    assert high_fragment.tune_name == "pack:/jester_hi"
    assert fragment.main_drawable.skeleton.bone_count == 66
    assert high_fragment.main_drawable.skeleton.bone_count == 66
    assert {lod: len(list(fragment.iter_meshes(lod))) for lod in YdrLod} == {
        YdrLod.HIGH: 15,
        YdrLod.MEDIUM: 13,
        YdrLod.LOW: 11,
        YdrLod.VERY_LOW: 6,
    }
    assert len(list(high_fragment.iter_meshes(YdrLod.HIGH))) == 23
    assert not any(
        high_fragment.main_drawable.lods.get(lod)
        for lod in (YdrLod.MEDIUM, YdrLod.LOW, YdrLod.VERY_LOW)
    )
    assert len(fragment.best_physics_lod.groups) == 20
    assert len(fragment.best_physics_lod.children) == 20
    assert len(fragment.best_physics_lod.link_attachments.matrices) == 20
    assert len(fragment.vehicle_glass_windows.windows) == 6
    assert high_fragment.vehicle_glass_windows is None
    assert validate_vehicle_yft_pair("jester", fragment, high_fragment).valid


@pytest.mark.integration("FIVEFURY_GTA5_ENHANCED_PATH")
def test_retail_enhanced_comet5_reauthoring_preserves_vertex_buffer_flags() -> None:
    assert _ENHANCED_ROOT is not None
    rebuilt_fragments = []
    with GameFileCache(
        _ENHANCED_ROOT,
        game=GameTarget.GTA5_ENHANCED,
        load_audio=False,
        load_peds=False,
        use_index_cache=True,
    ) as cache:
        cache.scan_game(gen9=True)
        for name in ("comet5", "comet5_hi"):
            asset = cache.get_asset(name, kind=GameFileType.YFT)
            assert asset is not None
            game_file = cache.load_asset(asset)
            assert game_file is not None
            donor = game_file.parsed
            donor_flags = _vertex_buffer_flags(donor)
            assert donor_flags
            assert set(donor_flags) == {0x00580409}
            assert donor.main_drawable is not None

            authored = create_yft(
                donor.main_drawable.to_build(name=name),
                name=name,
                version=171,
            )
            authored.tune_name = f"pack:/{name}"
            rebuilt = read_yft(build_yft_bytes(authored))

            assert _vertex_buffer_flags(rebuilt) == donor_flags
            rebuilt_fragments.append(rebuilt)

    assert validate_vehicle_yft_pair("comet5", *rebuilt_fragments).valid


def _fragment_tail(drawable):
    return (
        drawable.fragment_matrix,
        tuple(bound is None for bound in drawable.extra_bounds),
        drawable.extra_bound_matrices,
        drawable.skeleton_type_name,
        drawable.load_skeleton,
        bool(drawable.locators_pointer),
        bool(drawable.animations_pointer),
        bool(drawable.cloned_shader_group_pointer),
    )


def _fragment_build(drawable, *, name: str):
    return YftFragmentDrawableBuild.from_fragment(
        drawable,
        drawable.to_build(name=name),
    )


@pytest.mark.integration("FIVEFURY_GTA5_ENHANCED_PATH")
def test_retail_enhanced_comet5_reauthoring_preserves_fragment_drawable_tails() -> None:
    assert _ENHANCED_ROOT is not None
    rebuilt_fragments = []
    with GameFileCache(
        _ENHANCED_ROOT,
        game=GameTarget.GTA5_ENHANCED,
        load_audio=False,
        load_peds=False,
        use_index_cache=True,
    ) as cache:
        cache.scan_game(gen9=True)
        for name in ("comet5", "comet5_hi"):
            asset = cache.get_asset(name, kind=GameFileType.YFT)
            assert asset is not None
            game_file = cache.load_asset(asset)
            assert game_file is not None
            donor = game_file.parsed
            assert donor.main_drawable.skeleton_type_name == "skel"

            expected_tails = {
                entry.label: _fragment_tail(entry.drawable)
                for entry in donor.iter_physics_drawables()
            }
            assert len(expected_tails) == 21
            assert all(
                tail[3] is YftFragmentDrawableName.NULL
                for tail in expected_tails.values()
            )
            main_tail = _fragment_tail(donor.main_drawable)
            donor.main_drawable = _fragment_build(
                donor.main_drawable,
                name=name,
            )
            rebuilt_lods = []
            for lod in donor.physics_lod_details:
                children = []
                for child in lod.children:
                    entities = {}
                    for field_name in ("undamaged_entity", "damaged_entity"):
                        entity = getattr(child, field_name)
                        if entity is None or entity.drawable is None:
                            continue
                        entities[field_name] = dataclasses.replace(
                            entity,
                            drawable=_fragment_build(
                                entity.drawable,
                                name=entity.label,
                            ),
                        )
                    children.append(dataclasses.replace(child, **entities))
                child_by_pointer = {child.pointer: child for child in children}
                groups = tuple(
                    dataclasses.replace(
                        group,
                        children=tuple(
                            child_by_pointer[child.pointer] for child in group.children
                        ),
                    )
                    for group in lod.groups
                )
                rebuilt_lods.append(
                    dataclasses.replace(lod, children=tuple(children), groups=groups)
                )
            donor.physics_lod_details = rebuilt_lods

            rebuilt = read_yft(build_yft_bytes(donor))
            assert _fragment_tail(rebuilt.main_drawable) == main_tail
            assert {
                entry.label: _fragment_tail(entry.drawable)
                for entry in rebuilt.iter_physics_drawables()
            } == expected_tails
            assert rebuilt.validate().valid
            rebuilt_fragments.append(rebuilt)

    assert validate_vehicle_yft_pair("comet5", *rebuilt_fragments).valid


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
