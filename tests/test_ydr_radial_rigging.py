from __future__ import annotations

import copy
from unittest.mock import patch

import numpy as np
import pytest

from fivefury import Quaternion, Vector2, Vector3, Vector4
from fivefury.matrix import transform_tangents
from fivefury.ydr import (
    RadialBoneRigRule,
    Ydr,
    YdrBone,
    YdrLod,
    YdrMesh,
    YdrMeshInput,
    YdrModel,
    YdrSkeleton,
    YdrSkeletonBinding,
    build_ydr_bytes,
    create_ydr,
    read_ydr,
    rig_mesh_to_bones_radially,
    rig_ydr_to_bones_radially,
    skeleton_absolute_transforms,
)


@pytest.fixture(params=[False, True], ids=["fresh", "read"])
def skeleton(request) -> YdrSkeleton:
    skeleton = YdrSkeleton()
    root = skeleton.bone(
        "root",
        tag=100,
        translation=Vector3(10, 20, 30),
        rotation=Quaternion(0, 0, 2**-0.5, 2**-0.5),
        scale=Vector3(2, 3, 4),
    )
    parent = skeleton.bone(
        "parent",
        tag=200,
        parent=root,
        translation=Vector3(1, 2, 3),
        rotation=Quaternion(0, 0, 2**-0.5, 2**-0.5),
        scale=Vector3(5, 2, 1),
    )
    skeleton.bone("target", tag=300, parent=parent, translation=Vector3(1, 1, 1))
    if request.param:
        drawable = create_ydr(
            meshes=[
                YdrMeshInput(
                    positions=[Vector3(), Vector3(1, 0, 0), Vector3(0, 1, 0)],
                    indices=[0, 1, 2],
                    texcoords=[[Vector2(), Vector2(1, 0), Vector2(0, 1)]],
                )
            ],
            skeleton=skeleton,
        )
        skeleton = read_ydr(build_ydr_bytes(drawable)).skeleton
        assert skeleton is not None
        assert len(skeleton.transformations) == 3
    else:
        assert skeleton.transformations == []
    return skeleton


def _mesh(positions: list[Vector3]) -> YdrMesh:
    return YdrMesh(
        positions=positions,
        bone_ids=[0],
        blend_weights=[(1.0, 0.0, 0.0, 0.0)] * len(positions),
        blend_indices=[(0, 0, 0, 0)] * len(positions),
    )


def _weight(mesh: YdrMesh, vertex: int, tag: int) -> float:
    return sum(
        weight
        for index, weight in zip(
            mesh.blend_indices[vertex], mesh.blend_weights[vertex], strict=True
        )
        if mesh.bone_ids[index] == tag
    )


@pytest.mark.parametrize(
    "explicit", [False, True], ids=["default-center", "explicit-center"]
)
@pytest.mark.parametrize("selector", ["name", "tag", "index", "bone"])
def test_radial_centers_use_object_space(skeleton, explicit, selector) -> None:
    # target -> parent: (-1, 7, 4); parent -> root: (-11, 18, 46).
    bind_center = Vector3(-11, 18, 46)
    center = Vector3(40, 50, 60) if explicit else bind_center
    mesh = _mesh([center, center + Vector3(0.5, 0, 0), Vector3(1, 1, 1)])
    bone = {"name": "target", "tag": 300, "index": 2, "bone": skeleton.bones[2]}[
        selector
    ]
    before = copy.deepcopy(skeleton)

    report = rig_mesh_to_bones_radially(
        mesh,
        [
            RadialBoneRigRule(
                bone, radius=1, falloff="linear", center=center if explicit else None
            )
        ],
        skeleton=skeleton,
    )

    assert report.vertices == 2
    assert _weight(mesh, 0, 2) == pytest.approx(1, abs=1e-5)
    assert _weight(mesh, 1, 2) == pytest.approx(0.5, abs=1e-5)
    assert _weight(mesh, 2, 2) == 0
    assert skeleton.bones == before.bones
    assert skeleton.transformations == before.transformations


