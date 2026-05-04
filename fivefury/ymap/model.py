from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta import MetaBuilder, RawStruct, read_meta, Meta
from ..meta.defs import meta_name
from ..resource import build_rsc7
from .blocks import BlockDesc, CarGen, ContainerLodDef, PhysicsDictionary, TimeCycleModifier
from .entities import EntityDef, MloInstanceDef
from .enums import (
    YmapContentFlags,
    YmapFlags,
    YmapLodLevel,
    coerce_ymap_content_flags,
    coerce_ymap_flags,
)
from .surfaces import (
    AngleMode,
    BoxOccluder,
    DistantLodLightsSoa,
    GrassInstanceBatch,
    InstancedMapData,
    LodLight,
    LodLightsSoa,
    OccludeModel,
    _coerce_lod_light,
    _coerce_occlude_model,
)
from .defs import (
    YMAP_ENUM_INFOS,
    YMAP_STRUCT_INFOS,
    _ensure_base_name,
    _resource_text,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..rpf import RpfArchive, RpfFileEntry


def _suggest_resource_path(value: HashLike, meta_name_value: str, extension: str, fallback: str) -> str:
    meta_text = _resource_text(meta_name_value)
    if meta_text:
        lowered = meta_text.lower()
        return meta_text if lowered.endswith(extension) else f"{meta_text}{extension}"
    value_text = _resource_text(value)
    if value_text:
        lowered = value_text.lower()
        return value_text if lowered.endswith(extension) else f"{value_text}{extension}"
    return fallback


def _entity_positions(entities: list[Any]) -> list[tuple[float, float, float]]:
    positions: list[tuple[float, float, float]] = []
    for entity in entities:
        position = getattr(entity, "position", None)
        if isinstance(position, tuple) and len(position) == 3:
            positions.append((float(position[0]), float(position[1]), float(position[2])))
    return positions


def _positions_bounds(positions: list[tuple[float, float, float]]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    xs = [pos[0] for pos in positions]
    ys = [pos[1] for pos in positions]
    zs = [pos[2] for pos in positions]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _expand_bounds(
    min_value: tuple[float, float, float],
    max_value: tuple[float, float, float],
    padding: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if padding <= 0:
        return min_value, max_value
    return (
        (min_value[0] - padding, min_value[1] - padding, min_value[2] - padding),
        (max_value[0] + padding, max_value[1] + padding, max_value[2] + padding),
    )


def _merge_bounds(
    current: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
    new_bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    if new_bounds is None:
        return current
    if current is None:
        return new_bounds
    return (
        (
            min(current[0][0], new_bounds[0][0]),
            min(current[0][1], new_bounds[0][1]),
            min(current[0][2], new_bounds[0][2]),
        ),
        (
            max(current[1][0], new_bounds[1][0]),
            max(current[1][1], new_bounds[1][1]),
            max(current[1][2], new_bounds[1][2]),
        ),
    )


def _coerce_container_lod(item: Any) -> ContainerLodDef | Any:
    if isinstance(item, ContainerLodDef):
        return item
    if isinstance(item, dict):
        return ContainerLodDef.from_meta(item)
    return item


def _coerce_physics_dictionary(item: PhysicsDictionary | MetaHash | HashLike) -> PhysicsDictionary:
    return item if isinstance(item, PhysicsDictionary) else PhysicsDictionary(name=item)


@dataclasses.dataclass(slots=True)
class Ymap(MetaHashFieldsMixin):
    _hash_fields = ("name", "parent")

    name: MetaHash | HashLike = 0
    parent: MetaHash | HashLike = 0
    flags: YmapFlags | int = YmapFlags.NONE
    content_flags: YmapContentFlags | int = YmapContentFlags.NONE
    streaming_extents_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    streaming_extents_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    entities_extents_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    entities_extents_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
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
        self.name = _ensure_base_name(self.name, ".ymap")
        self.flags = coerce_ymap_flags(self.flags)
        self.content_flags = coerce_ymap_content_flags(self.content_flags)
        self.physics_dictionaries = [_coerce_physics_dictionary(item) for item in self.physics_dictionaries]

    @property
    def resource_name(self) -> str:
        return self.meta_name

    @resource_name.setter
    def resource_name(self, value: str) -> None:
        self.meta_name = str(value or "")

    def add_entity(self, entity: EntityDef | MloInstanceDef) -> EntityDef | MloInstanceDef:
        self.entities.append(entity)
        return entity

    def add_physics_dictionary(self, name: PhysicsDictionary | MetaHash | HashLike) -> PhysicsDictionary:
        return self.physics_dictionary(name)

    def physics_dictionary(self, name: PhysicsDictionary | MetaHash | HashLike) -> PhysicsDictionary:
        dictionary = _coerce_physics_dictionary(name)
        self.physics_dictionaries.append(dictionary)
        return dictionary

    def entity(self, archetype_name: HashLike, **kwargs: Any) -> EntityDef:
        entity = EntityDef(archetype_name=archetype_name, **kwargs)
        self.add_entity(entity)
        return entity

    def create_entity(self, archetype_name: HashLike, **kwargs: Any) -> EntityDef:
        return self.entity(archetype_name, **kwargs)

    def mlo_instance(self, archetype_name: HashLike, **kwargs: Any) -> MloInstanceDef:
        entity = MloInstanceDef(archetype_name=archetype_name, **kwargs)
        self.add_entity(entity)
        return entity

    def add(self, item: Any) -> Any:
        return self._add_one(item)

    def _add_one(self, item: Any) -> Any:
        if isinstance(item, (EntityDef, MloInstanceDef)):
            return self.add_entity(item)
        if isinstance(item, PhysicsDictionary):
            self.physics_dictionaries.append(item)
            return item
        if isinstance(item, ContainerLodDef):
            return self.add_container_lod(item)
        if isinstance(item, BoxOccluder):
            return self.add_box_occluder(item)
        if isinstance(item, OccludeModel):
            return self.add_occlude_model(item)
        if isinstance(item, GrassInstanceBatch):
            return self.add_grass_batch(item)
        if isinstance(item, LodLight):
            return self.add_lod_light(item)
        if isinstance(item, CarGen):
            return self.add_car_gen(item)
        if isinstance(item, TimeCycleModifier):
            return self.add_time_cycle_modifier(item)
        if isinstance(item, InstancedMapData):
            self.instanced_data = item
            return item
        if isinstance(item, LodLightsSoa):
            self.lod_lights = item
            return item
        if isinstance(item, DistantLodLightsSoa):
            self.distant_lod_lights = item
            return item
        if isinstance(item, BlockDesc):
            self.block = item
            return item
        raise TypeError(f"Unsupported YMAP component: {type(item).__name__}")

    def add_box_occluder(self, occluder: BoxOccluder | dict[str, Any]) -> Any:
        self.box_occluders.append(occluder)
        return occluder

    def box_occluder(self, **kwargs: Any) -> BoxOccluder:
        if "position" in kwargs and "size" in kwargs:
            position = kwargs.pop("position")
            size = kwargs.pop("size")
            angle = kwargs.pop("angle", 0.0)
            angle_mode = kwargs.pop("angle_mode", AngleMode.DEGREES)
            occ = BoxOccluder.from_box(position, size, angle, angle_mode)
        else:
            occ = BoxOccluder(**kwargs)
        self.add_box_occluder(occ)
        return occ

    def add_occlude_model(self, model: OccludeModel | dict[str, Any]) -> Any:
        self.occlude_models.append(model)
        return model

    def occlude_model(self, **kwargs: Any) -> Any:
        return self.add_occlude_model(_coerce_occlude_model(**kwargs))

    def occlude_box(
        self,
        min_pos: tuple[float, float, float],
        max_pos: tuple[float, float, float],
        *,
        flags: int = 0,
    ) -> list[OccludeModel]:
        models = OccludeModel.from_box(min_pos, max_pos, flags=flags)
        for model in models:
            self.add_occlude_model(model)
        return models

    def occlude_quad(
        self,
        corners: list[tuple[float, float, float]],
        *,
        flags: int = 0,
    ) -> list[OccludeModel]:
        models = OccludeModel.from_quad(corners, flags=flags)
        for model in models:
            self.add_occlude_model(model)
        return models

    def occlude_faces(
        self,
        vertices: list[tuple[float, float, float]],
        faces: list[tuple[int, ...]],
        *,
        flags: int = 0,
    ) -> list[OccludeModel]:
        models = OccludeModel.from_faces(vertices, faces, flags=flags)
        for model in models:
            self.add_occlude_model(model)
        return models

    def add_container_lod(self, lod: ContainerLodDef) -> ContainerLodDef:
        self.container_lods.append(lod)
        return lod

    def container_lod(self, **kwargs: Any) -> ContainerLodDef:
        lod = ContainerLodDef(**kwargs)
        self.add_container_lod(lod)
        return lod

    def ensure_instanced_data(self) -> InstancedMapData:
        if isinstance(self.instanced_data, InstancedMapData):
            return self.instanced_data
        self.instanced_data = InstancedMapData.from_meta(self.instanced_data) if isinstance(self.instanced_data, dict) else InstancedMapData()
        return self.instanced_data

    def add_grass_batch(self, batch: GrassInstanceBatch) -> GrassInstanceBatch:
        return self.ensure_instanced_data().add_grass_batch(batch)

    def grass_batch(self, **kwargs: Any) -> GrassInstanceBatch:
        return self.add_grass_batch(GrassInstanceBatch(**kwargs))

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

    def add_lod_light(self, light: LodLight) -> LodLight:
        self.ensure_lod_lights().append(light)
        self.ensure_distant_lod_lights().append(light.position, light.rgbi)
        return light

    def lod_light(self, **kwargs: Any) -> LodLight:
        light = _coerce_lod_light(**kwargs)
        if isinstance(light, LodLightsSoa):
            self.lod_lights = light
            return LodLight()
        self.add_lod_light(light)
        return light

    def iter_lod_lights(self) -> list[LodLight]:
        lod = self.ensure_lod_lights() if self.lod_lights is not None else LodLightsSoa()
        distant = self.ensure_distant_lod_lights() if self.distant_lod_lights is not None else DistantLodLightsSoa()
        count = max(len(lod), len(distant))
        lights: list[LodLight] = []
        for index in range(count):
            position = distant.position[index] if index < len(distant.position) else (0.0, 0.0, 0.0)
            direction = lod.direction[index] if index < len(lod.direction) else (0.0, 0.0, -1.0)
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

    def normalize_lod_lights(self) -> "Ymap":
        lod = self.ensure_lod_lights() if self.lod_lights is not None else None
        distant = self.ensure_distant_lod_lights() if self.distant_lod_lights is not None else None
        lod_count = len(lod) if isinstance(lod, LodLightsSoa) else 0
        distant_count = len(distant) if isinstance(distant, DistantLodLightsSoa) else 0

        if lod_count == 0:
            if isinstance(distant, DistantLodLightsSoa):
                distant.clamp_street_light_count()
            return self

        if not isinstance(distant, DistantLodLightsSoa) or distant_count == 0:
            raise ValueError("YMAP LOD lights require matching DistantLODLightsSOA entries for positions and RGBI")
        if distant_count != lod_count:
            raise ValueError(
                f"YMAP LOD light count mismatch: LODLightsSOA has {lod_count} entries but DistantLODLightsSOA has {distant_count}"
            )

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

    def add_car_gen(self, car_gen: CarGen) -> CarGen:
        self.car_generators.append(car_gen)
        return car_gen

    def car_gen(self, car_model: HashLike, position: tuple[float, float, float], heading: float = 0.0, **kwargs: Any) -> CarGen:
        cg = CarGen.create(car_model, position, heading, **kwargs)
        self.add_car_gen(cg)
        return cg

    def add_time_cycle_modifier(self, modifier: TimeCycleModifier) -> TimeCycleModifier:
        self.time_cycle_modifiers.append(modifier)
        return modifier

    def time_cycle_modifier(
        self,
        name: HashLike,
        position: tuple[float, float, float],
        size: tuple[float, float, float],
        **kwargs: Any,
    ) -> TimeCycleModifier:
        modifier = TimeCycleModifier.create(name, position, size, **kwargs)
        self.add_time_cycle_modifier(modifier)
        return modifier

    def suggested_path(self) -> str:
        return _suggest_resource_path(self.name, self.meta_name, ".ymap", "unnamed.ymap")

    def recalculate_extents(self, *, streaming_margin: float = 20.0, include_lod_distance: bool = True) -> "Ymap":
        bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
        entity_positions = _entity_positions(self.entities)
        if entity_positions:
            bounds = _merge_bounds(bounds, _positions_bounds(entity_positions))
        for car_gen in self.car_generators:
            position = getattr(car_gen, "position", None)
            if isinstance(position, tuple) and len(position) == 3:
                bounds = _merge_bounds(bounds, ((position[0], position[1], position[2]), (position[0], position[1], position[2])))
        for modifier in self.time_cycle_modifiers:
            min_extents = getattr(modifier, "min_extents", None)
            max_extents = getattr(modifier, "max_extents", None)
            if isinstance(min_extents, tuple) and isinstance(max_extents, tuple):
                bounds = _merge_bounds(bounds, (tuple(min_extents), tuple(max_extents)))
        for occluder in self.box_occluders:
            occluder_bounds = getattr(occluder, "bounds", None)
            if isinstance(occluder_bounds, tuple):
                bounds = _merge_bounds(bounds, occluder_bounds)
        for model in self.occlude_models:
            model_bounds = getattr(model, "bounds", None)
            if isinstance(model_bounds, tuple):
                bounds = _merge_bounds(bounds, model_bounds)
        if isinstance(self.instanced_data, InstancedMapData):
            for batch in self.instanced_data.grass_instance_list:
                bounds = _merge_bounds(bounds, batch.bounds)
        if isinstance(self.distant_lod_lights, DistantLodLightsSoa) and self.distant_lod_lights.position:
            bounds = _merge_bounds(bounds, _positions_bounds(list(self.distant_lod_lights.position)))
        if bounds is None:
            return self
        entities_min, entities_max = bounds
        self.entities_extents_min = tuple(float(value) for value in entities_min)
        self.entities_extents_max = tuple(float(value) for value in entities_max)
        padding = max(float(streaming_margin), 0.0)
        if include_lod_distance:
            padding += max((max(float(getattr(entity, "lod_dist", 0.0)), 0.0) for entity in self.entities), default=0.0)
        self.streaming_extents_min, self.streaming_extents_max = _expand_bounds(entities_min, entities_max, padding)
        return self

    def recalculate_flags(self) -> "Ymap":
        flags = YmapFlags.NONE
        content_flags = YmapContentFlags.NONE

        for entity in self.entities:
            lod_level = YmapLodLevel(int(getattr(entity, "lod_level", YmapLodLevel.DEPTH_HD) or 0))
            if lod_level in (YmapLodLevel.DEPTH_HD, YmapLodLevel.DEPTH_ORPHANHD):
                content_flags |= YmapContentFlags.ENTITIES_HD
            elif lod_level == YmapLodLevel.DEPTH_LOD:
                content_flags |= YmapContentFlags.ENTITIES_LOD
                flags |= YmapFlags.HAS_LODS
            elif lod_level == YmapLodLevel.DEPTH_SLOD1:
                content_flags |= YmapContentFlags.ENTITIES_CRITICAL
                flags |= YmapFlags.HAS_LODS
            elif lod_level in (YmapLodLevel.DEPTH_SLOD2, YmapLodLevel.DEPTH_SLOD3, YmapLodLevel.DEPTH_SLOD4):
                content_flags |= YmapContentFlags.ENTITIES_CONTAINER_LOD | YmapContentFlags.ENTITIES_CRITICAL
                flags |= YmapFlags.HAS_LODS

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
            flags |= YmapFlags.HAS_LODS
            content_flags |= YmapContentFlags.DISTANT_LOD_LIGHTS
        if self.box_occluders or self.occlude_models:
            content_flags |= YmapContentFlags.OCCLUDER

        self.flags = flags
        self.content_flags = content_flags
        return self

    def build(self, *, auto_extents: bool = False, auto_flags: bool = True) -> "Ymap":
        self.normalize_lod_lights()
        if auto_extents:
            self.recalculate_extents()
        if auto_flags:
            self.recalculate_flags()
        self.name = _ensure_base_name(self.name, ".ymap")
        return self

    def validate(self) -> list[str]:
        issues: list[str] = []
        if not self.entities and not self.box_occluders and not self.occlude_models and not self.car_generators:
            issues.append("YMAP has no entities or surfaces")
        lod_count = len(self.lod_lights) if isinstance(self.lod_lights, LodLightsSoa) else 0
        distant_count = len(self.distant_lod_lights) if isinstance(self.distant_lod_lights, DistantLodLightsSoa) else 0
        if lod_count > 0 and distant_count == 0:
            issues.append("YMAP LODLightsSOA requires matching DistantLODLightsSOA entries")
        elif lod_count > 0 and lod_count != distant_count:
            issues.append(
                f"YMAP LOD light count mismatch: LODLightsSOA has {lod_count} entries but DistantLODLightsSOA has {distant_count}"
            )
        if isinstance(self.distant_lod_lights, DistantLodLightsSoa):
            if self.distant_lod_lights.num_street_lights > len(self.distant_lod_lights):
                issues.append("YMAP DistantLODLightsSOA numStreetLights exceeds the distant light count")
        if lod_count > 0 and distant_count == lod_count:
            seen_non_street = False
            for light in self.iter_lod_lights():
                if light.is_street_light and seen_non_street:
                    issues.append("YMAP street lights must occupy the leading prefix of the paired LOD light arrays")
                    break
                if not light.is_street_light:
                    seen_non_street = True
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

    def to_bytes(self, *, version: int = 2) -> bytes:
        self.build()
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
    ) -> Path:
        if auto_extents:
            self.recalculate_extents()
        if auto_flags:
            self.recalculate_flags()
        destination = Path(path) if path is not None else Path(self.suggested_path())
        destination.write_bytes(self.to_bytes(version=version))
        return destination

    def save_into_rpf(
        self,
        archive: RpfArchive,
        path: str | Path | None = None,
        *,
        version: int = 2,
        auto_extents: bool = False,
        auto_flags: bool = True,
    ) -> RpfFileEntry:
        if auto_extents:
            self.recalculate_extents()
        if auto_flags:
            self.recalculate_flags()
        target = path if path is not None else self.suggested_path()
        return archive.add_file(target, self.to_bytes(version=version))

    def to_meta(self) -> Meta:
        return Meta(
            Name=self.meta_name or "",
            root_name_hash=meta_name("CMapData"),
            root_value=self.to_meta_root(),
            struct_infos=YMAP_STRUCT_INFOS,
            enum_infos=YMAP_ENUM_INFOS,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "Ymap":
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
        container_lods = [_coerce_container_lod(item) for item in root.get("containerLods", []) or []]
        return cls(
            name=root.get("name", 0),
            parent=root.get("parent", 0),
            flags=coerce_ymap_flags(int(root.get("flags", 0))),
            content_flags=coerce_ymap_content_flags(int(root.get("contentFlags", 0))),
            streaming_extents_min=tuple(root.get("streamingExtentsMin", (0.0, 0.0, 0.0))),
            streaming_extents_max=tuple(root.get("streamingExtentsMax", (0.0, 0.0, 0.0))),
            entities_extents_min=tuple(root.get("entitiesExtentsMin", (0.0, 0.0, 0.0))),
            entities_extents_max=tuple(root.get("entitiesExtentsMax", (0.0, 0.0, 0.0))),
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
    def from_path(cls, path: str | Path) -> "Ymap":
        return cls.from_bytes(Path(path).read_bytes())


def read_ymap(data: bytes) -> Ymap:
    return Ymap.from_bytes(data)


def save_ymap(
    ymap: Ymap,
    path: str | Path | None = None,
    *,
    version: int = 2,
    auto_extents: bool = False,
    auto_flags: bool = True,
) -> Path:
    return ymap.save(path, version=version, auto_extents=auto_extents, auto_flags=auto_flags)
