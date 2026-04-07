from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def find_parameter(parameters: Iterable[T], value: str | int) -> T | None:
    if isinstance(value, str):
        lowered = value.lower()
        for parameter in parameters:
            if getattr(parameter, "name", "").lower() == lowered:
                return parameter
        return None
    hash_value = int(value)
    for parameter in parameters:
        if int(getattr(parameter, "name_hash", 0)) == hash_value:
            return parameter
    return None


def find_material(materials: Iterable[T], value: str | int) -> T | None:
    if isinstance(value, str):
        lowered = value.lower()
        for material in materials:
            if getattr(material, "name", "").lower() == lowered:
                return material
            if (getattr(material, "shader_name", None) or "").lower() == lowered:
                return material
        return None
    index = int(value)
    for material in materials:
        if int(getattr(material, "index", -1)) == index:
            return material
    return None


__all__ = ["find_material", "find_parameter"]
