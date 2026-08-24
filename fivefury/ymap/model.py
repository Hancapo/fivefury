from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..authoring import BuildContext, asset_name
from ..authoring.diagnostics import ValidationReport
from ..meta import Meta, MetaBuilder, RawStruct, read_meta
from ..meta.defs import meta_name
from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..resource import build_rsc7
from ..vector import Aabb3, Quaternion, Vector3
from .base import BlockDesc, ContainerLodDef, PhysicsDictionary
from .cargens import CarGen
from .defs import (
    YMAP_ENUM_INFOS,
    YMAP_STRUCT_INFOS,
    _ensure_base_name,
)
from .entities import EntityDef, MloInstanceDef
from .enums import (
    YmapContentFlags,
    YmapFlags,
    YmapLodLevel,
    coerce_ymap_content_flags,
    coerce_ymap_flags,
)
from .grass import GrassInstanceBatch, InstancedMapData
from .lights import (
    DistantLodLightsSoa,
    LodLight,
    LodLightsSoa,
    _coerce_lod_light,
)
from .mlo_validation import (
    archetypes_by_hash,
    build_ymap_mlo_instances,
    validate_ymap_mlo_instances,
)
from .occluders import (
    AngleMode,
    BoxOccluder,
    OccludeModel,
    _coerce_occlude_model,
)
from .timecycle import TimeCycleModifier
from .utils import (
    coerce_container_lod,
    coerce_physics_dictionary,
    expand_bounds,
    merge_bounds,
    positions_bounds,
    suggest_resource_path,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..rpf import RpfArchive, RpfFileEntry
    from ..ybn import Ybn
    from ..ytyp import MloArchetypeDef, Ytyp


def _context_dependencies(
    context: BuildContext | None,
) -> tuple[tuple[Ytyp, ...] | None, dict[str, Ybn] | None]:
    if context is None:
        return None, None

    from ..ybn import Ybn
    from ..ytyp import Ytyp

    ytyps = context.assets.of_type(Ytyp)
    ybns = {
        asset_name(path): asset
        for path, asset in context.assets.items()
        if isinstance(asset, Ybn)
    }
    return (
        ytyps or (() if context.strict else None),
        ybns or ({} if context.strict else None),
    )


@dataclasses.dataclass(slots=True)
class Ymap(MetaHashFieldsMixin):
    _hash_fields = ("name", "parent")

    name: MetaHash | HashLike = 0
    parent: MetaHash | HashLike = 0
    flags: YmapFlags | int = YmapFlags.NONE
    content_flags: YmapContentFlags | int = YmapContentFlags.NONE
    streaming_extents_min: Vector3 = dataclasses.field(default_factory=Vector3)
    streaming_extents_max: Vector3 = dataclasses.field(default_factory=Vector3)
    entities_extents_min: Vector3 = dataclasses.field(default_factory=Vector3)
    entities_extents_max: Vector3 = dataclasses.field(default_factory=Vector3)
    entities: list[EntityDef | MloInstanceDef | RawStruct | dict[str, Any]] = dataclasses.field(default_factory=list)
    container_lods: list[ContainerLodDef | dict[str, Any] | RawStruct] = dataclasses.field(default_factory=list)
    box_occluders: list[BoxOccluder | dict[str, Any] | RawStruct] = dataclasses.field(default_factory=list)
    occlude_models: list[OccludeModel | dict[str, Any] | RawStruct] = dataclasses.field(default_factory=list)
    physics_dictionaries: list[PhysicsDictionary | MetaHash | HashLike] = dataclasses.field(default_factory=list)
    instanced_data: InstancedMapData | dict[str, Any] | None = None
    time_cycle_modifiers: list[TimeCycleModifier | dict[str, Any]] = dataclasses.field(default_factory=list)
    car_generators: list[CarGen | dict[str, Any]] = dataclasses.field(default_factory=list)
    lod_lights: LodLightsSoa | dict[str, Any] | RawStruct | None = None
    distant_lod_lights: DistantLodLightsSoa | dict[str, Any] | RawStruct | None = None
    block: BlockDesc = dataclasses.field(default_factory=BlockDesc)
    meta_name: str = ""

    def __post_init__(self) -> None:
        for name in ("streaming_extents_min", "streaming_extents_max", "entities_extents_min", "entities_extents_max"):
            if not isinstance(getattr(self, name), Vector3):
                raise TypeError(f"Ymap.{name} must be a Vector3")
        self.name = _ensure_base_name(self.name, ".ymap")
        self.flags = coerce_ymap_flags(self.flags)
        self.content_flags = coerce_ymap_content_flags(self.content_flags)
        self.physics_dictionaries = [coerce_physics_dictionary(item) for item in self.physics_dictionaries]

    @property
    def resource_name(self) -> str:
        return self.meta_name

    @resource_name.setter
    def resource_name(self, value: str) -> None:
        self.meta_name = str(value or "")

    def physics_dictionary(self, name: PhysicsDictionary | MetaHash | HashLike) -> PhysicsDictionary:
        dictionary = coerce_physics_dictionary(name)
        self.physics_dictionaries.append(dictionary)
        return dictionary

    def entity(self, archetype_name: HashLike, **kwargs: Any) -> EntityDef:
        entity = EntityDef(archetype_name=archetype_name, **kwargs)
        self.entities.append(entity)
        return entity

    def mlo_instance(
        self,
        archetype_name: HashLike | MloArchetypeDef,
        **kwargs: Any,
    ) -> MloInstanceDef:
        name = getattr(archetype_name, "name", archetype_name)
        entity = MloInstanceDef(archetype_name=name, **kwargs)
        self.entities.append(entity)
        return entity

    def box_occluder(self, **kwargs: Any) -> BoxOccluder:
        if "position" in kwargs and "size" in kwargs:
            position = kwargs.pop("position")
            size = kwargs.pop("size")
            angle = kwargs.pop("angle", 0.0)
            angle_mode = kwargs.pop("angle_mode", AngleMode.DEGREES)
            occ = BoxOccluder.from_box(position, size, angle, angle_mode)
        else:
            occ = BoxOccluder(**kwargs)
        self.box_occluders.append(occ)
        return occ

    def occlude_model(self, **kwargs: Any) -> Any:
        model = _coerce_occlude_model(**kwargs)
        self.occlude_models.append(model)
        return model

    def occlude_box(
        self,
        min_pos: Vector3,
        max_pos: Vector3,
        *,
        flags: int = 0,
    ) -> list[OccludeModel]:
        models = OccludeModel.from_box(min_pos, max_pos, flags=flags)
        self.occlude_models.extend(models)
        return models

    def occlude_quad(
        self,
        corners: list[Vector3],
        *,
        flags: int = 0,
    ) -> list[OccludeModel]:
        models = OccludeModel.from_quad(corners, flags=flags)
        self.occlude_models.extend(models)
        return models

    def occlude_faces(
        self,
        vertices: list[Vector3],
        faces: list[tuple[int, ...]],
        *,
        flags: int = 0,
    ) -> list[OccludeModel]:
        models = OccludeModel.from_faces(vertices, faces, flags=flags)
        self.occlude_models.extend(models)
        return models

    def container_lod(self, **kwargs: Any) -> ContainerLodDef:
        lod = ContainerLodDef(**kwargs)
        self.container_lods.append(lod)
        return lod

    def ensure_instanced_data(self) -> InstancedMapData:
        if isinstance(self.instanced_data, InstancedMapData):
            return self.instanced_data
        self.instanced_data = InstancedMapData.from_meta(self.instanced_data) if isinstance(self.instanced_data, dict) else InstancedMapData()
        return self.instanced_data

    def grass_batch(self, **kwargs: Any) -> GrassInstanceBatch:
        batch = GrassInstanceBatch(**kwargs)
        self.ensure_instanced_data().grass_instance_list.append(batch)
        return batch

    def ensure_lod_lights(self) -> LodLightsSoa:
        if isinstance(self.lod_lights, LodLightsSoa):
            return self.lod_lights
        self.lod_lights = LodLightsSoa.from_meta(self.lod_lights) if isinstance(self.lod_lights, dict) else LodLightsSoa()
        return self.lod_lights

    def ensure_distant_lod_lights(self) -> DistantLodLightsSoa:
        if isinstance(self.distant_lod_lights, DistantLodLightsSoa):
            return self.distant_lod_lights
        self.distant_lod_lights = (
            DistantLodLightsSoa.from_meta(self.distant_lod_lights)
            if isinstance(self.distant_lod_lights, dict)
            else DistantLodLightsSoa()
        )
        return self.distant_lod_lights

    def _append_lod_light(self, light: LodLight) -> LodLight:
        self.ensure_lod_lights().append(light)
        self.ensure_distant_lod_lights().append(light.position, light.rgbi)
        return light

    def lod_light(self, light: LodLight | None = None, **kwargs: Any) -> LodLight:
        if light is not None and kwargs:
            raise TypeError("Pass a LodLight or its fields, not both")
        resolved = light or _coerce_lod_light(**kwargs)
        if isinstance(resolved, LodLightsSoa):
            self.lod_lights = resolved
            return LodLight()
        self._append_lod_light(resolved)
        return resolved

    def iter_lod_lights(self) -> list[LodLight]:
        lod = self.ensure_lod_lights() if self.lod_lights is not None else LodLightsSoa()
        distant = self.ensure_distant_lod_lights() if self.distant_lod_lights is not None else DistantLodLightsSoa()
        count = max(len(lod), len(distant))
        lights: list[LodLight] = []
        for index in range(count):
            position = distant.position[index] if index < len(distant.position) else Vector3()
            direction = lod.direction[index] if index < len(lod.direction) else Vector3(0.0, 0.0, -1.0)
            lights.append(
                LodLight(
                    position=position,
                    direction=direction,
                    falloff=lod.falloff[index] if index < len(lod.falloff) else 0.0,
                    falloff_exponent=lod.falloff_exponent[index] if index < len(lod.falloff_exponent) else 0.0,
                    time_and_state_flags=lod.time_and_state_flags[index] if index < len(lod.time_and_state_flags) else 0,
                    hash=lod.hash[index] if index < len(lod.hash) else 0,
                    cone_inner_angle=lod.cone_inner_angle[index] if index < len(lod.cone_inner_angle) else 0,
                    cone_outer_angle_or_cap_ext=lod.cone_outer_angle_or_cap_ext[index] if index < len(lod.cone_outer_angle_or_cap_ext) else 0,
                    corona_intensity=lod.corona_intensity[index] if index < len(lod.corona_intensity) else 0,
                    rgbi=distant.RGBI[index] if index < len(distant.RGBI) else 0,
                )
            )
        return lights

    def normalize_lod_lights(self) -> Ymap:
        lod = self.ensure_lod_lights() if self.lod_lights is not None else None
        distant = self.ensure_distant_lod_lights() if self.distant_lod_lights is not None else None
        lod_count = len(lod) if isinstance(lod, LodLightsSoa) else 0
        distant_count = len(distant) if isinstance(distant, DistantLodLightsSoa) else 0

        issues = ValidationReport()
        if isinstance(lod, LodLightsSoa):
            issues.extend(lod.validate())
        if isinstance(distant, DistantLodLightsSoa):
            issues.extend(distant.validate())
        issues.raise_for_errors()

        # The game stores distant parents and LOD children in separate YMAPs.
        # Reordering is only safe when both paired arrays are present together.
        if lod_count == 0 or distant_count == 0:
            return self
        if distant_count != lod_count:
            return self

        ordered_lights = self.iter_lod_lights()
        street_lights = [light for light in ordered_lights if light.is_street_light]
        other_lights = [light for light in ordered_lights if not light.is_street_light]
        normalized = street_lights + other_lights

        normalized_lod = LodLightsSoa()
        normalized_distant = DistantLodLightsSoa(category=distant.category)
        for light in normalized:
            normalized_lod.append(light)
            normalized_distant.append(light.position, light.rgbi)
        normalized_distant.num_street_lights = len(street_lights)

        self.lod_lights = normalized_lod
        self.distant_lod_lights = normalized_distant
        return self

    def car_gen(self, car_model: HashLike, position: Vector3, heading: float = 0.0, **kwargs: Any) -> CarGen:
        cg = CarGen.create(car_model, position, heading, **kwargs)
        self.car_generators.append(cg)
        return cg

    def time_cycle_modifier(
        self,
        name: HashLike,
        position: Vector3,
        size: Vector3,
        **kwargs: Any,
    ) -> TimeCycleModifier:
        modifier = TimeCycleModifier.create(name, position, size, **kwargs)
        self.time_cycle_modifiers.append(modifier)
        return modifier

    def suggested_path(self) -> str:
        return suggest_resource_path(self.name, self.meta_name, ".ymap", "unnamed.ymap")

    def recalculate_extents(
        self,
        *,
        streaming_margin: float = 20.0,
        include_lod_distance: bool = True,
        context: BuildContext | None = None,
    ) -> Ymap:
        bounds: Aabb3 | None = None
        ytyps, _ = _context_dependencies(context)
        archetypes = archetypes_by_hash(ytyps)
        for entity in self.entities:
            position = getattr(entity, "position", Vector3())
            archetype = archetypes.get(int(getattr(entity, "archetype_name", 0)))
            minimum = getattr(archetype, "bb_min", None)
            maximum = getattr(archetype, "bb_max", None)
            if (
                archetype is not None
                and isinstance(minimum, Vector3)
                and isinstance(maximum, Vector3)
            ):
                scale_xy = float(getattr(entity, "scale_xy", 1.0))
                scale_z = float(getattr(entity, "scale_z", 1.0))
                rotation = getattr(entity, "rotation", Quaternion())
                if not isinstance(position, Vector3) or not isinstance(rotation, Quaternion):
                    raise TypeError("YMAP entity transforms must use Vector3 and Quaternion")
                entity_bounds = Aabb3(minimum, maximum).transformed(
                    translation=position,
                    rotation=rotation,
                    scale=Vector3(scale_xy, scale_xy, scale_z),
                )
            else:
                entity_bounds = positions_bounds([position])
            bounds = merge_bounds(bounds, entity_bounds)
        for car_gen in self.car_generators:
            position = getattr(car_gen, "position", None)
            if isinstance(position, Vector3):
                bounds = merge_bounds(bounds, Aabb3(position, position))
        for modifier in self.time_cycle_modifiers:
            min_extents = getattr(modifier, "min_extents", None)
            max_extents = getattr(modifier, "max_extents", None)
            if isinstance(min_extents, Vector3) and isinstance(max_extents, Vector3):
                bounds = merge_bounds(bounds, Aabb3(min_extents, max_extents))
        for occluder in self.box_occluders:
            occluder_bounds = getattr(occluder, "bounds", None)
            if isinstance(occluder_bounds, Aabb3):
                bounds = merge_bounds(bounds, occluder_bounds)
        for model in self.occlude_models:
            model_bounds = getattr(model, "bounds", None)
            if isinstance(model_bounds, Aabb3):
                bounds = merge_bounds(bounds, model_bounds)
        if isinstance(self.instanced_data, InstancedMapData):
            for batch in self.instanced_data.grass_instance_list:
                bounds = merge_bounds(bounds, batch.bounds)
        if isinstance(self.distant_lod_lights, DistantLodLightsSoa) and self.distant_lod_lights.position:
            bounds = merge_bounds(bounds, positions_bounds(list(self.distant_lod_lights.position)))
        if bounds is None:
            return self
        self.entities_extents_min = bounds.minimum
        self.entities_extents_max = bounds.maximum
        padding = max(float(streaming_margin), 0.0)
        if include_lod_distance:
            padding += max((max(float(getattr(entity, "lod_dist", 0.0)), 0.0) for entity in self.entities), default=0.0)
        streaming_bounds = expand_bounds(bounds, padding)
        self.streaming_extents_min = streaming_bounds.minimum
        self.streaming_extents_max = streaming_bounds.maximum
        return self

    def recalculate_flags(self) -> Ymap:
        flags = self.flags & (YmapFlags.MANUAL_STREAM_ONLY | YmapFlags.IS_PARENT)
        content_flags = YmapContentFlags.NONE

        for entity in self.entities:
            lod_level = YmapLodLevel(int(getattr(entity, "lod_level", YmapLodLevel.DEPTH_HD) or 0))
            match lod_level:
                case YmapLodLevel.DEPTH_HD | YmapLodLevel.DEPTH_ORPHANHD:
                    content_flags |= YmapContentFlags.ENTITIES_HD
                case YmapLodLevel.DEPTH_LOD:
                    content_flags |= YmapContentFlags.ENTITIES_LOD
                case YmapLodLevel.DEPTH_SLOD1:
                    content_flags |= YmapContentFlags.ENTITIES_CRITICAL
                case (
                    YmapLodLevel.DEPTH_SLOD2
                    | YmapLodLevel.DEPTH_SLOD3
                    | YmapLodLevel.DEPTH_SLOD4
                ):
                    content_flags |= (
                        YmapContentFlags.ENTITIES_CONTAINER_LOD
                        | YmapContentFlags.ENTITIES_CRITICAL
                    )

            if isinstance(entity, MloInstanceDef) or getattr(entity, "_meta_name", "") == "CMloInstanceDef":
                content_flags |= YmapContentFlags.MLO

        if self.block.version or self.block.flags or self.block.name or self.block.exported_by or self.block.owner or self.block.time:
            content_flags |= YmapContentFlags.BLOCKINFO

        if self.physics_dictionaries:
            content_flags |= YmapContentFlags.ENTITIES_USING_PHYSICS
        if isinstance(self.instanced_data, InstancedMapData) and self.instanced_data.grass_instance_list:
            content_flags |= YmapContentFlags.INSTANCE_LIST
        if isinstance(self.lod_lights, LodLightsSoa) and len(self.lod_lights) > 0:
            content_flags |= YmapContentFlags.LOD_LIGHTS
        if isinstance(self.distant_lod_lights, DistantLodLightsSoa) and len(self.distant_lod_lights) > 0:
            content_flags |= YmapContentFlags.DISTANT_LOD_LIGHTS
        if self.box_occluders or self.occlude_models:
            content_flags |= YmapContentFlags.OCCLUDER

        self.flags = flags
        self.content_flags = content_flags
        return self

    def build(
        self,
        *,
        auto_extents: bool = False,
        auto_flags: bool = True,
        context: BuildContext | None = None,
    ) -> Ymap:
        ytyps, _ = _context_dependencies(context)
        build_ymap_mlo_instances(self, ytyps)
        self.normalize_lod_lights()
        if auto_extents:
            self.recalculate_extents(context=context)
        if auto_flags:
            self.recalculate_flags()
        self.name = _ensure_base_name(self.name, ".ymap")
        return self

    def validate_mlos(self, *, context: BuildContext | None = None) -> ValidationReport:
        ytyps, ybns = _context_dependencies(context)
        return validate_ymap_mlo_instances(self, ytyps, ybns)

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        issues = ValidationReport()
        lod_count = len(self.lod_lights) if isinstance(self.lod_lights, LodLightsSoa) else 0
        distant_count = len(self.distant_lod_lights) if isinstance(self.distant_lod_lights, DistantLodLightsSoa) else 0
        if isinstance(self.lod_lights, LodLightsSoa):
            issues.extend(self.lod_lights.validate(), path="lod_lights")
        if isinstance(self.distant_lod_lights, DistantLodLightsSoa):
            issues.extend(self.distant_lod_lights.validate(), path="distant_lod_lights")
        if lod_count > 0 and distant_count == lod_count:
            seen_non_street = False
            for light in self.iter_lod_lights():
                if light.is_street_light and seen_non_street:
                    issues.issue("ymap.lod_lights.street_prefix", "YMAP street lights must occupy the leading prefix of the paired LOD light arrays", path="distant_lod_lights.num_street_lights")
                    break
                if not light.is_street_light:
                    seen_non_street = True
        issues.extend(self.validate_mlos(context=context))
        return issues

    def to_meta_root(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parent": self.parent,
            "flags": int(self.flags),
            "contentFlags": int(self.content_flags),
            "streamingExtentsMin": self.streaming_extents_min,
            "streamingExtentsMax": self.streaming_extents_max,
            "entitiesExtentsMin": self.entities_extents_min,
            "entitiesExtentsMax": self.entities_extents_max,
            "entities": [entity.to_meta() if hasattr(entity, "to_meta") else entity for entity in self.entities],
            "containerLods": [item.to_meta() if hasattr(item, "to_meta") else item for item in self.container_lods],
            "boxOccluders": [item.to_meta() if hasattr(item, "to_meta") else item for item in self.box_occluders],
            "occludeModels": [item.to_meta() if hasattr(item, "to_meta") else item for item in self.occlude_models],
            "physicsDictionaries": [
                item.to_meta() if hasattr(item, "to_meta") else item
                for item in self.physics_dictionaries
            ],
            "instancedData": self.instanced_data.to_meta() if hasattr(self.instanced_data, "to_meta") else self.instanced_data,
            "timeCycleModifiers": [modifier.to_meta() if hasattr(modifier, "to_meta") else modifier for modifier in self.time_cycle_modifiers],
            "carGenerators": [car_gen.to_meta() if hasattr(car_gen, "to_meta") else car_gen for car_gen in self.car_generators],
            "LODLightsSOA": self.lod_lights.to_meta() if hasattr(self.lod_lights, "to_meta") else self.lod_lights,
            "DistantLODLightsSOA": self.distant_lod_lights.to_meta() if hasattr(self.distant_lod_lights, "to_meta") else self.distant_lod_lights,
            "block": self.block.to_meta() if hasattr(self.block, "to_meta") else self.block,
            "_meta_name_hash": meta_name("CMapData"),
        }

    def to_bytes(
        self,
        *,
        version: int = 2,
        validate: bool = True,
        context: BuildContext | None = None,
    ) -> bytes:
        self.build(context=context)
        if validate:
            self.validate(context=context).raise_for_errors()
        builder = MetaBuilder(struct_infos=YMAP_STRUCT_INFOS, enum_infos=YMAP_ENUM_INFOS, name=self.meta_name or "")
        system = builder.build(root_name_hash=meta_name("CMapData"), root_value=self.to_meta_root())
        system_flags = builder.page_flags | (((version >> 4) & 0xF) << 28)
        return build_rsc7(system, version=version, system_alignment=0x2000, system_flags=system_flags)

    def save(
        self,
        path: str | Path | None = None,
        *,
        version: int = 2,
        auto_extents: bool = False,
        auto_flags: bool = True,
        validate: bool = True,
        context: BuildContext | None = None,
    ) -> Path:
        if auto_extents:
            self.recalculate_extents(context=context)
        if auto_flags:
            self.recalculate_flags()
        destination = Path(path) if path is not None else Path(self.suggested_path())
        destination.write_bytes(
            self.to_bytes(version=version, validate=validate, context=context)
        )
        return destination

    def save_into_rpf(
        self,
        archive: RpfArchive,
        path: str | Path | None = None,
        *,
        version: int = 2,
        auto_extents: bool = False,
        auto_flags: bool = True,
        validate: bool = True,
        context: BuildContext | None = None,
    ) -> RpfFileEntry:
        if auto_extents:
            self.recalculate_extents(context=context)
        if auto_flags:
            self.recalculate_flags()
        target = path if path is not None else self.suggested_path()
        return archive.file(
            target,
            self.to_bytes(version=version, validate=validate, context=context),
        )

    def to_meta(self) -> Meta:
        return Meta(
            Name=self.meta_name or "",
            root_name_hash=meta_name("CMapData"),
            root_value=self.to_meta_root(),
            struct_infos=YMAP_STRUCT_INFOS,
            enum_infos=YMAP_ENUM_INFOS,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> Ymap:
        parsed = read_meta(data)
        root = parsed.decoded_root
        if not isinstance(root, dict) or root.get("_meta_name") != "CMapData":
            raise ValueError("META payload is not a CMapData/YMAP")
        entities: list[Any] = []
        for item in root.get("entities", []) or []:
            if isinstance(item, dict) and item.get("_meta_name") == "CMloInstanceDef":
                entities.append(MloInstanceDef.from_meta(item))
            elif isinstance(item, dict) and item.get("_meta_name") == "CEntityDef":
                entities.append(EntityDef.from_meta(item))
            else:
                entities.append(item)
        container_lods = [coerce_container_lod(item) for item in root.get("containerLods", []) or []]
        return cls(
            name=root.get("name", 0),
            parent=root.get("parent", 0),
            flags=coerce_ymap_flags(int(root.get("flags", 0))),
            content_flags=coerce_ymap_content_flags(int(root.get("contentFlags", 0))),
            streaming_extents_min=Vector3.from_iterable(root.get("streamingExtentsMin", (0.0, 0.0, 0.0))),
            streaming_extents_max=Vector3.from_iterable(root.get("streamingExtentsMax", (0.0, 0.0, 0.0))),
            entities_extents_min=Vector3.from_iterable(root.get("entitiesExtentsMin", (0.0, 0.0, 0.0))),
            entities_extents_max=Vector3.from_iterable(root.get("entitiesExtentsMax", (0.0, 0.0, 0.0))),
            entities=entities,
            container_lods=container_lods,
            box_occluders=[BoxOccluder.from_meta(item) if isinstance(item, dict) else item for item in root.get("boxOccluders", []) or []],
            occlude_models=[OccludeModel.from_meta(item) if isinstance(item, dict) else item for item in root.get("occludeModels", []) or []],
            physics_dictionaries=[
                PhysicsDictionary.from_meta(item)
                for item in root.get("physicsDictionaries", []) or []
            ],
            instanced_data=InstancedMapData.from_meta(root.get("instancedData")) if isinstance(root.get("instancedData"), dict) else root.get("instancedData"),
            time_cycle_modifiers=[TimeCycleModifier.from_meta(item) if isinstance(item, dict) else item for item in root.get("timeCycleModifiers", []) or []],
            car_generators=[CarGen.from_meta(item) if isinstance(item, dict) else item for item in root.get("carGenerators", []) or []],
            lod_lights=LodLightsSoa.from_meta(root.get("LODLightsSOA")) if isinstance(root.get("LODLightsSOA"), dict) else root.get("LODLightsSOA"),
            distant_lod_lights=DistantLodLightsSoa.from_meta(root.get("DistantLODLightsSOA")) if isinstance(root.get("DistantLODLightsSOA"), dict) else root.get("DistantLODLightsSOA"),
            block=BlockDesc.from_meta(root.get("block")),
            meta_name=parsed.name,
        )

    @classmethod
    def from_path(cls, path: str | Path) -> Ymap:
        return cls.from_bytes(Path(path).read_bytes())
