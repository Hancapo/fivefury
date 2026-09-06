import itertools
import math

import numpy as np
import pytest

from fivefury import (
    Aabb3,
    AssetSet,
    BuildContext,
    GameTarget,
    Quaternion,
    Vector3,
    YmapEntityFlags,
)
from fivefury.ymap import EntityDef, MloInstanceDef, Ymap
from fivefury.ytyp import (
    ArchetypeAssetType,
    ArchetypeFlags,
    BaseArchetypeDef,
    MloArchetypeDef,
    Ytyp,
)


def matrix(rotation):
    # Independent unit-quaternion matrix oracle for asymmetric bounds.
    x, y, z, w = rotation
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize("mlo", [False, True])
def test_asymmetric_offcentre_extents_decode_ordinary_and_mlo_separately(game, mlo):
    rotation = Quaternion.from_euler_xyz(Vector3(0.4, -0.6, 0.9))
    minimum, maximum = Vector3(-3, 1, -2), Vector3(7, 4, 6)
    archetype = (MloArchetypeDef if mlo else BaseArchetypeDef)(
        name="asymmetric",
        bb_min=minimum,
        bb_max=maximum,
        asset_type=ArchetypeAssetType.DRAWABLE,
    )
    entity = (MloInstanceDef if mlo else EntityDef)(
        archetype_name="asymmetric",
        position=Vector3(25, -11, 30),
        rotation=rotation,
        scale_xy=1.7,
        scale_z=0.6,
        lod_dist=35,
    )
    before = entity.to_meta()
    assets = AssetSet()
    assets["asymmetric.ytyp"] = Ytyp(name="asymmetric", archetypes=[archetype])
    ymap = Ymap(name="placed", entities=[entity])
    ymap.recalculate_extents(
        context=BuildContext(assets=assets, game=game), streaming_margin=5
    )
    transform = matrix(rotation)
    if not mlo:
        transform = transform.T @ np.diag([1.7, 1.7, 0.6])
    corners = np.array(list(itertools.product(*zip(minimum, maximum, strict=True))))
    world = corners @ transform.T + np.array(tuple(entity.position))
    expected_min, expected_max = world.min(axis=0), world.max(axis=0)
    assert ymap.entities_extents_min.components == pytest.approx(expected_min)
    assert ymap.entities_extents_max.components == pytest.approx(expected_max)
    assert ymap.streaming_extents_min.components == pytest.approx(expected_min - 40)
    assert ymap.streaming_extents_max.components == pytest.approx(expected_max + 40)
    assert entity.to_meta() == before


@pytest.mark.parametrize(
    "flags,animated,full",
    [
        (0, False, False),
        (YmapEntityFlags.FULLMATRIX, False, True),
        (0, True, True),
    ],
)
def test_small_tilt_uses_heading_unless_full_matrix_is_required(flags, animated, full):
    rotation = Quaternion.from_euler_xyz(Vector3(0.025, -0.035, 0.8))
    entity = EntityDef(rotation=rotation, flags=flags)
    archetype = BaseArchetypeDef(
        clip_dictionary="movement" if animated else 0,
        flags=ArchetypeFlags.HAS_ANIM if animated else 0,
    )
    result = entity.world_rotation(archetype)
    if full:
        assert matrix(result) == pytest.approx(matrix(rotation).T)
    else:
        heading = -2 * math.acos(rotation.w)
        assert matrix(result) == pytest.approx(
            np.array(
                [
                    [math.cos(heading), -math.sin(heading), 0],
                    [math.sin(heading), math.cos(heading), 0],
                    [0, 0, 1],
                ]
            )
        )
        assert result.x == result.y == 0


@pytest.mark.parametrize(
    "x,full", [(0.049, False), (0.05000000074505806, False), (0.051, True)]
)
def test_fullmatrix_threshold_matches_runtime_strict_comparison(x, full):
    rotation = Quaternion(x, 0, 0.2, math.sqrt(1 - x * x - 0.04))
    result = EntityDef(rotation=rotation).world_rotation()
    assert (abs(result.x) > 0) is full


@pytest.mark.parametrize(
    "asset_type,scale",
    [
        (ArchetypeAssetType.DRAWABLE, Vector3(2, 2, 3)),
        (ArchetypeAssetType.FRAGMENT, Vector3(1, 1, 1)),
    ],
)
def test_fragment_placement_ignores_definition_scale(asset_type, scale):
    entity = EntityDef(scale_xy=2, scale_z=3)
    archetype = BaseArchetypeDef(asset_type=asset_type)
    assert entity.world_scale(archetype) == scale
    bounds = entity.world_bounds(Aabb3(Vector3(1, 2, 3), Vector3(4, 5, 6)), archetype)
    assert bounds.minimum == Vector3(scale.x, 2 * scale.y, 3 * scale.z)


def test_simple_heading_identity_and_sign():
    assert (
        EntityDef(rotation=Quaternion(0.01, 0.02, 0.03, 1)).world_rotation()
        == Quaternion()
    )
    for z in (-0.6, 0.6):
        stored = Quaternion(0, 0, z, 0.8)
        assert matrix(EntityDef(rotation=stored).world_rotation()) == pytest.approx(
            matrix(stored).T
        )


def test_animation_flag_without_clip_dictionary_keeps_simple_transform():
    entity = EntityDef(rotation=Quaternion.from_euler_xyz(Vector3(0.02, 0.01, 0.4)))
    result = entity.world_rotation(BaseArchetypeDef(flags=ArchetypeFlags.HAS_ANIM))
    assert result.x == result.y == 0
