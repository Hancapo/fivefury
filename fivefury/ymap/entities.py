from __future__ import annotations

import dataclasses
from typing import Any

from ..extensions import extensions_from_meta, extensions_to_meta
from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta.defs import meta_name


@dataclasses.dataclass(slots=True)
class EntityDef(MetaHashFieldsMixin):
    _hash_fields = ("archetype_name",)

    archetype_name: MetaHash | HashLike = 0
    flags: int = 0
    guid: int = 0
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    scale_xy: float = 1.0
    scale_z: float = 1.0
    parent_index: int = -1
    lod_dist: float = 0.0
    child_lod_dist: float = 0.0
    lod_level: int = 0
    num_children: int = 0
    priority_level: int = 0
    extensions: list[Any] = dataclasses.field(default_factory=list)
    ambient_occlusion_multiplier: int = 255
    artificial_ambient_occlusion: int = 255
    tint_value: int = 0

    def add_extension(self, extension: Any) -> Any:
        self.extensions.append(extension)
        return extension

    def to_meta(self) -> dict[str, Any]:
        return {
            "archetypeName": self.archetype_name,
            "flags": self.flags,
            "guid": self.guid,
            "position": self.position,
            "rotation": self.rotation,
            "scaleXY": self.scale_xy,
            "scaleZ": self.scale_z,
            "parentIndex": self.parent_index,
            "lodDist": self.lod_dist,
            "childLodDist": self.child_lod_dist,
            "lodLevel": self.lod_level,
            "numChildren": self.num_children,
            "priorityLevel": self.priority_level,
            "extensions": extensions_to_meta(self.extensions),
            "ambientOcclusionMultiplier": self.ambient_occlusion_multiplier,
            "artificialAmbientOcclusion": self.artificial_ambient_occlusion,
            "tintValue": self.tint_value,
            "_meta_name_hash": meta_name("CEntityDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "EntityDef":
        return cls(
            archetype_name=value.get("archetypeName", 0),
            flags=int(value.get("flags", 0)),
            guid=int(value.get("guid", 0)),
            position=tuple(value.get("position", (0.0, 0.0, 0.0))),
            rotation=tuple(value.get("rotation", (0.0, 0.0, 0.0, 1.0))),
            scale_xy=float(value.get("scaleXY", 1.0)),
            scale_z=float(value.get("scaleZ", 1.0)),
            parent_index=int(value.get("parentIndex", -1)),
            lod_dist=float(value.get("lodDist", 0.0)),
            child_lod_dist=float(value.get("childLodDist", 0.0)),
            lod_level=int(value.get("lodLevel", 0)),
            num_children=int(value.get("numChildren", 0)),
            priority_level=int(value.get("priorityLevel", 0)),
            extensions=extensions_from_meta(value.get("extensions", []) or []),
            ambient_occlusion_multiplier=int(value.get("ambientOcclusionMultiplier", 255)),
            artificial_ambient_occlusion=int(value.get("artificialAmbientOcclusion", 255)),
            tint_value=int(value.get("tintValue", 0)),
        )


@dataclasses.dataclass(slots=True)
class MloInstanceDef(EntityDef):
    _hash_list_fields = ("default_entity_sets",)

    group_id: int = 0
    floor_id: int = 0
    default_entity_sets: list[MetaHash | HashLike] = dataclasses.field(default_factory=list)
    num_exit_portals: int = 0
    mlo_inst_flags: int = 0

    def to_meta(self) -> dict[str, Any]:
        data = super().to_meta()
        data.update(
            {
                "groupId": self.group_id,
                "floorId": self.floor_id,
                "defaultEntitySets": self.default_entity_sets,
                "numExitPortals": self.num_exit_portals,
                "MLOInstflags": self.mlo_inst_flags,
                "_meta_name_hash": meta_name("CMloInstanceDef"),
            }
        )
        return data

    @classmethod
    def from_meta(cls, value: Any) -> "MloInstanceDef":
        base = EntityDef.from_meta(value)
        return cls(
            archetype_name=base.archetype_name,
            flags=base.flags,
            guid=base.guid,
            position=base.position,
            rotation=base.rotation,
            scale_xy=base.scale_xy,
            scale_z=base.scale_z,
            parent_index=base.parent_index,
            lod_dist=base.lod_dist,
            child_lod_dist=base.child_lod_dist,
            lod_level=base.lod_level,
            num_children=base.num_children,
            priority_level=base.priority_level,
            extensions=base.extensions,
            ambient_occlusion_multiplier=base.ambient_occlusion_multiplier,
            artificial_ambient_occlusion=base.artificial_ambient_occlusion,
            tint_value=base.tint_value,
            group_id=int(value.get("groupId", 0)),
            floor_id=int(value.get("floorId", 0)),
            default_entity_sets=list(value.get("defaultEntitySets", []) or []),
            num_exit_portals=int(value.get("numExitPortals", 0)),
            mlo_inst_flags=int(value.get("MLOInstflags", 0)),
        )
