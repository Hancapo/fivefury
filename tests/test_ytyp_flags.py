from fivefury import ArchetypeFlags, BaseArchetypeDef


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
