from __future__ import annotations

import pytest

from fivefury import (
    Vector2,
    Vector3,
    YdrBone,
    YdrJoints,
    YdrMesh,
    YdrMeshInput,
    YdrSkeleton,
    create_ydr,
    read_ydr,
)


def skeleton_with_overlapping_root_tag() -> YdrSkeleton:
    return YdrSkeleton(bones=[
        YdrBone(name="root", tag=1, index=0),
        YdrBone(name="child", tag=500, index=1, parent_index=0),
    ])


@pytest.mark.parametrize("version", [165, 159])
@pytest.mark.parametrize("loaded", [False, True])
def test_root_normalization_preserves_palette_indices(version: int, loaded: bool) -> None:
    skeleton = skeleton_with_overlapping_root_tag()
    joints = YdrJoints()
    joints.rotation_limit(bone_id=1)
    joints.translation_limit(bone_id=1)
    mesh = YdrMeshInput(
        positions=[Vector3(), Vector3(1, 0, 0), Vector3(0, 1, 0)],
        indices=[0, 1, 2],
        texcoords=[[Vector2(), Vector2(1, 0), Vector2(0, 1)]],
        blend_weights=[(1, 0, 0, 0)] * 3,
        blend_indices=[(1, 0, 0, 0)] * 3,
        bone_ids=[0, 1],
    )
    source = create_ydr(meshes=[mesh], skeleton=skeleton, joints=joints, version=version)
    if loaded:
        source = read_ydr(source.to_bytes())
        source.skeleton.bones[0].tag = 1
        for limit in (*source.joints.rotation_limits, *source.joints.translation_limits):
            limit.bone_id = 1
        data = source.to_build().to_bytes()
    else:
        data = source.to_bytes()
    result = read_ydr(data)
    assert result.skeleton.bones[0].tag == 0
    assert result.meshes[0].bone_ids == [0, 1]
    assert result.meshes[0].blend_indices == [(1, 0, 0, 0)] * 3
    assert result.joints.rotation_limits[0].bone_id == 0
    assert result.joints.translation_limits[0].bone_id == 0
    assert result.meshes[0].resolve_bones(result.skeleton)[1].name == "child"
    assert read_ydr(result.to_build().to_bytes()).meshes[0].blend_indices == result.meshes[0].blend_indices


def test_named_and_object_palette_bindings_use_indices() -> None:
    skeleton = skeleton_with_overlapping_root_tag()
    mesh = YdrMesh(material_index=0)
    mesh.set_bone_ids([skeleton.bones[0], "child"], skeleton=skeleton)
    assert mesh.bone_ids == [0, 1]
    assert mesh.resolve_bones(skeleton) == skeleton.bones
    assert skeleton.resolve_bone_ids([1, 500]) == [skeleton.bones[1]] * 2
