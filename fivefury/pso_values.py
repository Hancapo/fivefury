from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from .hashing import jenk_hash
from .meta.defs import META_NAME_REVERSE
from .metahash import MetaHash
from .pso import PsoHashedString, PsoNode

T = TypeVar("T")


def fields(value: Any) -> Mapping[str, Any]:
    if isinstance(value, PsoNode):
        return value.fields or {}
    if isinstance(value, Mapping):
        return value
    return {}


def field(value: Any, name: str, *aliases: str, default: Any = None) -> Any:
    values = fields(value)
    names = (name, *aliases)
    for candidate in names:
        if candidate in values:
            return values[candidate]
    for candidate in names:
        hash_value = jenk_hash(candidate)
        for hashed_name in (f"hash_{hash_value:08X}", f"0x{hash_value:08X}"):
            if hashed_name in values:
                return values[hashed_name]
    return default


def items(value: Any, name: str, *aliases: str) -> list[Any]:
    result = field(value, name, *aliases)
    return list_value(result)


def list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def text(value: Any) -> str:
    if isinstance(value, PsoHashedString):
        return value.text or str(MetaHash(value.hash))
    if isinstance(value, MetaHash):
        return str(value)
    return str(value or "")


def meta_hash(value: Any) -> MetaHash:
    if isinstance(value, PsoHashedString):
        return MetaHash(value.hash)
    if isinstance(value, MetaHash):
        return value
    if isinstance(value, str):
        return MetaHash(value)
    return MetaHash(int(value or 0))


def hash_value(value: Any) -> int:
    return meta_hash(value).uint


def number(value: Any, default: T) -> T:
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


def boolean(value: Any, default: bool = False) -> bool:
    return default if value is None else bool(value)


def vector(
    value: Any,
    size: int = 3,
    *,
    default: tuple[float, ...] | None = None,
) -> tuple[float, ...]:
    fallback = default if default is not None else (0.0,) * size
    if len(fallback) != size:
        raise ValueError("vector default length must match size")
    if not isinstance(value, (list, tuple)):
        return fallback
    values = [float(component) for component in value[:size]]
    return tuple(values) + fallback[len(values) :]


def enum_value(enum_type: type[T], value: Any, default: T) -> T | int:
    if isinstance(value, str):
        name = value.strip()
        if name:
            token_parser = getattr(enum_type, "from_token", None)
            if token_parser is not None:
                parsed = token_parser(name)
                if parsed is not None:
                    return parsed
            try:
                return enum_type[name]
            except KeyError:
                for member in sorted(
                    enum_type, key=lambda item: len(item.name), reverse=True
                ):
                    if name.endswith(f"_{member.name}"):
                        return member
    try:
        return enum_type(int(value))
    except (TypeError, ValueError):
        return int(value) if isinstance(value, int) else default


def node_type_name(value: Any) -> str:
    if isinstance(value, PsoNode):
        return value.type_name
    if isinstance(value, Mapping):
        return str(value.get("__type__", value.get("type", "")))
    return ""


def make_name_resolver(names: tuple[str, ...]):
    mapping = {jenk_hash(name): name for name in names}

    def resolve(hash_value: int) -> str:
        return (
            mapping.get(hash_value)
            or META_NAME_REVERSE.get(hash_value)
            or f"hash_{hash_value:08X}"
        )

    return resolve


__all__ = [
    "boolean",
    "enum_value",
    "field",
    "fields",
    "hash_value",
    "items",
    "list_value",
    "make_name_resolver",
    "meta_hash",
    "node_type_name",
    "number",
    "text",
    "vector",
]
