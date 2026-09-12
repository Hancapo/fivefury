import dataclasses

import pytest

from fivefury.map_extensions import (
    EXTENSION_TYPES_BY_META_NAME,
    KNOWN_EXTENSION_TYPES,
    CapsuleBoundDef,
    LightAttrDef,
    LightEffectExtension,
    LightExtension,
    ScriptChildExtension,
    ScriptExtension,
    VerletClothCustomBoundsExtension,
    extensions_from_meta,
)
from fivefury.meta import MetaBuilder, ParsedMeta
from fivefury.meta.defs import meta_name
from fivefury.vector import Vector3
from fivefury.ymap import EntityDef, Ymap
from fivefury.ymap.defs import YMAP_ENUM_INFOS, YMAP_STRUCT_INFOS


@pytest.mark.parametrize("nested_map", [False, True])
def test_entity_codecs_preserve_generic_inspection_and_unknown_extension_payloads(nested_map):
    entity = EntityDef(archetype_name="nested", guid=91)
    unknown_extension = Ymap(entities=[entity]).to_meta_root() if nested_map else entity.to_meta()
    source = Ymap(name="typed", entities=[EntityDef(archetype_name="outer", extensions=[unknown_extension])])
    data = source.to_bytes()
    generic = ParsedMeta.from_bytes(data).decoded_root
    assert isinstance(generic["entities"][0], dict)
    restored = Ymap.from_bytes(data)
    assert isinstance(restored.entities[0], EntityDef)
    nested = restored.entities[0].extensions[0]
    if nested_map:
        assert isinstance(nested, dict) and nested["_meta_name"] == "CMapData"
        nested = nested["entities"][0]
    assert isinstance(nested, dict) and nested["_meta_name"] == "CEntityDef"
    assert nested["guid"] == 91
    assert ParsedMeta.from_bytes(restored.to_bytes()).decoded_root == generic


@pytest.mark.parametrize("different_root", [False, True])
def test_entity_read_uses_the_files_layout_when_known_schema_differs(different_root):
    entity_hash = meta_name("CEntityDef")
    original = next(info for info in YMAP_STRUCT_INFOS if info.name_hash == entity_hash)
    offsets = {field.name: field.data_offset for field in original.entries}
    swapped = {meta_name("guid"): offsets["tintValue"], meta_name("tintValue"): offsets["guid"]}
    variant = dataclasses.replace(original, key=original.key + 1,
        entries=[dataclasses.replace(field, data_offset=swapped.get(field.name_hash, field.data_offset))
                 for field in original.entries])
    schemas = [variant if info.name_hash == entity_hash else info for info in YMAP_STRUCT_INFOS]
    if different_root:
        schemas = [dataclasses.replace(info, key=info.key + 1) if info.name_hash == meta_name("CMapData") else info for info in schemas]
    source = Ymap(name="variant", entities=[EntityDef(archetype_name="test", guid=17, tint_value=29)])
    data = MetaBuilder(struct_infos=schemas, enum_infos=YMAP_ENUM_INFOS).build(meta_name("CMapData"), source.to_meta_root())
    restored = Ymap.from_bytes(data).entities[0]
    assert restored.guid == 17 and restored.tint_value == 29
    first, second = ParsedMeta.from_bytes(data), ParsedMeta.from_bytes(data)
    first.struct_infos[entity_hash].entries.clear()
    assert len(second.struct_infos[entity_hash].entries) == len(original.entries)


def test_known_extension_codecs_match_generic_materialization_and_allow_edits():
    extensions = {cls: cls() for cls in KNOWN_EXTENSION_TYPES}
    extensions[LightEffectExtension].instances = [LightAttrDef(posn=Vector3(1, 2, 3), colour=(10, 20, 30))]
    extensions[LightEffectExtension].instances[0].colour = (1, 2, 3)
    extensions[LightEffectExtension].instances[0].vol_outer_colour = (1, 0, 1)
    extensions[ScriptExtension].children = [ScriptChildExtension(position=Vector3(4, 5, 6))]
    extensions[VerletClothCustomBoundsExtension].collision_data = [CapsuleBoundDef(owner_name="capsule")]
    data = Ymap(entities=[EntityDef(extensions=list(extensions.values()))]).to_bytes()
    generic = ParsedMeta.from_bytes(data).decoded_root["entities"][0]["extensions"]
    restored = Ymap.from_bytes(data)
    assert restored.entities[0].extensions == extensions_from_meta(generic)
    light = next(value for value in restored.entities[0].extensions if isinstance(value, LightEffectExtension))
    light.instances[0].posn = Vector3(7, 8, 9)
    edited = Ymap.from_bytes(restored.to_bytes())
    assert edited.entities[0].extensions == restored.entities[0].extensions


def test_extension_registry_replacements_apply_after_codec_warmup(monkeypatch):
    data = Ymap(entities=[EntityDef(extensions=[LightExtension()])]).to_bytes()
    assert type(Ymap.from_bytes(data).entities[0].extensions[0]) is LightExtension
    class CustomLight(LightExtension):
        pass
    monkeypatch.setitem(EXTENSION_TYPES_BY_META_NAME, LightExtension.META_NAME, CustomLight)
    assert type(Ymap.from_bytes(data).entities[0].extensions[0]) is CustomLight
    class CustomMap(Ymap):
        pass
    assert type(CustomMap.from_bytes(data)) is CustomMap
