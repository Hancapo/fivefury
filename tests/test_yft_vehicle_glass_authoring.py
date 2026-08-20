from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import numpy as np
import pytest

from fivefury import GameTarget, Vector2, Vector3, Vector4
from fivefury.bounds import (
    BoundBox,
    BoundChild,
    BoundComposite,
    BoundGeometry,
    BoundMaterial,
    BoundMaterialType,
    BoundTriangleChunk,
    BoundType,
    build_geometry_bvh_from_chunk,
)
from fivefury.cache import GameFileCache
from fivefury.gamefile import GameFileType
from fivefury.rpf import RpfArchive
from fivefury.ydr import (
    Ydr,
    YdrBone,
    YdrBuild,
    YdrLod,
    YdrMaterialInput,
    YdrMeshInput,
    YdrModelInput,
    YdrSkeleton,
    YdrSkeletonBinding,
)
from fivefury.yft import (
    YftFragmentDrawable,
    YftPhysicsChild,
    YftPhysicsEntity,
    YftPhysicsGroup,
    YftPhysicsLod,
    YftVehicleGlassAssignment,
    build_yft_bytes,
    create_yft,
    read_yft,
    validate_yft_vehicle_glass,
)

_PANE_NAMES = (
    "windscreen",
    "windscreen_r",
    "window_lf",
    "window_rf",
    "window_lr",
    "window_rr",
)
_ENHANCED_ROOT_VALUE = os.environ.get("FIVEFURY_GTA5_ENHANCED_PATH")
_ENHANCED_ROOT = Path(_ENHANCED_ROOT_VALUE) if _ENHANCED_ROOT_VALUE else None


def _window_projection(window) -> np.ndarray:
    return np.asarray(window.basis, dtype=np.float64).reshape((4, 4)).T


def _project_points(window, points) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64)
    homogeneous = np.column_stack((values, np.ones(len(values), dtype=np.float64)))
    projected = (_window_projection(window) @ homogeneous.T).T
    return projected[:, :3] / projected[:, 3, None]


def _outline_corners(window) -> np.ndarray:
    raster = np.asarray(
        (
            (0.0, 0.0, 0.0, 1.0),
            (float(window.column_count), 0.0, 0.0, 1.0),
            (float(window.column_count), float(window.row_count), 0.0, 1.0),
            (0.0, float(window.row_count), 0.0, 1.0),
        ),
        dtype=np.float64,
    )
    projected = (np.linalg.inv(_window_projection(window)) @ raster.T).T
    return projected[:, :3] / projected[:, 3, None]


def _assert_projection_contains_points(window, points) -> None:
    values = np.asarray(points, dtype=np.float64)
    projected = _project_points(window, values)
    assert np.all(projected[:, 0] >= -1e-5)
    assert np.all(projected[:, 0] <= window.column_count + 1e-5)
    assert np.all(projected[:, 1] >= -1e-5)
    assert np.all(projected[:, 1] <= window.row_count + 1e-5)
    assert np.allclose(projected[:, 2], 0.0, atol=1e-5)

    outline = _outline_corners(window)
    assert np.all(values.min(axis=0) >= outline.min(axis=0) - 1e-5)
    assert np.all(values.max(axis=0) <= outline.max(axis=0) + 1e-5)