@pytest.mark.parametrize("operation", ["mesh", "drawable"])
def test_bind_pose_composed_once_per_operation(skeleton, operation) -> None:
    meshes = [_mesh([Vector3(-11, 18, 46)] * 8) for _ in range(4)]
    rules = [
        RadialBoneRigRule("target", radius=1),
        RadialBoneRigRule("parent", radius=1),
    ]
    models = [
        YdrModel(lod=YdrLod.HIGH, meshes=meshes[:2]),
        YdrModel(lod=YdrLod.LOW, meshes=meshes[2:]),
    ]
    for model in models:
        model.set_skin_binding()
    drawable = Ydr(
        version=165,
        skeleton=skeleton,
        lods={YdrLod.HIGH: [models[0]], YdrLod.LOW: [models[1]]},
    )
    with patch(
        "fivefury.ydr.rigging.skeleton_absolute_transforms",
        wraps=skeleton_absolute_transforms,
    ) as compose:
        if operation == "mesh":
            report = rig_mesh_to_bones_radially(meshes[0], rules, skeleton=skeleton)
        else:
            report = rig_ydr_to_bones_radially(drawable, rules)
        compose.assert_called_once_with(skeleton)
    assert report.meshes == (1 if operation == "mesh" else 4)


@pytest.mark.parametrize("explicit", [False, True])
def test_rigid_conversion_preserves_all_meshes_and_binding(skeleton, explicit) -> None:
    hit = YdrMesh(
        positions=[Vector3(1, 1, 1), Vector3(1, 1, 1.1)],
        normals=[Vector3(1, 1, 0).normalized()] * 2,
        tangents=[Vector4(1, -1, 0, -1)] * 2,
    )
    miss = YdrMesh(positions=[Vector3(0, 0, 0)])
    model = YdrModel(lod=YdrLod.HIGH, meshes=[hit, miss])
    model.bind_to_bone("parent", skeleton=skeleton)
    drawable = Ydr(version=165, skeleton=skeleton, lods={YdrLod.HIGH: [model]})
    rule = RadialBoneRigRule(
        "target",
        radius=1,
        falloff="linear",
        center=Vector3(-11, 18, 46) if explicit else None,
    )

    report = rig_ydr_to_bones_radially(drawable, [rule])

    assert report.vertices == 2
    assert model.has_skin
    assert model.meshes == [hit, miss]
    np.testing.assert_allclose(
        hit.positions, [(-11, 18, 46), (-11, 18, 46.4)], atol=1e-5
    )
    np.testing.assert_allclose(miss.positions, [(4, 22, 42)], atol=1e-5)
    assert _weight(hit, 1, 2) == pytest.approx(0.6, abs=1e-5)
    assert _weight(hit, 1, 1) == pytest.approx(0.4, abs=1e-5)
    assert _weight(miss, 0, 1) == 1
    # Combined XY basis is diag(-15, -4): normals use its inverse transpose.
    normal = Vector3(-1 / 15, -1 / 4, 0).normalized()
    tangent = Vector3(-15, 4, 0).normalized()
    np.testing.assert_allclose(hit.normals, [normal, normal], atol=1e-5)
    np.testing.assert_allclose(hit.tangents, [Vector4(*tangent, -1)] * 2, atol=1e-5)
    positions = list(hit.positions)
    rig_ydr_to_bones_radially(drawable, [rule])
    assert hit.positions == positions


def test_unaffected_rigid_model_is_not_converted(skeleton) -> None:
    model = YdrModel(lod=YdrLod.HIGH, meshes=[YdrMesh(positions=[Vector3()])])
    model.bind_to_bone("parent", skeleton=skeleton)
    before = copy.deepcopy(model)
    drawable = Ydr(version=165, skeleton=skeleton, lods={YdrLod.HIGH: [model]})
    report = rig_ydr_to_bones_radially(
        drawable, [RadialBoneRigRule("target", radius=1)]
    )
    assert report.vertices == 0
    assert not report.changed
    assert model == before


def test_standalone_parented_bone_requires_coordinate_context() -> None:
    mesh = _mesh([Vector3(1, 2, 3)])
    bone = YdrBone(tag=300, parent_index=0, translation=Vector3(1, 2, 3))
    with pytest.raises(ValueError, match="skeleton= or center="):
        rig_mesh_to_bones_radially(mesh, [RadialBoneRigRule(bone, radius=1)])
    report = rig_mesh_to_bones_radially(
        mesh, [RadialBoneRigRule(bone, radius=1, center=Vector3(1, 2, 3))]
    )
    assert report.vertices == 1


