from __future__ import annotations

import pytest

from fivefury.bounds import BoundBox
from fivefury.ydr import (
    Ydr,
    YdrBone,
    YdrBuild,
    YdrLod,
    YdrMaterial,
    YdrMaterialInput,
    YdrMesh,
    YdrMeshInput,
    YdrModel,
    YdrModelInput,
    YdrShader,
    YdrSkeleton,
    YdrSkeletonBinding,
)
from fivefury.yft import (
    Yft,
    YftFragmentDrawable,
    YftPhysicsChild,
    YftPhysicsEntity,
    YftPhysicsGroup,
    YftPhysicsLod,
    build_yft_bytes,
    create_yft,
    read_yft,
    simple_physics_bound,
    validate_yft,
)


def _glass_fragment() -> Yft:
    material = YdrMaterial(
        index=0,
        name="pane",
        shader_file_name="glass_breakable.sps",
    )
    mesh = YdrMesh(
        material_index=0,
        material=material,
        indices=[0, 1, 2, 0, 2, 3],
        positions=[
            (-1.0, 0.0, -1.0),
            (1.0, 0.0, -1.0),
            (1.0, 0.0, 1.0),
            (-1.0, 0.0, 1.0),
        ],
        tangents=[(1.0, 0.0, 0.0, 1.0)] * 4,
        texcoords=[[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]],
    )
    skeleton = YdrSkeleton(
        bones=[YdrBone(name="pane", tag=3882, index=0)]
    ).build()
    model = YdrModel(
        lod=YdrLod.HIGH,
        meshes=[mesh],
        skeleton_binding=YdrSkeletonBinding.rigid(bone_index=0),
    )
    drawable = Ydr(
        version=162,
        materials=[material],
        lods={YdrLod.HIGH: [model]},
        skeleton=skeleton,
    )
    child_drawable = YftFragmentDrawable.from_ydr(
        Ydr(
            version=162,
            bound=BoundBox.from_center_size(
                (0.0, 0.0, 0.0),
                (2.0, 0.04, 2.0),
            ),
        )
    )
    child = YftPhysicsChild.declare(
        bone_id=3882,
        undamaged_entity=YftPhysicsEntity.declare(child_drawable),
    )
    group = YftPhysicsGroup.declare_glass(
        "pane",
        glass_type=2,
        children=(child,),
    )
    return Yft(
        version=162,
        main_drawable=drawable,
        physics_lod_details=[YftPhysicsLod.declare("high", groups=(group,))],
    )


def _input_glass_fragment(*, bone_index: int = 0, mesh_count: int = 1) -> Yft:
    material = YdrMaterialInput(
        name="pane",
        shader=YdrShader.GLASS_BREAKABLE,
    )
    mesh = YdrMeshInput(
        material="pane",
        indices=[0, 1, 2, 0, 2, 3],
        positions=[
            (-1.0, 0.0, -1.0),
            (1.0, 0.0, -1.0),
            (1.0, 0.0, 1.0),
            (-1.0, 0.0, 1.0),
        ],
        tangents=[(1.0, 0.0, 0.0, 1.0)] * 4,
        texcoords=[
            [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
            [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        ],
    )
    skeleton = YdrSkeleton(
        bones=[YdrBone(name="pane", tag=3882, index=0)]
    ).build()
    drawable = YdrBuild(
        materials=[material],
        lods={
            YdrLod.HIGH: [
                YdrModelInput(
                    meshes=[mesh] * mesh_count,
                    skeleton_binding=YdrSkeletonBinding.rigid(
                        bone_index=bone_index
                    ),
                )
            ]
        },
        skeleton=skeleton,
    )
    child_drawable = YdrBuild(
        materials=[],
        bound=BoundBox.from_center_size(
            (0.0, 0.0, 0.0),
            (2.0, 0.04, 2.0),
        ),
    )
    child = YftPhysicsChild.declare(
        bone_id=3882,
        undamaged_entity=YftPhysicsEntity.declare(child_drawable),
    )
    group = YftPhysicsGroup.declare_glass(
        "pane",
        glass_type=2,
        children=(child,),
    )
    bound = simple_physics_bound()
    return create_yft(
        drawable,
        version=162,
        physics_lods=(YftPhysicsLod.declare("high", groups=(group,)),),
        physics_bound=bound,
    )


def test_build_glass_resolves_group_bone_mesh_shader_and_bound() -> None:
    fragment = _glass_fragment()

    panes = fragment.build_glass()

    assert panes == fragment.glass_panes
    assert len(panes) == 1
    assert panes[0].glass_type == 2
    assert panes[0].shader_index == 0
    assert panes[0].position_width == pytest.approx((2.0, 0.0, 0.0))
    assert panes[0].position_height == pytest.approx((0.0, 0.0, 2.0))
    assert panes[0].bounds_offset_front == pytest.approx(0.02)
    assert panes[0].bounds_offset_back == pytest.approx(0.02)
    assert fragment.best_physics_lod.groups[0].glass_pane_model_info_index == 0
    assert not [
        issue
        for issue in fragment.validate()
        if "glass" in issue.path or "glass" in issue.message
    ]


def test_ensure_glass_builds_missing_metadata() -> None:
    fragment = _glass_fragment()

    assert fragment.ensure_glass() == fragment.glass_panes
    assert len(fragment.glass_panes) == 1


def test_build_glass_rejects_ambiguous_geometry() -> None:
    fragment = _glass_fragment()
    model = next(fragment.main_drawable.iter_models(YdrLod.HIGH))
    model.meshes.append(model.meshes[0])

    with pytest.raises(ValueError, match="selects 2 glass meshes"):
        fragment.build_glass()


def test_input_glass_authoring_builds_and_round_trips() -> None:
    fragment = _input_glass_fragment()

    panes = fragment.ensure_glass()
    data = build_yft_bytes(fragment)
    rebuilt = read_yft(data)

    assert panes == fragment.glass_panes
    assert len(panes) == 1
    assert panes[0].shader_index == 0
    assert not [
        issue
        for issue in validate_yft(rebuilt).errors
        if "glass" in (issue.path or "") or "glass" in issue.message
    ]


def test_input_glass_authoring_rejects_ambiguous_geometry() -> None:
    fragment = _input_glass_fragment(mesh_count=2)

    with pytest.raises(ValueError, match="selects 2 glass meshes"):
        fragment.ensure_glass()


def test_input_glass_authoring_rejects_nonmatching_bone() -> None:
    fragment = _input_glass_fragment(bone_index=1)

    with pytest.raises(ValueError, match="does not select any glass geometry"):
        fragment.ensure_glass()


def test_input_glass_authoring_rejects_empty_skinning_arrays_cleanly() -> None:
    fragment = _input_glass_fragment()
    model = next(fragment.main_drawable.iter_models(YdrLod.HIGH))
    model.skeleton_binding = YdrSkeletonBinding.skinned()

    with pytest.raises(ValueError, match="does not select any glass geometry"):
        fragment.ensure_glass()
