"""Known entity layouts for direct domain reads; unknown layouts keep generic decoding."""

from functools import lru_cache, partial

from ..common import _int_enum_member
from ..map_extensions import EXTENSION_TYPES_BY_META_NAME, KNOWN_EXTENSION_TYPES, extension_from_meta
from ..map_extension_codec import extension_model_codecs
from ..meta.defs import meta_name
from ..meta.materialize import MetaModelCodec
from ..metahash import _NATIVE_HASH_BINDING
from ..vector import Quaternion, Vector3
from .defs import YMAP_STRUCT_INFOS
from .entities import EntityDef, MloInstanceDef, _entity_from_meta
from .enums import YmapContentFlags, YmapEntityFlags, YmapFlags, YmapLodLevel, YmapMloInstanceFlags, YmapPriorityLevel


def entity_array_codecs():
    # Custom registrations use the ordinary extension factory, including changes after warmup.
    enabled = tuple(cls for cls in KNOWN_EXTENSION_TYPES if EXTENSION_TYPES_BY_META_NAME.get(cls.META_NAME) is cls)
    return _entity_array_codecs(enabled)


@lru_cache(maxsize=8)
def _entity_array_codecs(enabled_extensions):
    schemas = {info.name_hash: info for info in YMAP_STRUCT_INFOS}
    extensions = extension_model_codecs(schemas, enabled_extensions)
    converters = {
        # Native scalar decoding has already produced exact Python integers.
        "archetypeName": _NATIVE_HASH_BINDING,
        "flags": partial(_int_enum_member, YmapEntityFlags),
        "lodLevel": partial(_int_enum_member, YmapLodLevel),
        "priorityLevel": partial(_int_enum_member, YmapPriorityLevel),
        "position": (Vector3, ("x", "y", "z")),
        "rotation": (Quaternion, ("x", "y", "z", "w")),
        "MLOInstflags": partial(_int_enum_member, YmapMloInstanceFlags),
    }
    codecs = {meta_name(name): MetaModelCodec(schemas[meta_name(name)], cls,
                  converters=converters, attributes={"MLOInstflags": "mlo_inst_flags"},
                  array_items={"extensions": extension_from_meta, "defaultEntitySets": _NATIVE_HASH_BINDING},
                  array_codecs={"extensions": extensions})
              for name, cls in (("CEntityDef", EntityDef), ("CMloInstanceDef", MloInstanceDef))}
    return {(meta_name("CMapData"), meta_name("entities")): codecs}


def map_model_codec(array_codecs):
    entities = array_codecs[(meta_name("CMapData"), meta_name("entities"))]
    return _map_model_codec(tuple(entities.items()))


def _from_meta_dict(model_type, value):
    return model_type.from_meta(value) if isinstance(value, dict) else value


@lru_cache(maxsize=8)
def _map_model_codec(entities):
    from .base import BlockDesc, PhysicsDictionary
    from .cargens import CarGen
    from .grass import InstancedMapData
    from .lights import DistantLodLightsSoa, LodLightsSoa
    from .model import Ymap
    from .occluders import BoxOccluder, OccludeModel
    from .timecycle import TimeCycleModifier
    from .utils import coerce_container_lod

    info = next(info for info in YMAP_STRUCT_INFOS if info.name_hash == meta_name("CMapData"))
    converters = {
        "name": _NATIVE_HASH_BINDING, "parent": _NATIVE_HASH_BINDING,
        "flags": partial(_int_enum_member, YmapFlags), "contentFlags": partial(_int_enum_member, YmapContentFlags),
        "block": BlockDesc.from_meta,
        **{name: (Vector3, ("x", "y", "z")) for name in
           ("streamingExtentsMin", "streamingExtentsMax", "entitiesExtentsMin", "entitiesExtentsMax")},
        **{name: partial(_from_meta_dict, cls) for name, cls in
           (("instancedData", InstancedMapData), ("LODLightsSOA", LodLightsSoa), ("DistantLODLightsSOA", DistantLodLightsSoa))},
    }
    items = {
        "entities": _entity_from_meta, "containerLods": coerce_container_lod,
        "physicsDictionaries": PhysicsDictionary.from_meta,
        **{name: partial(_from_meta_dict, cls) for name, cls in
           (("boxOccluders", BoxOccluder), ("occludeModels", OccludeModel),
            ("timeCycleModifiers", TimeCycleModifier), ("carGenerators", CarGen))},
    }
    return MetaModelCodec(info, Ymap, converters=converters, array_items=items,
        array_codecs={"entities": dict(entities)},
        attributes={"LODLightsSOA": "lod_lights", "DistantLODLightsSOA": "distant_lod_lights"})
