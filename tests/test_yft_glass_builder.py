from __future__ import annotations

import pytest

from fivefury.bounds import BoundBox
from fivefury.ydr import (
    Ydr,
    YdrBone,
    YdrLod,
    YdrMaterial,
    YdrMesh,
    YdrModel,
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
