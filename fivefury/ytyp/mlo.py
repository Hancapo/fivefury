from __future__ import annotations

import dataclasses
from typing import Any

from ..meta import RawStruct
from ..meta.defs import meta_name
from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..ymap import EntityDef, MloInstanceDef
from .base_archetype import BaseArchetypeDef
from .flags import MloInteriorFlags, PortalFlags, RoomFlags
from .mlo_validation import build_mlo_archetype, validate_mlo_archetype


def _entity_from_meta(value: Any) -> EntityDef | MloInstanceDef | RawStruct | dict[str, Any]:
    if isinstance(value, dict) and value.get("_meta_name") == "CMloInstanceDef":
        return MloInstanceDef.from_meta(value)
    if isinstance(value, dict) and value.get("_meta_name") == "CEntityDef":
        return EntityDef.from_meta(value)
    return value


@dataclasses.dataclass(slots=True)
class MloRoomDef(MetaHashFieldsMixin):
    _hash_fields = ("timecycle_name", "secondary_timecycle_name")

    name: str = ""
    bb_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bb_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    blend: float = 0.0
    timecycle_name: MetaHash | HashLike = 0
    secondary_timecycle_name: MetaHash | HashLike = 0
    flags: RoomFlags | int = 0
    portal_count: int = 0
    floor_id: int = 0
    exterior_visibility_depth: int = 0
    attached_objects: list[int] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        self.flags = RoomFlags(int(self.flags))

    def to_meta(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bbMin": self.bb_min,
            "bbMax": self.bb_max,
            "blend": self.blend,
            "timecycleName": self.timecycle_name,
            "secondaryTimecycleName": self.secondary_timecycle_name,
            "flags": int(self.flags),
            "portalCount": self.portal_count,
            "floorId": self.floor_id,
            "exteriorVisibiltyDepth": self.exterior_visibility_depth,
            "attachedObjects": self.attached_objects,
            "_meta_name_hash": meta_name("CMloRoomDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> MloRoomDef:
        return cls(
            name=str(value.get("name", "")),
            bb_min=tuple(value.get("bbMin", (0.0, 0.0, 0.0))),
            bb_max=tuple(value.get("bbMax", (0.0, 0.0, 0.0))),
            blend=float(value.get("blend", 0.0)),
            timecycle_name=value.get("timecycleName", 0),
            secondary_timecycle_name=value.get("secondaryTimecycleName", 0),
            flags=int(value.get("flags", 0)),
            portal_count=int(value.get("portalCount", 0)),
            floor_id=int(value.get("floorId", 0)),
            exterior_visibility_depth=int(value.get("exteriorVisibiltyDepth", 0)),
            attached_objects=list(value.get("attachedObjects", []) or []),
        )


@dataclasses.dataclass(slots=True)
class MloPortalDef:
    room_from: int = 0
    room_to: int = 0
    flags: PortalFlags | int = 0
    mirror_priority: int = 0
    opacity: int = 0
    audio_occlusion: int = 0
    corners: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    attached_objects: list[int] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        self.flags = PortalFlags(int(self.flags))

    def to_meta(self) -> dict[str, Any]:
        return {
            "roomFrom": self.room_from,
            "roomTo": self.room_to,
            "flags": int(self.flags),
            "mirrorPriority": self.mirror_priority,
            "opacity": self.opacity,
            "audioOcclusion": self.audio_occlusion,
            "corners": self.corners,
            "attachedObjects": self.attached_objects,
            "_meta_name_hash": meta_name("CMloPortalDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> MloPortalDef:
        return cls(
            room_from=int(value.get("roomFrom", 0)),
            room_to=int(value.get("roomTo", 0)),
            flags=int(value.get("flags", 0)),
            mirror_priority=int(value.get("mirrorPriority", 0)),
            opacity=int(value.get("opacity", 0)),
            audio_occlusion=int(value.get("audioOcclusion", 0)),
            corners=list(value.get("corners", []) or []),
            attached_objects=list(value.get("attachedObjects", []) or []),
        )


@dataclasses.dataclass(slots=True)
class MloEntitySet(MetaHashFieldsMixin):
    _hash_fields = ("name",)

    name: MetaHash | HashLike = 0
    locations: list[int] = dataclasses.field(default_factory=list)
    entities: list[EntityDef | MloInstanceDef | RawStruct | dict[str, Any]] = dataclasses.field(default_factory=list)

    def to_meta(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "locations": self.locations,
            "entities": [entity.to_meta() if hasattr(entity, "to_meta") else entity for entity in self.entities],
            "_meta_name_hash": meta_name("CMloEntitySet"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> MloEntitySet:
        return cls(
            name=value.get("name", 0),
            locations=list(value.get("locations", []) or []),
            entities=[_entity_from_meta(item) for item in value.get("entities", []) or []],
        )


@dataclasses.dataclass(slots=True)
class MloTimeCycleModifier(MetaHashFieldsMixin):
    _hash_fields = ("name",)

    name: MetaHash | HashLike = 0
    sphere: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    percentage: float = 0.0
    range: float = 0.0
    start_hour: int = 0
    end_hour: int = 0

    def to_meta(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sphere": self.sphere,
            "percentage": self.percentage,
            "range": self.range,
            "startHour": self.start_hour,
            "endHour": self.end_hour,
            "_meta_name_hash": meta_name("CMloTimeCycleModifier"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> MloTimeCycleModifier:
        return cls(
            name=value.get("name", 0),
            sphere=tuple(value.get("sphere", (0.0, 0.0, 0.0, 0.0))),
            percentage=float(value.get("percentage", 0.0)),
            range=float(value.get("range", 0.0)),
            start_hour=int(value.get("startHour", 0)),
            end_hour=int(value.get("endHour", 0)),
        )


@dataclasses.dataclass(slots=True)
class MloArchetypeDef(BaseArchetypeDef):
    mlo_flags: MloInteriorFlags | int = 0
    entities: list[EntityDef | MloInstanceDef | RawStruct | dict[str, Any]] = dataclasses.field(default_factory=list)
    rooms: list[MloRoomDef | dict[str, Any]] = dataclasses.field(default_factory=list)
    portals: list[MloPortalDef | dict[str, Any]] = dataclasses.field(default_factory=list)
    entity_sets: list[MloEntitySet | dict[str, Any]] = dataclasses.field(default_factory=list)
    time_cycle_modifiers: list[MloTimeCycleModifier | dict[str, Any]] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.mlo_flags = MloInteriorFlags(int(self.mlo_flags))
        self.entities = [_entity_from_meta(item) for item in self.entities]
        self.rooms = [MloRoomDef.from_meta(item) if isinstance(item, dict) else item for item in self.rooms]
        self.portals = [MloPortalDef.from_meta(item) if isinstance(item, dict) else item for item in self.portals]
        self.entity_sets = [MloEntitySet.from_meta(item) if isinstance(item, dict) else item for item in self.entity_sets]
        self.time_cycle_modifiers = [
            MloTimeCycleModifier.from_meta(item) if isinstance(item, dict) else item
            for item in self.time_cycle_modifiers
        ]

    def room(self, name: str, **kwargs: Any) -> MloRoomDef:
        room = MloRoomDef(name=name, **kwargs)
        self.rooms.append(room)
        return room

    def room_index(self, room: int | str | MloRoomDef) -> int:
        if isinstance(room, int):
            if not 0 <= room < len(self.rooms):
                raise IndexError(f"MLO room index {room} is outside the room array")
            return room
        for room_index, candidate in enumerate(self.rooms):
            if candidate is room or candidate.name == room:
                return room_index
        raise KeyError(f"MLO room {room!r} does not exist")

    def portal_index(self, portal: int | MloPortalDef) -> int:
        if isinstance(portal, int):
            if not 0 <= portal < len(self.portals):
                raise IndexError(f"MLO portal index {portal} is outside the portal array")
            return portal
        for portal_index, candidate in enumerate(self.portals):
            if candidate is portal:
                return portal_index
        raise ValueError("MLO portal does not belong to this archetype")

    def collision_material(self, room: int | str | MloRoomDef, material_type: Any = 0, **kwargs: Any) -> Any:
        """Create a bound material tagged with this archetype's room index."""
        from ..bounds import BoundMaterial

        return BoundMaterial(type=material_type, room_id=self.room_index(room), **kwargs)

    def portal(
        self,
        room_from: int,
        room_to: int,
        corners: list[tuple[float, float, float]],
        **kwargs: Any,
    ) -> MloPortalDef:
        portal = MloPortalDef(room_from=room_from, room_to=room_to, corners=corners, **kwargs)
        self.portals.append(portal)
        return portal

    def entity_set(self, name: HashLike, **kwargs: Any) -> MloEntitySet:
        entity_set = MloEntitySet(name=name, **kwargs)
        self.entity_sets.append(entity_set)
        return entity_set

    def time_cycle_modifier(self, name: HashLike, **kwargs: Any) -> MloTimeCycleModifier:
        modifier = MloTimeCycleModifier(name=name, **kwargs)
        self.time_cycle_modifiers.append(modifier)
        return modifier

    def entity(
        self,
        archetype_name: HashLike,
        *,
        room: int | str | MloRoomDef | None = None,
        portal: int | MloPortalDef | None = None,
        **kwargs: Any,
    ) -> EntityDef:
        if (room is None) == (portal is None):
            raise ValueError("MLO entities require exactly one room or portal location")
        room_index = self.room_index(room) if room is not None else None
        portal_index = self.portal_index(portal) if portal is not None else None
        entity = EntityDef(archetype_name=archetype_name, **kwargs)
        entity_index = len(self.entities)
        self.entities.append(entity)
        if room_index is not None:
            self.rooms[room_index].attached_objects.append(entity_index)
        else:
            self.portals[int(portal_index)].attached_objects.append(entity_index)
        return entity

    def build(self) -> MloArchetypeDef:
        build_mlo_archetype(self)
        return self

    def validate_collision(self, ybn: Any) -> list[str]:
        from ..ybn import validate_mlo_collision

        return validate_mlo_collision(ybn, self)

    def validate(self) -> list[str]:
        return validate_mlo_archetype(self)

    def to_meta(self) -> dict[str, Any]:
        data = super().to_meta()
        data.update(
            {
                "mloFlags": int(self.mlo_flags),
                "entities": [entity.to_meta() if hasattr(entity, "to_meta") else entity for entity in self.entities],
                "rooms": [room.to_meta() if hasattr(room, "to_meta") else room for room in self.rooms],
                "portals": [portal.to_meta() if hasattr(portal, "to_meta") else portal for portal in self.portals],
                "entitySets": [entity_set.to_meta() if hasattr(entity_set, "to_meta") else entity_set for entity_set in self.entity_sets],
                "timeCycleModifiers": [modifier.to_meta() if hasattr(modifier, "to_meta") else modifier for modifier in self.time_cycle_modifiers],
                "_meta_name_hash": meta_name("CMloArchetypeDef"),
            }
        )
        return data

    @classmethod
    def from_meta(cls, value: Any) -> MloArchetypeDef:
        base = BaseArchetypeDef.from_meta(value)
        return cls(
            **dataclasses.asdict(base),
            mlo_flags=int(value.get("mloFlags", 0)),
            entities=[_entity_from_meta(item) for item in value.get("entities", []) or []],
            rooms=[MloRoomDef.from_meta(item) if isinstance(item, dict) else item for item in value.get("rooms", []) or []],
            portals=[MloPortalDef.from_meta(item) if isinstance(item, dict) else item for item in value.get("portals", []) or []],
            entity_sets=[MloEntitySet.from_meta(item) if isinstance(item, dict) else item for item in value.get("entitySets", []) or []],
            time_cycle_modifiers=[MloTimeCycleModifier.from_meta(item) if isinstance(item, dict) else item for item in value.get("timeCycleModifiers", []) or []],
        )


MloArchetype = MloArchetypeDef
Room = MloRoomDef
Portal = MloPortalDef
EntitySet = MloEntitySet
MloTimeModifier = MloTimeCycleModifier
