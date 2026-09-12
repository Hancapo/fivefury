from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, ClassVar, get_args, get_origin, get_type_hints

from .. import _native_abi3
from ..vector import Quaternion, Vector2, Vector3, Vector4
from .defs import meta_name

_VALUE_TYPES = (Vector2, Vector3, Vector4, Quaternion)


@lru_cache(maxsize=512)
def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


@lru_cache(maxsize=256)
def _model_annotations(model_type: type) -> dict[str, Any]:
    return get_type_hints(model_type)


@lru_cache(maxsize=256)
def _model_fields(model_type: type) -> tuple[dataclasses.Field, ...]:
    return dataclasses.fields(model_type)


@lru_cache(maxsize=256)
def _field_bindings(model_type: type, field_map: tuple) -> tuple:
    names = dict(field_map)
    return tuple((field.name, names.get(field.name, _snake_to_camel(field.name))) for field in _model_fields(model_type))


@dataclasses.dataclass(slots=True)
class MetaBackedStruct:
    META_NAME: ClassVar[str] = ""
    META_FIELD_MAP: ClassVar[dict[str, str]] = {}
    META_LIST_TYPES: ClassVar[dict[str, type[MetaBackedStruct]]] = {}

    def __post_init__(self) -> None:
        hints = _model_annotations(type(self))
        for field in _model_fields(type(self)):
            annotation = hints.get(field.name)
            value = getattr(self, field.name)
            if annotation in _VALUE_TYPES and not isinstance(value, annotation):
                raise TypeError(f"{type(self).__name__}.{field.name} must be a {annotation.__name__}")
            if get_origin(annotation) is list:
                element_type = get_args(annotation)[0]
                if element_type in _VALUE_TYPES and any(not isinstance(item, element_type) for item in value):
                    raise TypeError(f"{type(self).__name__}.{field.name} must contain {element_type.__name__} values")

    def to_meta(self) -> dict[str, Any]:
        serialize = self._serialize_field
        custom = getattr(serialize, "__func__", None) is not MetaBackedStruct._serialize_field
        return _native_abi3.meta_struct_values(self,
            _field_bindings(type(self), tuple(self.META_FIELD_MAP.items())),
            {"_meta_name_hash": meta_name(self.META_NAME)}, serialize, custom)

    def _serialize_field(self, attr: str, value: Any) -> Any:
        if isinstance(value, list):
            return [item.to_meta() if hasattr(item, "to_meta") else item for item in value]
        if hasattr(value, "to_meta") and not isinstance(value, (str, bytes, bytearray)):
            return value.to_meta()
        return value

    @classmethod
    def from_meta(cls, value: Any) -> MetaBackedStruct:
        if not isinstance(value, Mapping):
            return cls()
        kwargs: dict[str, Any] = {}
        for attr, meta_field in _field_bindings(cls, tuple(cls.META_FIELD_MAP.items())):
            if meta_field not in value:
                continue
            kwargs[attr] = cls._deserialize_field(attr, value.get(meta_field))
        return cls(**kwargs)

    @classmethod
    def _deserialize_field(cls, attr: str, value: Any) -> Any:
        item_type = cls.META_LIST_TYPES.get(attr)
        if item_type is not None:
            return [item_type.from_meta(item) if isinstance(item, Mapping) else item for item in (value or [])]
        annotation = _model_annotations(cls).get(attr)
        if annotation in _VALUE_TYPES:
            return annotation.from_iterable(value)
        if get_origin(annotation) is list:
            element_type = get_args(annotation)[0]
            if element_type in _VALUE_TYPES:
                return [element_type.from_iterable(item) for item in (value or [])]
        return value


__all__ = ["MetaBackedStruct"]