def _vehicle_fragment(game: GameTarget = GameTarget.GTA5_ENHANCED):
    version = 171 if game is GameTarget.GTA5_ENHANCED else 162
    positions: list[Vector3] = []
    indices: list[int] = []
    texcoords: list[Vector2] = []
    blend_indices: list[tuple[int, int, int, int]] = []
    for pane_index in range(6):
        base = len(positions)
        x = float(pane_index * 2)
        positions.extend(
            (
                Vector3(x, 0.0, 0.0),
                Vector3(x + 1.0, 0.0, 0.0),
                Vector3(x + 1.0, 0.0, 0.75),
                Vector3(x, 0.0, 0.75),
            )
        )
        indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
        texcoords.extend((Vector2(), Vector2(1.0, 0.0), Vector2(1.0, 1.0), Vector2(0.0, 1.0)))
        blend_indices.extend(((pane_index + 1, 0, 0, 0),) * 4)
    skeleton = YdrSkeleton(
        bones=[YdrBone(name="root", tag=0, index=0)]
        + [
            YdrBone(name=name, tag=100 + index, index=index + 1, parent_index=0)
            for index, name in enumerate(_PANE_NAMES)
        ],
    ).build()
    material = YdrMaterialInput(
        name="outer_glass",
        shader="vehicle_vehglass.sps",
        render_bucket=1,
    )
    mesh = YdrMeshInput(
        material="outer_glass",
        indices=indices,
        positions=positions,
        normals=[Vector3(0.0, -1.0, 0.0)] * len(positions),
        tangents=[Vector4(1.0, 0.0, 0.0, 1.0)] * len(positions),
        texcoords=[list(texcoords), list(texcoords)],
        colours0=[(1.0, 1.0, 1.0, 1.0)] * len(positions),
        blend_weights=[(1.0, 0.0, 0.0, 0.0)] * len(positions),
        blend_indices=blend_indices,
        bone_ids=[bone.tag for bone in skeleton.bones],
    )
    drawable = YdrBuild(
        version=version,
        materials=[material],
        lods={
            YdrLod.HIGH: [
                YdrModelInput(
                    meshes=[mesh],
                    skeleton_binding=YdrSkeletonBinding.skinned(),
                )
            ]
        },
        skeleton=skeleton,
    )
    children = []
    bounds = []
    for bone in skeleton.bones[1:]:
        bound = BoundBox.from_center_size(
            Vector3(),
            Vector3(1.0, 0.05, 0.75),
            material_index=BoundMaterialType.CAR_GLASS_WEAK,
        )
        child_drawable = YftFragmentDrawable.from_ydr(Ydr(version=version, bound=bound))
        bounds.append(bound)
        children.append(
            YftPhysicsChild.declare(
                bone_id=bone.tag,
                undamaged_entity=YftPhysicsEntity.declare(child_drawable),
            )
        )
    composite = BoundComposite(
        bound_type=BoundType.COMPOSITE,
        sphere_radius=0.0,
        box_max=Vector3(),
        margin=0.0,
        box_min=Vector3(),
        box_center=Vector3(),
        sphere_center=Vector3(),
        children=[BoundChild(bound) for bound in bounds],
    ).build()
    group = YftPhysicsGroup.declare("windows", children=children)
    source = create_yft(
        drawable,
        name="synthetic_vehicle",
        version=version,
        physics_lods=(YftPhysicsLod.declare("high", groups=(group,)),),
        physics_bound=composite,
    )
    assignments = [
        YftVehicleGlassAssignment.declare(index, 0, name, name=name)
        for index, name in enumerate(_PANE_NAMES)
    ]
    return source, mesh, assignments


def test_vehicle_glass_builder_derives_six_deterministic_windows() -> None:
    source, mesh, assignments = _vehicle_fragment()
    original_weights = list(mesh.blend_weights)
    original_indices = list(mesh.blend_indices)
    original_palette = list(mesh.bone_ids)

    result = source.recalculate_vehicle_glass(
        assignments,
        game=GameTarget.GTA5_ENHANCED,
    )

    assert result.report.valid
    assert len(result.windows.windows) == 6
    assert len(mesh.texcoords) == 3
    assert all(window.geometry_index == 0 for window in result.windows.windows)
    assert all(window.rows for window in result.windows.windows)
    assert mesh.blend_weights == original_weights
    assert mesh.blend_indices == original_indices
    assert mesh.bone_ids == original_palette
    assert validate_yft_vehicle_glass(source).valid
    for pane_index, window in enumerate(result.windows.windows):
        _assert_projection_contains_points(
            window,
            mesh.positions[pane_index * 4 : pane_index * 4 + 4],
        )

    previous = bytes(
        value
        for window in result.windows.windows
        for row in window.rows
        for span in (row.first, row.second)
        if span is not None
        for value in span.values
    )
    mesh.positions[0] = (-0.25, 0.0, 0.0)
    changed = source.recalculate_vehicle_glass(
        assignments,
        game=GameTarget.GTA5_ENHANCED,
    )
    current = bytes(
        value
        for window in changed.windows.windows
        for row in window.rows
        for span in (row.first, row.second)
        if span is not None
        for value in span.values
    )
    assert changed.report.valid
    assert current != previous


