from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

from ..metahash import HashLike, MetaHash, coerce_meta_hash
from ..pso import PsoHashedString, PsoNode
from ..xml import add_items, child_item_values


def _hash_text(value: MetaHash | HashLike) -> str:
    hashed = coerce_meta_hash(value)
    return hashed.text or str(hashed)


def _from_hashish(value: Any) -> MetaHash:
    if isinstance(value, PsoHashedString):
        return MetaHash.from_value(value.text if value.text else value.hash)
    if isinstance(value, MetaHash):
        return value
    return MetaHash.from_value(value or 0)


def _get(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, PsoNode):
        fields = value.fields or {}
        for name in names:
            if name in fields:
                return fields[name]
        return default
    if isinstance(value, dict):
        for name in names:
            if name in value:
                return value[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _get_list(value: Any, *names: str) -> list[Any]:
    result = _get(value, *names, default=[])
    return list(result or [])


def _get_hash(value: Any, *names: str) -> MetaHash:
    return _from_hashish(_get(value, *names, default=0))


def _get_hash_list(value: Any, *names: str) -> list[MetaHash]:
    return [_from_hashish(item) for item in _get_list(value, *names)]


def _hash_items(element: ET.Element, name: str) -> list[MetaHash]:
    return child_item_values(element, name, MetaHash.from_value)


def _append_hash_items(parent: ET.Element, name: str, values: list[MetaHash]) -> None:
    add_items(parent, name, (_hash_text(value) for value in values), omit_empty=True)
