from __future__ import annotations

import pytest

from fivefury.bounds import BoundMaterialType, build_bound_from_triangles
from fivefury.ybn import Ybn
from fivefury.ymap import EntityDef, MloInstanceDef, Ymap
from fivefury.ytyp import (
    MloArchetypeDef,
    MloInteriorFlags,
    PortalFlags,
    RoomFlags,
    Ytyp,
)
from fivefury.ytyp.mlo_validation import PORTAL_LOCATION_BIT, exit_portal_count

PORTAL_CORNERS = [
    (0.0, 0.0, 0.0),
    (0.0, 2.0, 0.0),
    (0.0, 2.0, 3.0),
    (0.0, 0.0, 3.0),
]


def _valid_mlo_ytyp() -> tuple[Ytyp, MloArchetypeDef]:
    ytyp = Ytyp(name="test_ityp")
    mlo = ytyp.mlo_archetype("test_mlo", mlo_flags=MloInteriorFlags.ALLOW_RUN)
    mlo.room(
        "limbo",
        bb_min=(-5.0, -5.0, -1.0),
        bb_max=(5.0, 5.0, 4.0),
        flags=RoomFlags.NO_EXTERIOR_LIGHTS,
    )
    mlo.room("main", bb_min=(0.0, 0.0, 0.0), bb_max=(10.0, 10.0, 4.0))
    mlo.entity("shell_prop", room=0)
    mlo.entity("interior_prop", room=1)
    mlo.portal(0, 1, PORTAL_CORNERS, flags=PortalFlags.ALLOW_CLOSING)
    mlo.entity_set(
        "optional_props",
        locations=[1, PORTAL_LOCATION_BIT],
        entities=[EntityDef("optional_room_prop"), EntityDef("optional_portal_prop")],
    )
    mlo.time_cycle_modifier(
        "test_timecycle",
        sphere=(5.0, 5.0, 2.0, 10.0),
        percentage=1.0,
        range=10.0,
        start_hour=0,
        end_hour=23,
    )
    return ytyp, mlo


def _valid_mlo_ybn(mlo: MloArchetypeDef, *, room: int | str = "main") -> Ybn:
    bound = build_bound_from_triangles(
        [
            (
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
            )
        ],
        material=mlo.collision_material(room, BoundMaterialType.CONCRETE),
    )
    return Ybn.from_bound(bound, path="test_mlo.ybn")


def test_mlo_build_synchronizes_room_portal_counts() -> None:
    ytyp, mlo = _valid_mlo_ytyp()
    assert [room.portal_count for room in mlo.rooms] == [0, 0]

    ytyp.build()

    assert [room.portal_count for room in mlo.rooms] == [1, 1]
    assert ytyp.validate() == []


def test_mlo_link_portals_are_not_exit_portals() -> None:
    _, mlo = _valid_mlo_ytyp()
    mlo.portal(0, 1, PORTAL_CORNERS, flags=PortalFlags.LINK)

    assert exit_portal_count(mlo) == 1


def test_mlo_ytyp_binary_roundtrip_preserves_explicit_structures() -> None:
    ytyp, _ = _valid_mlo_ytyp()

    parsed = Ytyp.from_bytes(ytyp.to_bytes())
    parsed_mlo = parsed.archetypes[0]

    assert isinstance(parsed_mlo, MloArchetypeDef)
    assert parsed_mlo.mlo_flags is MloInteriorFlags.ALLOW_RUN
    assert parsed_mlo.rooms[0].flags is RoomFlags.NO_EXTERIOR_LIGHTS
    assert parsed_mlo.portals[0].flags is PortalFlags.ALLOW_CLOSING
    assert [room.portal_count for room in parsed_mlo.rooms] == [1, 1]
    assert parsed.validate() == []


def test_mlo_validation_rejects_runtime_unsafe_graphs() -> None:
    _, mlo = _valid_mlo_ytyp()
    mlo.portals[0].room_to = 5
    mlo.portals[0].corners.pop()
    mlo.rooms[1].attached_objects.clear()
    mlo.entity_sets[0].locations = [PORTAL_LOCATION_BIT | 5]

    issues = mlo.validate()

    assert any("room_to=5 is outside the room array" in issue for issue in issues)
    assert any("exactly four corners" in issue for issue in issues)
    assert any("entities[1] is not attached" in issue for issue in issues)
    assert any("has 1 locations for 2 entities" in issue for issue in issues)
    assert any("references portal 5" in issue for issue in issues)


def test_mlo_writer_rejects_missing_room_zero() -> None:
    ytyp = Ytyp(name="broken_ityp", archetypes=[MloArchetypeDef(name="broken_mlo")])

    with pytest.raises(ValueError, match="room 0 is required"):
        ytyp.to_bytes()


def test_mlo_declarative_entity_rejects_invalid_locations() -> None:
    _, mlo = _valid_mlo_ytyp()

    with pytest.raises(IndexError, match="room index 5"):
        mlo.entity("invalid_prop", room=5)
    with pytest.raises(ValueError, match="exactly one room or portal"):
        mlo.entity("invalid_prop")


