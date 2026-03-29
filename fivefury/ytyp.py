from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .extensions import EXTENSION_STRUCT_INFOS, extensions_from_meta, extensions_to_meta
from .metahash import HashLike, MetaHash, MetaHashFieldsMixin
from .meta import Meta, MetaBuilder, MetaEnumEntry, MetaEnumInfo, MetaFieldInfo, MetaStructInfo, RawStruct, read_meta
from .meta_defs import META_TYPE_NAME_ARRAYINFO, KNOWN_ENUMS, MetaDataType, meta_name
from .resource import build_rsc7
from .ymap import EntityDef, MloInstanceDef, _arrayinfo, _ensure_base_name, _entry, _enum_info, _suggest_resource_path

if TYPE_CHECKING:  # pragma: no cover
    from .rpf import RpfArchive, RpfFileEntry


YTYP_STRUCT_INFOS = [
    MetaStructInfo(
        name_hash=meta_name("CBaseArchetypeDef"),
        key=2411387556,
        unknown=1024,
        structure_size=144,
        entries=[
            _entry("lodDist", 8, MetaDataType.FLOAT),
            _entry("flags", 12, MetaDataType.UNSIGNED_INT),
            _entry("specialAttribute", 16, MetaDataType.UNSIGNED_INT),
            _entry("bbMin", 32, MetaDataType.FLOAT_XYZ),
            _entry("bbMax", 48, MetaDataType.FLOAT_XYZ),
            _entry("bsCentre", 64, MetaDataType.FLOAT_XYZ),
            _entry("bsRadius", 80, MetaDataType.FLOAT),
            _entry("hdTextureDist", 84, MetaDataType.FLOAT),
            _entry("name", 88, MetaDataType.HASH),
            _entry("textureDictionary", 92, MetaDataType.HASH),
            _entry("clipDictionary", 96, MetaDataType.HASH),
            _entry("drawableDictionary", 100, MetaDataType.HASH),
            _entry("physicsDictionary", 104, MetaDataType.HASH),
            _entry("assetType", 108, MetaDataType.INT_ENUM, ref_key="rage__fwArchetypeDef__eAssetType"),
            _entry("assetName", 112, MetaDataType.HASH),
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("extensions", 120, MetaDataType.ARRAY, ref_index=15),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CTimeArchetypeDef"),
        key=2520619910,
        unknown=1024,
        structure_size=160,
        entries=[
            _entry("lodDist", 8, MetaDataType.FLOAT),
            _entry("flags", 12, MetaDataType.UNSIGNED_INT),
            _entry("specialAttribute", 16, MetaDataType.UNSIGNED_INT),
            _entry("bbMin", 32, MetaDataType.FLOAT_XYZ),
            _entry("bbMax", 48, MetaDataType.FLOAT_XYZ),
            _entry("bsCentre", 64, MetaDataType.FLOAT_XYZ),
            _entry("bsRadius", 80, MetaDataType.FLOAT),
            _entry("hdTextureDist", 84, MetaDataType.FLOAT),
            _entry("name", 88, MetaDataType.HASH),
            _entry("textureDictionary", 92, MetaDataType.HASH),
            _entry("clipDictionary", 96, MetaDataType.HASH),
            _entry("drawableDictionary", 100, MetaDataType.HASH),
            _entry("physicsDictionary", 104, MetaDataType.HASH),
            _entry("assetType", 108, MetaDataType.INT_ENUM, ref_key="rage__fwArchetypeDef__eAssetType"),
            _entry("assetName", 112, MetaDataType.HASH),
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("extensions", 120, MetaDataType.ARRAY, ref_index=15),
            _entry("timeFlags", 144, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CMloRoomDef"),
        key=3885428245,
        unknown=1024,
        structure_size=112,
        entries=[
            _entry("name", 8, MetaDataType.CHAR_POINTER),
            _entry("bbMin", 32, MetaDataType.FLOAT_XYZ),
            _entry("bbMax", 48, MetaDataType.FLOAT_XYZ),
            _entry("blend", 64, MetaDataType.FLOAT),
            _entry("timecycleName", 68, MetaDataType.HASH),
            _entry("secondaryTimecycleName", 72, MetaDataType.HASH),
            _entry("flags", 76, MetaDataType.UNSIGNED_INT),
            _entry("portalCount", 80, MetaDataType.UNSIGNED_INT),
            _entry("floorId", 84, MetaDataType.SIGNED_INT),
            _entry("exteriorVisibiltyDepth", 88, MetaDataType.SIGNED_INT),
            _arrayinfo(MetaDataType.UNSIGNED_INT),
            _entry("attachedObjects", 96, MetaDataType.ARRAY, ref_index=10),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CMloPortalDef"),
        key=1110221513,
        unknown=768,
        structure_size=64,
        entries=[
            _entry("roomFrom", 8, MetaDataType.UNSIGNED_INT),
            _entry("roomTo", 12, MetaDataType.UNSIGNED_INT),
            _entry("flags", 16, MetaDataType.UNSIGNED_INT),
            _entry("mirrorPriority", 20, MetaDataType.UNSIGNED_INT),
            _entry("opacity", 24, MetaDataType.UNSIGNED_INT),
            _entry("audioOcclusion", 28, MetaDataType.UNSIGNED_INT),
            _arrayinfo(MetaDataType.FLOAT_XYZ),
            _entry("corners", 32, MetaDataType.ARRAY, ref_index=6),
            _arrayinfo(MetaDataType.UNSIGNED_INT),
            _entry("attachedObjects", 48, MetaDataType.ARRAY, ref_index=8),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CMloEntitySet"),
        key=4180211587,
        unknown=768,
        structure_size=48,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _arrayinfo(MetaDataType.UNSIGNED_INT),
            _entry("locations", 16, MetaDataType.ARRAY, ref_index=1),
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("entities", 32, MetaDataType.ARRAY, ref_index=3),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CMloTimeCycleModifier"),
        key=838874674,
        unknown=1024,
        structure_size=48,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("sphere", 16, MetaDataType.FLOAT_XYZW),
            _entry("percentage", 32, MetaDataType.FLOAT),
            _entry("range", 36, MetaDataType.FLOAT),
            _entry("startHour", 40, MetaDataType.UNSIGNED_INT),
            _entry("endHour", 44, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CMloArchetypeDef"),
        key=937664754,
        unknown=1024,
        structure_size=240,
        entries=[
            _entry("lodDist", 8, MetaDataType.FLOAT),
            _entry("flags", 12, MetaDataType.UNSIGNED_INT),
            _entry("specialAttribute", 16, MetaDataType.UNSIGNED_INT),
            _entry("bbMin", 32, MetaDataType.FLOAT_XYZ),
            _entry("bbMax", 48, MetaDataType.FLOAT_XYZ),
            _entry("bsCentre", 64, MetaDataType.FLOAT_XYZ),
            _entry("bsRadius", 80, MetaDataType.FLOAT),
            _entry("hdTextureDist", 84, MetaDataType.FLOAT),
            _entry("name", 88, MetaDataType.HASH),
            _entry("textureDictionary", 92, MetaDataType.HASH),
            _entry("clipDictionary", 96, MetaDataType.HASH),
            _entry("drawableDictionary", 100, MetaDataType.HASH),
            _entry("physicsDictionary", 104, MetaDataType.HASH),
            _entry("assetType", 108, MetaDataType.INT_ENUM, ref_key="rage__fwArchetypeDef__eAssetType"),
            _entry("assetName", 112, MetaDataType.HASH),
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("extensions", 120, MetaDataType.ARRAY, ref_index=15),
            _entry("mloFlags", 144, MetaDataType.UNSIGNED_INT),
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("entities", 152, MetaDataType.ARRAY, ref_index=18),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CMloRoomDef"),
            _entry("rooms", 168, MetaDataType.ARRAY, ref_index=20),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CMloPortalDef"),
            _entry("portals", 184, MetaDataType.ARRAY, ref_index=22),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CMloEntitySet"),
            _entry("entitySets", 200, MetaDataType.ARRAY, ref_index=24),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CMloTimeCycleModifier"),
            _entry("timeCycleModifiers", 216, MetaDataType.ARRAY, ref_index=26),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CMapTypes"),
        key=2608875220,
        unknown=768,
        structure_size=80,
        entries=[
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("extensions", 8, MetaDataType.ARRAY, ref_index=0),
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("archetypes", 24, MetaDataType.ARRAY, ref_index=2),
            _entry("name", 40, MetaDataType.HASH),
            _arrayinfo(MetaDataType.HASH),
            _entry("dependencies", 48, MetaDataType.ARRAY, ref_index=5),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CCompositeEntityType"),
            _entry("compositeEntityTypes", 64, MetaDataType.ARRAY, ref_index=7),
        ],
    ),
]

YTYP_STRUCT_INFOS.extend(EXTENSION_STRUCT_INFOS)

YTYP_ENUM_INFOS = [
    _enum_info("rage__fwArchetypeDef__eAssetType"),
]


@dataclasses.dataclass(slots=True)
class BaseArchetypeDef(MetaHashFieldsMixin):
    _hash_fields = ("name", "texture_dictionary", "clip_dictionary", "drawable_dictionary", "physics_dictionary", "asset_name")

    lod_dist: float = 0.0
    flags: int = 0
    special_attribute: int = 0
    bb_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bb_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bs_centre: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bs_radius: float = 0.0
    hd_texture_dist: float = 0.0
    name: MetaHash | HashLike = 0
    texture_dictionary: MetaHash | HashLike = 0
    clip_dictionary: MetaHash | HashLike = 0
    drawable_dictionary: MetaHash | HashLike = 0
    physics_dictionary: MetaHash | HashLike = 0
    asset_type: int = 0
    asset_name: MetaHash | HashLike = 0
    extensions: list[Any] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        if self.asset_name in (0, "") and self.name not in (0, ""):
            self.asset_name = self.name

    def add_extension(self, extension: Any) -> Any:
        self.extensions.append(extension)
        return extension

    def to_meta(self) -> dict[str, Any]:
        return {
            "lodDist": self.lod_dist,
            "flags": self.flags,
            "specialAttribute": self.special_attribute,
            "bbMin": self.bb_min,
            "bbMax": self.bb_max,
            "bsCentre": self.bs_centre,
            "bsRadius": self.bs_radius,
            "hdTextureDist": self.hd_texture_dist,
            "name": self.name,
            "textureDictionary": self.texture_dictionary,
            "clipDictionary": self.clip_dictionary,
            "drawableDictionary": self.drawable_dictionary,
            "physicsDictionary": self.physics_dictionary,
            "assetType": self.asset_type,
            "assetName": self.asset_name,
            "extensions": extensions_to_meta(self.extensions),
            "_meta_name_hash": meta_name("CBaseArchetypeDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "BaseArchetypeDef":
        return cls(
            lod_dist=float(value.get("lodDist", 0.0)),
            flags=int(value.get("flags", 0)),
            special_attribute=int(value.get("specialAttribute", 0)),
            bb_min=tuple(value.get("bbMin", (0.0, 0.0, 0.0))),
            bb_max=tuple(value.get("bbMax", (0.0, 0.0, 0.0))),
            bs_centre=tuple(value.get("bsCentre", (0.0, 0.0, 0.0))),
            bs_radius=float(value.get("bsRadius", 0.0)),
            hd_texture_dist=float(value.get("hdTextureDist", 0.0)),
            name=value.get("name", 0),
            texture_dictionary=value.get("textureDictionary", 0),
            clip_dictionary=value.get("clipDictionary", 0),
            drawable_dictionary=value.get("drawableDictionary", 0),
            physics_dictionary=value.get("physicsDictionary", 0),
            asset_type=int(value.get("assetType", 0)),
            asset_name=value.get("assetName", 0),
            extensions=extensions_from_meta(value.get("extensions", []) or []),
        )


@dataclasses.dataclass(slots=True)
class TimeArchetypeDef(BaseArchetypeDef):
    time_flags: int = 0

    def to_meta(self) -> dict[str, Any]:
        data = super().to_meta()
        data.update({"timeFlags": self.time_flags, "_meta_name_hash": meta_name("CTimeArchetypeDef")})
        return data

    @classmethod
    def from_meta(cls, value: Any) -> "TimeArchetypeDef":
        base = BaseArchetypeDef.from_meta(value)
        return cls(**dataclasses.asdict(base), time_flags=int(value.get("timeFlags", 0)))


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


@dataclasses.dataclass(slots=True)
class Ytyp(MetaHashFieldsMixin):
    _hash_fields = ("name",)
    _hash_list_fields = ("dependencies",)

    extensions: list[Any] = dataclasses.field(default_factory=list)
    archetypes: list[BaseArchetypeDef | TimeArchetypeDef | MloArchetypeDef | RawStruct | dict[str, Any]] = dataclasses.field(default_factory=list)
    name: MetaHash | HashLike = 0
    dependencies: list[MetaHash | HashLike] = dataclasses.field(default_factory=list)
    composite_entity_types: list[Any] = dataclasses.field(default_factory=list)
    meta_name: str = ""

    def __post_init__(self) -> None:
        self.name = _ensure_base_name(self.name, ".ytyp")

    @property
    def resource_name(self) -> str:
        return self.meta_name

    @resource_name.setter
    def resource_name(self, value: str) -> None:
        self.meta_name = str(value or "")

    def add_archetype(self, archetype: BaseArchetypeDef | TimeArchetypeDef | MloArchetypeDef) -> None:
        self.archetypes.append(archetype)

    def archetype(self, name: HashLike, **kwargs: Any) -> BaseArchetypeDef:
        archetype = BaseArchetypeDef(name=name, asset_name=kwargs.pop("asset_name", name), **kwargs)
        self.add_archetype(archetype)
        return archetype

    def create_archetype(self, name: HashLike, **kwargs: Any) -> BaseArchetypeDef:
        return self.archetype(name, **kwargs)

    def time_archetype(self, name: HashLike, **kwargs: Any) -> TimeArchetypeDef:
        archetype = TimeArchetypeDef(name=name, asset_name=kwargs.pop("asset_name", name), **kwargs)
        self.add_archetype(archetype)
        return archetype

    def mlo_archetype(self, name: HashLike, **kwargs: Any) -> MloArchetypeDef:
        archetype = MloArchetypeDef(name=name, asset_name=kwargs.pop("asset_name", name), **kwargs)
        self.add_archetype(archetype)
        return archetype

    def suggested_path(self) -> str:
        return _suggest_resource_path(self.name, self.meta_name, ".ytyp", "unnamed.ytyp")

    def to_meta_root(self) -> dict[str, Any]:
        return {
            "extensions": extensions_to_meta(self.extensions),
            "archetypes": [archetype.to_meta() if hasattr(archetype, "to_meta") else archetype for archetype in self.archetypes],
            "name": self.name,
            "dependencies": self.dependencies,
            "compositeEntityTypes": self.composite_entity_types,
            "_meta_name_hash": meta_name("CMapTypes"),
        }

    def to_bytes(self, *, version: int = 2) -> bytes:
        builder = MetaBuilder(struct_infos=YTYP_STRUCT_INFOS, enum_infos=YTYP_ENUM_INFOS, name=self.meta_name or "")
        system = builder.build(root_name_hash=meta_name("CMapTypes"), root_value=self.to_meta_root())
        return build_rsc7(system, version=version, system_alignment=0x2000)

    def save(self, path: str | Path | None = None, *, version: int = 2) -> Path:
        destination = Path(path) if path is not None else Path(self.suggested_path())
        destination.write_bytes(self.to_bytes(version=version))
        return destination

    def save_into_rpf(
        self,
        archive: RpfArchive,
        path: str | Path | None = None,
        *,
        version: int = 2,
    ) -> RpfFileEntry:
        target = path if path is not None else self.suggested_path()
        return archive.add_file(target, self.to_bytes(version=version))

    def to_meta(self) -> Meta:
        return Meta(
            Name=self.meta_name or "",
            root_name_hash=meta_name("CMapTypes"),
            root_value=self.to_meta_root(),
            struct_infos=YTYP_STRUCT_INFOS,
            enum_infos=YTYP_ENUM_INFOS,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "Ytyp":
        parsed = read_meta(data)
        root = parsed.decoded_root
        if not isinstance(root, dict) or root.get("_meta_name") != "CMapTypes":
            raise ValueError("META payload is not a CMapTypes/YTYP")
        archetypes: list[Any] = []
        for item in root.get("archetypes", []) or []:
            if isinstance(item, dict) and item.get("_meta_name") == "CTimeArchetypeDef":
                archetypes.append(TimeArchetypeDef.from_meta(item))
            elif isinstance(item, dict) and item.get("_meta_name") == "CMloArchetypeDef":
                archetypes.append(MloArchetypeDef.from_meta(item))
            elif isinstance(item, dict) and item.get("_meta_name") == "CBaseArchetypeDef":
                archetypes.append(BaseArchetypeDef.from_meta(item))
            else:
                archetypes.append(item)
        return cls(
            extensions=extensions_from_meta(root.get("extensions", []) or []),
            archetypes=archetypes,
            name=root.get("name", 0),
            dependencies=list(root.get("dependencies", []) or []),
            composite_entity_types=list(root.get("compositeEntityTypes", []) or []),
            meta_name=parsed.name,
        )

    @classmethod
    def from_path(cls, path: str | Path) -> "Ytyp":
        return cls.from_bytes(Path(path).read_bytes())


def read_ytyp(data: bytes) -> Ytyp:
    return Ytyp.from_bytes(data)


def save_ytyp(ytyp: Ytyp, path: str | Path | None = None, *, version: int = 2) -> Path:
    return ytyp.save(path, version=version)


Archetype = BaseArchetypeDef
TimeArchetype = TimeArchetypeDef
MloArchetype = MloArchetypeDef
Room = MloRoomDef
Portal = MloPortalDef
EntitySet = MloEntitySet
MloTimeModifier = MloTimeCycleModifier


__all__ = [
    "Archetype",
    "BaseArchetypeDef",
    "EntitySet",
    "MloArchetype",
    "MloArchetypeDef",
    "MloEntitySet",
    "MloPortalDef",
    "MloRoomDef",
    "MloTimeCycleModifier",
    "MloTimeModifier",
    "Portal",
    "Room",
    "TimeArchetype",
    "TimeArchetypeDef",
    "YTYP_ENUM_INFOS",
    "YTYP_STRUCT_INFOS",
    "Ytyp",
    "read_ytyp",
    "save_ytyp",
]