def test_vehicle_glass_validation_uses_direct_geometry_polygon_materials() -> None:
    source, _mesh, assignments = _vehicle_fragment()
    source.recalculate_vehicle_glass(
        assignments,
        game=GameTarget.GTA5_ENHANCED,
    ).report.raise_for_errors()
    geometry_bvh = build_geometry_bvh_from_chunk(
        BoundTriangleChunk(
                vertices=[
                    Vector3(),
                    Vector3(1.0, 0.0, 0.0),
                    Vector3(0.0, 0.0, 1.0),
            ],
            triangles=[(0, 1, 2)],
            material_indices=[1],
        ),
        materials=[
            BoundMaterial(type=BoundMaterialType.DEFAULT),
            BoundMaterial(type=BoundMaterialType.CAR_GLASS_WEAK),
        ],
    )
    direct_glass = BoundGeometry(
        **{
            field.name: getattr(geometry_bvh, field.name)
            for field in dataclasses.fields(BoundGeometry)
        }
    )
    direct_glass.bound_type = BoundType.GEOMETRY
    direct_glass.build()
    composite = source.best_physics_lod.composite_bound
    assert composite is not None
    composite.children[0].bound = direct_glass

    report = validate_yft_vehicle_glass(source)
    rebuilt = read_yft(build_yft_bytes(source))

    assert direct_glass.material_type is BoundMaterialType.DEFAULT
    assert report.valid
    assert validate_yft_vehicle_glass(rebuilt).valid


def test_vehicle_glass_builder_resolves_sparse_palette_before_skeleton_index() -> None:
    source, mesh, assignments = _vehicle_fragment()
    original_palette = list(mesh.bone_ids)
    mesh.bone_ids = [
        original_palette[0],
        original_palette[2],
        original_palette[1],
        *original_palette[3:],
    ]
    slot_by_bone = {bone_id: index for index, bone_id in enumerate(mesh.bone_ids)}
    mesh.blend_indices = [
        (slot_by_bone[original_palette[indices[0]]], 0, 0, 0)
        for indices in mesh.blend_indices
    ]

    result = source.recalculate_vehicle_glass(
        assignments,
        game=GameTarget.GTA5_ENHANCED,
    )

    assert result.report.valid
    assert len(result.windows.windows) == 6


@pytest.mark.skipif(
    _ENHANCED_ROOT is None or not _ENHANCED_ROOT.is_dir(),
    reason="set FIVEFURY_GTA5_ENHANCED_PATH to run the retail vehicle-glass regression",
)
def test_retail_enhanced_jester_vehicle_glass_uses_polygon_materials() -> None:
    assert _ENHANCED_ROOT is not None
    with GameFileCache(
        _ENHANCED_ROOT,
        game=GameTarget.GTA5_ENHANCED,
        load_audio=False,
        load_peds=False,
        use_index_cache=True,
    ) as cache:
        cache.scan_game(gen9=True)
        asset = cache.get_asset("jester", kind=GameFileType.YFT)
        assert asset is not None
        game_file = cache.load_asset(asset)
        assert game_file is not None
        source = game_file.parsed

    assert source.vehicle_glass_windows is not None
    assert len(source.vehicle_glass_windows.windows) == 6
    assert validate_yft_vehicle_glass(source).valid
    for window in source.vehicle_glass_windows.windows:
        expected = np.asarray(
            (
                (0.0, 0.0, 0.0),
                (float(window.column_count), 0.0, 0.0),
                (float(window.column_count), float(window.row_count), 0.0),
                (0.0, float(window.row_count), 0.0),
            )
        )
        assert np.allclose(_project_points(window, _outline_corners(window)), expected)


