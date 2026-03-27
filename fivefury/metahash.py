from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from .hashing import jenk_hash


class MetaHash:
    __slots__ = ("_value",)

    @classmethod
    def from_value(cls, value: "HashLike | None" = 0, *, text: str | None = None) -> "MetaHash":
        if isinstance(value, MetaHash):
            if text is None:
                text = value.text
            return cls(text if text is not None else value.raw)
        if text is not None:
            normalized = str(text).strip()
            return cls(normalized if normalized else value)
        return cls(value)

    def __init__(self, value: "HashLike | None" = 0) -> None:
        if isinstance(value, MetaHash):
            self._value = value.raw
        elif value in (None, ""):
            self._value = 0
        elif isinstance(value, str):
            self._value = value
        else:
            self._value = int(value)

    @property
    def raw(self) -> int | str:
        return self._value

    @property
    def hash(self) -> int:
        return self.uint

    @property
    def uint(self) -> int:
        if isinstance(self._value, str):
            return jenk_hash(self._value)
        return int(self._value)

    @property
    def meta_hash(self) -> int:
        return self.uint

    @property
    def text(self) -> str | None:
        if isinstance(self._value, str):
            return self._value or None
        if self.uint == 0:
            return None
        from .resolver import resolve_hash

        return resolve_hash(self.uint)

    @property
    def string(self) -> str | None:
        return self.text

    @property
    def resolved(self) -> int | str:
        text = self.text
        return text if text is not None else self.uint

    @property
    def hex(self) -> str:
        return f"{self.uint:08X}"

    def __int__(self) -> int:
        return self.uint

    def __index__(self) -> int:
        return self.uint

    def __str__(self) -> str:
        text = self.text
        if text is not None:
            return text
        return "" if self.uint == 0 else f"0x{self.uint:08X}"

    def __repr__(self) -> str:
        if isinstance(self._value, str):
            return f"MetaHash({self._value!r})"
        return f"MetaHash(0x{self.uint:08X})"

    def __bool__(self) -> bool:
        return self.uint != 0

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MetaHash):
            return self.uint == other.uint
        if other in (None, ""):
            return self.uint == 0
        if isinstance(other, str):
            if isinstance(self._value, str):
                return self._value == other
            text = self.text
            return text == other if text is not None else self.uint == jenk_hash(other)
        try:
            return self.uint == int(other)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False

    def __hash__(self) -> int:
        return hash(self.uint)


HashString = MetaHash
HashLike = MetaHash | int | str


def coerce_meta_hash(value: HashLike | None) -> MetaHash:
    return value if isinstance(value, MetaHash) else MetaHash(value)


def coerce_meta_hash_list(values: Iterable[HashLike] | None) -> list[MetaHash]:
    if values is None:
        return []
    return [coerce_meta_hash(value) for value in values]


class MetaHashFieldsMixin:
    __slots__ = ()

    _hash_fields: ClassVar[tuple[str, ...]] = ()
    _hash_list_fields: ClassVar[tuple[str, ...]] = ()

    def __setattr__(self, name: str, value: Any) -> None:
        if name in type(self)._hash_fields:
            object.__setattr__(self, name, coerce_meta_hash(value))
            return
        if name in type(self)._hash_list_fields:
            object.__setattr__(self, name, coerce_meta_hash_list(value))
            return
        object.__setattr__(self, name, value)


__all__ = [
    "HashLike",
    "HashString",
    "MetaHash",
    "MetaHashFieldsMixin",
    "coerce_meta_hash",
    "coerce_meta_hash_list",
]
