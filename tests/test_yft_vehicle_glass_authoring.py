from __future__ import annotations

import pytest

from fivefury import GameTarget
from fivefury.bounds import (
    BoundBox,
    BoundChild,
    BoundComposite,
    BoundMaterialType,
    BoundType,
)
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


def _vehicle_fragment(game: GameTarget = GameTarget.GTA5_ENHANCED):
    version = 171 if game is GameTarget.GTA5_ENHANCED else 162
    positions: list[tuple[float, float, float]] = []
    indices: list[int] = []
    texcoords: list[tuple[float, float]] = []
    blend_indices: list[tuple[int, int, int, int]] = []
    for pane_index in range(6):
        base = len(positions)
        x = float(pane_index * 2)
        positions.extend(
            (
                (x, 0.0, 0.0),
                (x + 1.0, 0.0, 0.0),
                (x + 1.0, 0.0, 0.75),
                (x, 0.0, 0.75),
            )
        )
        indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
        texcoords.extend(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)))
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
        normals=[(0.0, -1.0, 0.0)] * len(positions),
        tangents=[(1.0, 0.0, 0.0, 1.0)] * len(positions),
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
            (0.0, 0.0, 0.0),
            (1.0, 0.05, 0.75),
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
        box_max=(0.0, 0.0, 0.0),
        margin=0.0,
        box_min=(0.0, 0.0, 0.0),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
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
    source, _mesh, assignments = _vehicle_fragment(game)
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