def test_vehicle_glass_builder_rejects_overlap_without_mutation() -> None:
    source, mesh, assignments = _vehicle_fragment()
    assignments[1] = YftVehicleGlassAssignment.declare(
        1,
        0,
        "windscreen",
        name="duplicate",
    )

    result = source.recalculate_vehicle_glass(
        assignments,
        game=GameTarget.GTA5_ENHANCED,
    )

    assert not result.report.valid
    assert source.vehicle_glass_windows is None
    assert len(mesh.texcoords) == 2
    assert any(
        issue.code == "yft.vehicle_glass.assignment_overlap" for issue in result.report
    )


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_vehicle_glass_builder_round_trips_yft(game: GameTarget) -> None:
    source, mesh, assignments = _vehicle_fragment(game)
    result = source.recalculate_vehicle_glass(
        assignments,
        game=game,
    )
    result.report.raise_for_errors()

    payload = build_yft_bytes(source)
    nested = RpfArchive.empty("vehicles.rpf")
    nested.file("synthetic_vehicle.yft", payload)
    outer = RpfArchive.empty("dlc.rpf")
    outer.file("x64/levels/gta5/vehicles/vehicles.rpf", nested.to_bytes())
    packaged = RpfArchive.from_bytes(outer.to_bytes(), name="dlc.rpf", load_nested=True)
    entry = packaged.find_entry(
        "x64/levels/gta5/vehicles/vehicles.rpf/synthetic_vehicle.yft"
    )

    assert entry is not None
    rebuilt = read_yft(packaged.children[0].read_entry_standalone(entry))

    assert rebuilt.version == (171 if game is GameTarget.GTA5_ENHANCED else 162)
    assert rebuilt.vehicle_glass_windows is not None
    assert len(rebuilt.vehicle_glass_windows.windows) == 6
    assert validate_yft_vehicle_glass(rebuilt).valid
    for pane_index, window in enumerate(rebuilt.vehicle_glass_windows.windows):
        _assert_projection_contains_points(
            window,
            mesh.positions[pane_index * 4 : pane_index * 4 + 4],
        )


def test_vehicle_glass_builder_rejects_target_version_mismatch() -> None:
    source, mesh, assignments = _vehicle_fragment()

    result = source.recalculate_vehicle_glass(assignments, game=GameTarget.GTA5)

    assert not result.report.valid
    assert any(
        issue.code == "yft.vehicle_glass.edition_version" for issue in result.report
    )
    assert source.vehicle_glass_windows is None
    assert len(mesh.texcoords) == 2


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("missing_tangents", "yft.vehicle_glass.vertex_channels"),
        ("missing_uv1", "yft.vehicle_glass.vertex_channels"),
        ("degenerate", "yft.vehicle_glass.geometry"),
        ("unresolved_bone", "yft.vehicle_glass.bone_unresolved"),
        ("invalid_geometry", "yft.vehicle_glass.geometry_index"),
    ],
)
def test_vehicle_glass_builder_rejects_invalid_authoring_without_mutation(
    case: str,
    code: str,
) -> None:
    source, mesh, assignments = _vehicle_fragment()
    if case == "missing_tangents":
        mesh.tangents = []
    elif case == "missing_uv1":
        mesh.texcoords = [mesh.texcoords[0]]
    elif case == "degenerate":
        mesh.positions = [(0.0, 0.0, 0.0)] * 4 + list(mesh.positions[4:])
    elif case == "unresolved_bone":
        assignments[0] = YftVehicleGlassAssignment.declare(0, 0, "missing")
    elif case == "invalid_geometry":
        assignments[0] = YftVehicleGlassAssignment.declare(0, 99, "windscreen")

    result = source.recalculate_vehicle_glass(
        assignments,
        game=GameTarget.GTA5_ENHANCED,
    )

    assert not result.report.valid
    assert any(issue.code == code for issue in result.report)
    assert source.vehicle_glass_windows is None
    assert len(mesh.texcoords) < 3
