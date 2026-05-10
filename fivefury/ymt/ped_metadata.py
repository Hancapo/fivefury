from __future__ import annotations

import dataclasses
from typing import Any

from ..gtxd import TxdRelationship
from ..metahash import MetaHash
from ..pso import PsoHashedString, PsoNode


@dataclasses.dataclass(slots=True, frozen=True)
class YmtPedInitData:
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    props_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    clip_dictionary_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    expression_set_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    expression_dictionary_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    ped_type: MetaHash = dataclasses.field(default_factory=MetaHash)
    movement_clip_set: MetaHash = dataclasses.field(default_factory=MetaHash)
    ped_component_set_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    ped_component_cloth_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    ped_ik_settings_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    raw: Any = None

    @classmethod
    def from_value(cls, value: Any) -> "YmtPedInitData":
        fields = _fields(value)
        return cls(
            name=_meta_hash(_field(fields, "Name", "0xACE6443E", "hash_ACE6443E")),
            props_name=_meta_hash(_field(fields, "PropsName", "0x464AF554", "hash_464AF554")),
            clip_dictionary_name=_meta_hash(_field(fields, "ClipDictionaryName", "0x994CF78F", "hash_994CF78F")),
            expression_set_name=_meta_hash(_field(fields, "ExpressionSetName", "0x8C3E474C", "hash_8C3E474C")),
            expression_dictionary_name=_meta_hash(_field(fields, "ExpressionDictionaryName", "0x68EFE1B7", "hash_68EFE1B7")),
            ped_type=_meta_hash(_field(fields, "Pedtype", "0xB5EF3F22", "hash_B5EF3F22")),
            movement_clip_set=_meta_hash(_field(fields, "MovementClipSet", "0xC19D8347", "hash_C19D8347")),
            ped_component_set_name=_meta_hash(_field(fields, "PedComponentSetName", "0xC465D37B", "hash_C465D37B")),
            ped_component_cloth_name=_meta_hash(_field(fields, "PedComponentClothName", "0x9FB729D8", "hash_9FB729D8")),
            ped_ik_settings_name=_meta_hash(_field(fields, "PedIKSettingsName", "0x32BAC273", "hash_32BAC273")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class YmtPedMetadata:
    resident_txd: str = ""
    resident_anims: list[MetaHash] = dataclasses.field(default_factory=list)
    init_datas: list[YmtPedInitData] = dataclasses.field(default_factory=list)
    txd_relationships: list[TxdRelationship] = dataclasses.field(default_factory=list)
    multi_txd_relationships: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    raw: Any = None

    @classmethod
    def from_value(cls, value: Any) -> "YmtPedMetadata":
        fields = _fields(value)
        return cls(
            resident_txd=_string(_field(fields, "residentTxd", "0x405BBE59", "hash_405BBE59")),
            resident_anims=[_meta_hash(item) for item in _list(_field(fields, "residentAnims", "0x7A50C66E", "hash_7A50C66E"))],
            init_datas=[YmtPedInitData.from_value(item) for item in _list(_field(fields, "InitDatas", "0x5A24736F", "hash_5A24736F"))],
            txd_relationships=_txd_relationships(_field(fields, "txdRelationships", "0x069ADF93", "hash_069ADF93")),
            multi_txd_relationships=_multi_txd_relationships(_field(fields, "multiTxdRelationships", "0xD98E5646", "hash_D98E5646")),
            raw=value,
        )

    @property
    def ped_names(self) -> list[MetaHash]:
        return [item.name for item in self.init_datas]


def _fields(value: Any) -> dict[str, Any]:
    if isinstance(value, PsoNode):
        return value.fields or {}
    if isinstance(value, dict):
        return value
    return {}


def _field(fields: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in fields:
            return fields[name]
    return default


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string(value: Any) -> str:
    if isinstance(value, PsoHashedString):
        return str(MetaHash(value.hash))
    if isinstance(value, MetaHash):
        return str(value)
    return str(value or "")


def _meta_hash(value: Any) -> MetaHash:
    if isinstance(value, PsoHashedString):
        return MetaHash(value.hash)
    if isinstance(value, MetaHash):
        return value
    if isinstance(value, str):
        return MetaHash(value)
    return MetaHash(int(value or 0))


def _txd_relationships(value: Any) -> list[TxdRelationship]:
    relationships: list[TxdRelationship] = []
    for item in _list(value):
        fields = _fields(item)
        parent = _string(_field(fields, "parent", "0xA99DCC51", "hash_A99DCC51"))
        child = _string(_field(fields, "child", "0x033EC6B5", "hash_033EC6B5"))
        if parent and child:
            relationships.append(TxdRelationship(child=child, parent=parent))
    return relationships


def _multi_txd_relationships(value: Any) -> dict[str, list[str]]:
    relationships: dict[str, list[str]] = {}
    for item in _list(value):
        fields = _fields(item)
        parent = _string(_field(fields, "parent", "0xA99DCC51", "hash_A99DCC51"))
        children = [_string(child) for child in _list(_field(fields, "children", "0x0E5CA185", "hash_0E5CA185"))]
        if parent:
            relationships[parent] = [child for child in children if child]
    return relationships


__all__ = [
    "YmtPedInitData",
    "YmtPedMetadata",
]