def test_mlo_declarative_objects_resolve_rooms_portals_and_instances() -> None:
    ytyp, mlo = _valid_mlo_ytyp()
    room = mlo.rooms[1]
    portal = mlo.portals[0]

    room_entity = mlo.entity("room_object", room=room)
    portal_entity = mlo.entity("portal_object", portal=portal)
    ymap = Ymap(name="test_imap")
    instance = ymap.mlo_instance(mlo)

    assert mlo.entities.index(room_entity) in room.attached_objects
    assert mlo.entities.index(portal_entity) in portal.attached_objects
    assert int(instance.archetype_name) == int(mlo.name)
    ymap.build(ytyps=ytyp)
    assert ymap.validate(ytyps=ytyp) == []


def test_mlo_writer_rejects_room_zero_capacity_overflow() -> None:
    ytyp, mlo = _valid_mlo_ytyp()
    mlo.rooms[0].attached_objects = list(range(12))
    mlo.entities = [EntityDef(f"prop_{index}") for index in range(12)]

    with pytest.raises(ValueError, match="supports at most 11"):
        ytyp.to_bytes()


def test_ymap_cross_validation_builds_exit_portals_and_checks_entity_sets() -> None:
    ytyp, mlo = _valid_mlo_ytyp()
    ymap = Ymap(name="test_imap")
    instance = ymap.mlo_instance(
        "test_mlo",
        group_id=1,
        num_exit_portals=99,
        default_entity_sets=["optional_props"],
    )

    ybn = _valid_mlo_ybn(mlo)
    data = ymap.to_bytes(ytyps=ytyp, ybns={"test_mlo": ybn})
    parsed = Ymap.from_bytes(data)

    assert instance.num_exit_portals == 1
    assert [int(item.name) for item in ymap.physics_dictionaries] == [int(mlo.physics_dictionary)]
    assert isinstance(parsed.entities[0], MloInstanceDef)
    assert parsed.entities[0].num_exit_portals == 1
    assert parsed.validate(ytyps=ytyp, ybns={"test_mlo": ybn}) == []


def test_mlo_physics_dictionary_and_static_bound_keep_distinct_names() -> None:
    ytyp, mlo = _valid_mlo_ytyp()
    mlo.physics_dictionary = "custom_collision_group"
    ybn = _valid_mlo_ybn(mlo)
    ymap = Ymap(name="test_imap")
    ymap.mlo_instance(mlo)

    ymap.to_bytes(ytyps=ytyp, ybns={mlo.name: ybn})

    assert [int(item.name) for item in ymap.physics_dictionaries] == [
        int(mlo.physics_dictionary)
    ]
    assert int(mlo.physics_dictionary) != int(mlo.name)
    assert ymap.validate(ytyps=ytyp, ybns={mlo.name: ybn}) == []


def test_ymap_cross_validation_rejects_missing_archetypes_and_sets() -> None:
    ytyp, _ = _valid_mlo_ytyp()
    instance = MloInstanceDef(
        archetype_name="test_mlo",
        group_id=255,
        default_entity_sets=["missing_set"],
    )
    ymap = Ymap(name="test_imap", entities=[instance])

    issues = ymap.validate(ytyps=ytyp)

    assert any("group_id must be between 0 and 254" in issue for issue in issues)
    assert any("unknown default entity set" in issue for issue in issues)

    missing_issues = ymap.validate(ytyps=Ytyp(name="other_ityp"))
    assert any("absent from the supplied YTYPs" in issue for issue in missing_issues)


def test_mlo_collision_uses_material_room_ids_and_archetype_filename() -> None:
    _, mlo = _valid_mlo_ytyp()
    ybn = _valid_mlo_ybn(mlo)

    assert ybn.room_ids == {1}
    assert mlo.validate_collision(ybn) == []

    ybn.set_room(2)
    ybn.path = "wrong_name.ybn"
    issues = mlo.validate_collision(ybn)

    assert any("uses room_id 2" in issue for issue in issues)
    assert any("must match the archetype name" in issue for issue in issues)


def test_ymap_mlo_validation_requires_supplied_static_bound() -> None:
    ytyp, _ = _valid_mlo_ytyp()
    ymap = Ymap(name="test_imap")
    ymap.mlo_instance("test_mlo")
    ymap.build(ytyps=ytyp)

    issues = ymap.validate(ytyps=ytyp, ybns={})

    assert any("has no YBN static bound" in issue for issue in issues)


def test_ymap_mlo_extents_use_transformed_archetype_bounds() -> None:
    ytyp, mlo = _valid_mlo_ytyp()
    mlo.bb_min = (-5.0, -5.0, -1.0)
    mlo.bb_max = (5.0, 5.0, 4.0)
    ymap = Ymap(name="test_imap")
    ymap.mlo_instance("test_mlo", position=(100.0, 200.0, 10.0))

    ymap.recalculate_extents(ytyps=ytyp, streaming_margin=0.0, include_lod_distance=False)

    assert ymap.entities_extents_min == (95.0, 195.0, 9.0)
    assert ymap.entities_extents_max == (105.0, 205.0, 14.0)
