from __future__ import annotations

import dataclasses
from typing import Any

from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta import RawStruct
from ..meta.defs import meta_name
from ..ymap import EntityDef, MloInstanceDef

from .archetypes import BaseArchetypeDef


@dataclasses.dataclass(slots=True)
class MloRoomDef(MetaHashFieldsMixin):
    _hash_fields = ("timecycle_name", "secondary_timecycle_name")

    name: str = ""
    bb_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bb_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    blend: float = 0.0
    timecycle_name: MetaHash | HashLike = 0
    secondary_timecycle_name: MetaHash | HashLike = 0
    flags: int = 0
    portal_count: int = 0
    floor_id: int = 0
    exterior_visibility_depth: int = 0
    attached_objects: list[int] = dataclasses.field(default_factory=list)

    def to_meta(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bbMin": self.bb_min,
            "bbMax": self.bb_max,
            "blend": self.blend,
            "timecycleName": self.timecycle_name,
            "secondaryTimecycleName": self.secondary_timecycle_name,
            "flags": self.flags,
            "portalCount": self.portal_count,
            "floorId": self.floor_id,
            "exteriorVisibiltyDepth": self.exterior_visibility_depth,
            "attachedObjects": self.attached_objects,
            "_meta_name_hash": meta_name("CMloRoomDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "MloRoomDef":
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
    flags: int = 0
    mirror_priority: int = 0
    opacity: int = 0
    audio_occlusion: int = 0
    corners: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    attached_objects: list[int] = dataclasses.field(default_factory=list)

    def to_meta(self) -> dict[str, Any]:
        return {
            "roomFrom": self.room_from,
            "roomTo": self.room_to,
            "flags": self.flags,
            "mirrorPriority": self.mirror_priority,
            "opacity": self.opacity,
            "audioOcclusion": self.audio_occlusion,
            "corners": self.corners,
            "attachedObjects": self.attached_objects,
            "_meta_name_hash": meta_name("CMloPortalDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "MloPortalDef":
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
    def from_meta(cls, value: Any) -> "MloEntitySet":
        entities: list[Any] = []
        for item in value.get("entities", []) or []:
            if isinstance(item, dict) and item.get("_meta_name") == "CMloInstanceDef":
                entities.append(MloInstanceDef.from_meta(item))
            elif isinstance(item, dict) and item.get("_meta_name") == "CEntityDef":
                entities.append(EntityDef.from_meta(item))
            else:
                entities.append(item)
        return cls(name=value.get("name", 0), locations=list(value.get("locations", []) or []), entities=entities)


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
    def from_meta(cls, value: Any) -> "MloTimeCycleModifier":
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
    mlo_flags: int = 0
    entities: list[EntityDef | MloInstanceDef | RawStruct | dict[str, Any]] = dataclasses.field(default_factory=list)
    rooms: list[MloRoomDef | dict[str, Any]] = dataclasses.field(default_factory=list)
    portals: list[MloPortalDef | dict[str, Any]] = dataclasses.field(default_factory=list)
    entity_sets: list[MloEntitySet | dict[str, Any]] = dataclasses.field(default_factory=list)
    time_cycle_modifiers: list[MloTimeCycleModifier | dict[str, Any]] = dataclasses.field(default_factory=list)

    def to_meta(self) -> dict[str, Any]:
        data = super().to_meta()
        data.update(
            {
                "mloFlags": self.mlo_flags,
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
    def from_meta(cls, value: Any) -> "MloArchetypeDef":
        base = BaseArchetypeDef.from_meta(value)
        entities: list[Any] = []
        for item in value.get("entities", []) or []:
            if isinstance(item, dict) and item.get("_meta_name") == "CMloInstanceDef":
                entities.append(MloInstanceDef.from_meta(item))
            elif isinstance(item, dict) and item.get("_meta_name") == "CEntityDef":
                entities.append(EntityDef.from_meta(item))
            else:
                entities.append(item)
        return cls(
            **dataclasses.asdict(base),
            mlo_flags=int(value.get("mloFlags", 0)),
            entities=entities,
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
