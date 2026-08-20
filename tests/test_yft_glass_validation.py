from __future__ import annotations

import dataclasses

import pytest

from fivefury import Vector3
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
    YftGlassPane,
    YftPhysicsChild,
    YftPhysicsEntity,
    YftPhysicsGroup,
    YftPhysicsGroupFlag,
    YftPhysicsLod,
    validate_yft,
)


def _drawable(*, bound: BoundBox | None = None) -> Ydr:
    material = YdrMaterial(index=0, name="glass")
    skeleton = YdrSkeleton(bones=[YdrBone(name="pane", tag=7, index=0)]).build()
    model = YdrModel(
        lod=YdrLod.HIGH,
        meshes=[YdrMesh(material_index=0, material=material)],
        skeleton_binding=YdrSkeletonBinding.rigid(bone_index=0),
    )
    return Ydr(
        version=162,
        materials=[material],
        lods={YdrLod.HIGH: [model]},
        skeleton=skeleton,
        bound=bound,
    )


def _glass_child(*, with_bound: bool = True) -> YftPhysicsChild:
    bound = (
        BoundBox.from_center_size(Vector3(), Vector3(1.0, 1.0, 0.1))
        if with_bound
        else None
    )
    return YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(_drawable(bound=bound)),
        bone_id=7,
    )


def _source(group: YftPhysicsGroup, *, pane_count: int = 1) -> Yft:
    return Yft(
        main_drawable=_drawable(),
        glass_panes=[YftGlassPane() for _ in range(pane_count)],
        physics_lod_details=[YftPhysicsLod.declare(groups=(group,))],
    )


def _glass_errors(source: Yft) -> list[str]:
    return [
        f"{issue.path or issue.code}: {issue.message}"
        for issue in validate_yft(source)
        if "glass" in (issue.path or "") or "glass" in issue.message
    ]


def test_declare_glass_group_uses_modern_layout() -> None:
    child = _glass_child()

    group = YftPhysicsGroup.declare_glass(
        "pane",
        pane_index=3,
        children=(child,),
        flags=YftPhysicsGroupFlag.DAMAGE_WHEN_BROKEN,
    )

    assert group.is_glass
    assert group.flags & YftPhysicsGroupFlag.DAMAGE_WHEN_BROKEN
    assert group.glass_model_and_type == 0xFF
    assert group.glass_pane_model_info_index == 3
    assert YftPhysicsGroup().glass_model_and_type == 0xFF


def test_declare_can_configure_glass_without_manual_flags() -> None:
    group = YftPhysicsGroup.declare(
        "pane",
        children=(_glass_child(),),
        glass_pane_index=0,
    )

    assert group.is_glass
    assert group.glass_pane_model_info_index == 0


@pytest.mark.parametrize("pane_index", [-1, 256])
def test_declare_glass_rejects_invalid_pane_index(pane_index: int) -> None:
    with pytest.raises(ValueError, match="unsigned byte"):
        YftPhysicsGroup.declare_glass(
            "pane",
            pane_index=pane_index,
            children=(_glass_child(),),
        )


def test_declare_glass_requires_a_physics_child() -> None:
    with pytest.raises(ValueError, match="physics child"):
        YftPhysicsGroup.declare_glass("pane", pane_index=0, children=())


def test_validation_rejects_glass_group_without_child() -> None:
    group = YftPhysicsGroup(
        flags=YftPhysicsGroupFlag.MADE_OF_GLASS,
        glass_pane_model_info_index=0,
    )

    assert any(
        "require at least one physics child" in error
        for error in _glass_errors(_source(group))
    )


def test_validation_rejects_invalid_glass_pane_reference() -> None:
    group = YftPhysicsGroup.declare_glass(
        "pane",
        pane_index=1,
        children=(_glass_child(),),
    )

    assert any(
        "fragment glass pane array" in error
        for error in _glass_errors(_source(group))
    )


def test_validation_rejects_non_glass_pane_reference() -> None:
    group = YftPhysicsGroup.declare("body", children=(_glass_child(),))
    group = dataclasses.replace(group, glass_pane_model_info_index=1)

    assert any(
        "non-glass groups" in error
        for error in _glass_errors(_source(group, pane_count=2))
    )


def test_validation_checks_intact_glass_bound_and_render_geometry() -> None:
    valid = YftPhysicsGroup.declare_glass(
        "pane",
        pane_index=0,
        children=(_glass_child(),),
    )
    missing_bound = YftPhysicsGroup.declare_glass(
        "pane",
        pane_index=0,
        children=(_glass_child(with_bound=False),),
    )

    assert _glass_errors(_source(valid)) == []
    assert any(
        "intact drawable bound" in error
        for error in _glass_errors(_source(missing_bound))
    )


def test_validation_rejects_glass_child_without_intact_drawable() -> None:
    group = YftPhysicsGroup.declare_glass(
        "pane",
        pane_index=0,
        children=(YftPhysicsChild.declare(bone_id=7),),
    )

    assert any(
        "intact child drawable" in error for error in _glass_errors(_source(group))
    )


def test_validation_checks_pane_shader_against_selected_geometry() -> None:
    group = YftPhysicsGroup.declare_glass(
        "pane",
        pane_index=0,
        children=(_glass_child(),),
    )
    source = _source(group)
    source.glass_panes[0].shader_index = 1

    assert any("shader group" in error for error in _glass_errors(source))
