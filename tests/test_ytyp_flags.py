from fivefury import (
    ArchetypeAssetType,
    ArchetypeFlags,
    BaseArchetypeDef,
    Ytyp,
    cutscene_prop_flags,
    infer_archetype_lod_dist,
    mark_cutscene_prop_archetypes,
)


def test_archetype_flags_match_cbasearchetypedef_load_flags() -> None:
    assert ArchetypeFlags.IS_FIXED == 1 << 5
    assert ArchetypeFlags.HAS_ANIM == 1 << 9
    assert ArchetypeFlags.HAS_UVANIM == 1 << 10
    assert ArchetypeFlags.IS_TYPE_OBJECT == 1 << 17
    assert ArchetypeFlags.OVERRIDE_PHYSICS_BOUNDS == 1 << 18
    assert ArchetypeFlags.DOOR_PHYSICS == 1 << 26
    assert ArchetypeFlags.DONT_AVOID_BY_PEDS == 1 << 28
    assert ArchetypeFlags.HAS_ALPHA_SHADOW == 1 << 31


def test_base_archetype_flags_roundtrip_as_int() -> None:
    flags = ArchetypeFlags.IS_FIXED | ArchetypeFlags.HAS_ANIM | ArchetypeFlags.HAS_UVANIM
    archetype = BaseArchetypeDef(name="test_arch", flags=int(flags))

    meta = archetype.to_meta()

    assert meta["flags"] == int(flags)

    parsed = BaseArchetypeDef.from_meta(meta)
    assert parsed.flags == int(flags)


def test_cutscene_prop_flags_match_retail_cutscene_props() -> None:
    assert cutscene_prop_flags() == (ArchetypeFlags.IS_TYPE_OBJECT | ArchetypeFlags.USE_AMBIENT_SCALE)
    assert cutscene_prop_flags(animated=False) == ArchetypeFlags.IS_TYPE_OBJECT


def test_mark_cutscene_prop_archetypes_can_target_specific_assets() -> None:
    ytyp = Ytyp(name="sample_meta")
    animated = ytyp.archetype(
        "animated_prop",
        asset_type=ArchetypeAssetType.DRAWABLE,
        flags=int(ArchetypeFlags.HAS_ANIM),
    )
    static = ytyp.archetype("static_prop", asset_type=ArchetypeAssetType.DRAWABLE)

    mark_cutscene_prop_archetypes(ytyp, names=["animated_prop"])

    assert animated.flags == int(ArchetypeFlags.IS_TYPE_OBJECT | ArchetypeFlags.USE_AMBIENT_SCALE)
    assert static.flags == 0


def test_base_archetype_asset_type_roundtrips_as_enum() -> None:
    archetype = BaseArchetypeDef(name="test_arch", asset_type=ArchetypeAssetType.DRAWABLE)

    meta = archetype.to_meta()

    assert meta["assetType"] == int(ArchetypeAssetType.DRAWABLE)

    parsed = BaseArchetypeDef.from_meta(meta)
    assert parsed.asset_type is ArchetypeAssetType.DRAWABLE


def test_archetype_defaults_infer_visible_lod_dist_from_bounds() -> None:
    archetype = BaseArchetypeDef(
        name="test_arch",
        bs_radius=12.0,
        bb_min=(-12.0, -12.0, -2.0),
        bb_max=(12.0, 12.0, 2.0),
        asset_type=ArchetypeAssetType.DRAWABLE,
    )

    assert archetype.lod_dist == 100.0
    assert archetype.hd_texture_dist == 50.0


def test_archetype_lod_default_scales_for_large_bounds() -> None:
    archetype = BaseArchetypeDef(
        name="test_large_arch",
        bs_radius=80.0,
        asset_type=ArchetypeAssetType.DRAWABLE,
    )

    assert archetype.lod_dist == 240.0
    assert archetype.hd_texture_dist == 120.0


def test_archetype_lod_can_be_inferred_from_aabb_when_radius_missing() -> None:
    lod_dist = infer_archetype_lod_dist(
        bb_min=(-10.0, -10.0, -10.0),
        bb_max=(10.0, 10.0, 10.0),
    )

    assert lod_dist == 100.0


def test_archetype_from_meta_preserves_explicit_zero_lod_distances() -> None:
    parsed = BaseArchetypeDef.from_meta(
        {
            "name": "raw_arch",
            "assetType": int(ArchetypeAssetType.DRAWABLE),
            "lodDist": 0.0,
            "hdTextureDist": 0.0,
            "bsRadius": 12.0,
            "bbMin": (-12.0, -12.0, -2.0),
            "bbMax": (12.0, 12.0, 2.0),
        }
    )

    assert parsed.lod_dist == 0.0
    assert parsed.hd_texture_dist == 0.0