def test_standalone_root_and_numeric_explicit_center() -> None:
    for bone, center in [
        (YdrBone(tag=300, translation=Vector3(1, 2, 3)), None),
        (300, Vector3(1, 2, 3)),
    ]:
        mesh = _mesh([Vector3(1, 2, 3)])
        report = rig_mesh_to_bones_radially(
            mesh, [RadialBoneRigRule(bone, radius=1, center=center)]
        )
        assert report.vertices == 1
        assert _weight(mesh, 0, bone.index if isinstance(bone, YdrBone) else bone) == 1


@pytest.mark.parametrize("selector, expected", [("root", 0), (1, 1), ("child", 1)])
def test_radial_palette_prefers_indices_over_ambiguous_tags(selector, expected) -> None:
    skeleton = YdrSkeleton()
    root = skeleton.bone("root", tag=1)
    skeleton.bone("child", tag=500, parent=root)
    mesh = _mesh([Vector3()])
    mesh.bone_ids = [1, 0, 500]
    report = rig_mesh_to_bones_radially(
        mesh, [RadialBoneRigRule(selector, radius=1)], skeleton=skeleton
    )
    assert report.bones_added == 0
    assert mesh.bone_ids == [1, 0, 500]
    assert mesh.blend_indices[0][0] == (1 if expected == 0 else 0)
    assert _weight(mesh, 0, expected) == 1


@pytest.mark.parametrize("palette, added", [([0], 1), ([0, 500], 0)])
def test_resolved_palette_appends_or_normalizes_canonical_index(palette, added) -> None:
    skeleton = YdrSkeleton()
    root = skeleton.bone("root", tag=1)
    skeleton.bone("child", tag=500, parent=root)
    mesh = _mesh([Vector3()])
    mesh.bone_ids = palette
    report = rig_mesh_to_bones_radially(
        mesh, [RadialBoneRigRule("child", radius=1)], skeleton=skeleton
    )
    assert report.bones_added == added
    assert mesh.bone_ids == [0, 1]
    assert _weight(mesh, 0, 1) == 1


def test_tangent_transform_reflection_and_empty_channel() -> None:
    transform = np.diag([-2, 3, 4, 1])
    assert transform_tangents([], transform) == []
    assert transform_tangents([Vector4(1, 0, 0, -1)], transform) == [
        Vector4(-1, 0, 0, 1)
    ]


@pytest.mark.parametrize("version", [165, 159], ids=["legacy", "enhanced"])
def test_decoded_rigid_drawable_roundtrip_retains_skin_declaration(
    skeleton, version
) -> None:
    source = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[Vector3(1, 1, 1), Vector3(1, 1, 1.1), Vector3()],
                indices=[0, 1, 2],
                texcoords=[[Vector2(), Vector2(1, 0), Vector2(0, 1)]],
            )
        ],
        skeleton=skeleton,
        version=version,
        skeleton_binding=YdrSkeletonBinding.rigid(bone_index=1),
    )
    drawable = read_ydr(source.to_bytes())
    static_flags = drawable.meshes[0].declaration_flags
    skin_flags = (1 << 1) | (1 << 2)
    assert static_flags & skin_flags == 0

    rig_ydr_to_bones_radially(
        drawable, [RadialBoneRigRule("target", radius=1, falloff="linear")]
    )
    result = read_ydr(build_ydr_bytes(drawable))

    assert result.models[0].has_skin
    mesh = result.meshes[0]
    assert mesh.declaration_flags == static_flags | skin_flags
    assert len(mesh.blend_weights) == len(mesh.positions)
    assert len(mesh.blend_indices) == len(mesh.positions)
    np.testing.assert_allclose(
        mesh.positions, [(-11, 18, 46), (-11, 18, 46.4), (4, 22, 42)], atol=1e-5
    )
    assert _weight(mesh, 0, 2) == pytest.approx(1, abs=1 / 255)
    assert _weight(mesh, 1, 2) == pytest.approx(0.6, abs=1 / 255)
    assert _weight(mesh, 1, 1) == pytest.approx(0.4, abs=1 / 255)
    assert _weight(mesh, 2, 1) == pytest.approx(1, abs=1 / 255)
