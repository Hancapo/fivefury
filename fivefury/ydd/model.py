from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TypeAlias

from ..hashing import jenk_hash
from ..ydr import Ydr, YdrBuild

YddDrawableInput: TypeAlias = "YddDrawable | Ydr | YdrBuild"
YddDrawableCollection: TypeAlias = Mapping[str, YddDrawableInput] | Sequence[YddDrawableInput]


def _drawable_input_name(value: YddDrawableInput, index: int) -> str:
    if isinstance(value, YddDrawable) and value.name:
        return value.name
    return str(getattr(value, "name", "") or f"drawable_{index}")


def _coerce_drawable_input(
    value: YddDrawableInput,
    index: int,
    *,
    name: str | None = None,
    name_hash: int | None = None,
) -> "YddDrawable":
    if isinstance(value, YddDrawable):
        drawable_name = str(name or value.name or f"drawable_{index}")
        drawable_hash = int(name_hash if name_hash is not None else value.name_hash or jenk_hash(drawable_name)) & 0xFFFFFFFF
        return YddDrawable(name_hash=drawable_hash, name=drawable_name, drawable=value.drawable)
    drawable_name = str(name or _drawable_input_name(value, index))
    return YddDrawable(
        name_hash=int(name_hash if name_hash is not None else jenk_hash(drawable_name)) & 0xFFFFFFFF,
        name=drawable_name,
        drawable=value,
    )


def _iter_drawable_inputs(drawables: YddDrawableCollection) -> Iterator[tuple[str | None, YddDrawableInput]]:
    if isinstance(drawables, Mapping):
        for name, drawable in drawables.items():
            yield str(name), drawable
        return
    for drawable in drawables:
        yield None, drawable


@dataclasses.dataclass(slots=True)
class YddDrawable:
    name_hash: int
    drawable: Ydr | YdrBuild
    name: str = ""

    def __post_init__(self) -> None:
        self.name_hash = int(self.name_hash) & 0xFFFFFFFF
        if not self.name:
            self.name = f"hash_{self.name_hash:08X}"


@dataclasses.dataclass(slots=True)
class Ydd:
    version: int = 165
    path: str = ""
    drawables: list[YddDrawable] = dataclasses.field(default_factory=list)

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, *, path: str = "") -> "Ydd":
        from . import read_ydd

        return read_ydd(data, path=path)

    @property
    def name(self) -> str:
        if self.path:
            return Path(self.path).stem
        return "drawable_dictionary"

    @property
    def drawable_count(self) -> int:
        return len(self.drawables)

    @property
    def names(self) -> list[str]:
        return [entry.name for entry in self.drawables]

    @classmethod
    def from_drawables(
        cls,
        drawables: YddDrawableCollection,
        *,
        name: str = "",
        version: int = 165,
    ) -> "Ydd":
        ydd = cls(version=int(version), path=name)
        for index, (drawable_name, drawable) in enumerate(_iter_drawable_inputs(drawables)):
            ydd.drawables.append(_coerce_drawable_input(drawable, index, name=drawable_name))
        return ydd

    def iter_drawables(self) -> Iterator[YddDrawable]:
        yield from self.drawables

    def with_drawables(
        self,
        drawables: YddDrawableCollection,
    ) -> "Ydd":
        self.drawables = [
            _coerce_drawable_input(drawable, index, name=drawable_name)
            for index, (drawable_name, drawable) in enumerate(_iter_drawable_inputs(drawables))
        ]
        return self

    def get(self, value: str | int) -> YddDrawable | None:
        if isinstance(value, int):
            if 0 <= value < len(self.drawables):
                return self.drawables[value]
            target_hash = int(value) & 0xFFFFFFFF
        else:
            target_name = str(value).lower()
            target_hash = int(jenk_hash(target_name)) & 0xFFFFFFFF
            for entry in self.drawables:
                if entry.name.lower() == target_name:
                    return entry

        for entry in self.drawables:
            if entry.name_hash == target_hash:
                return entry
        return None

    def require(self, value: str | int) -> YddDrawable:
        entry = self.get(value)
        if entry is None:
            raise KeyError(f"Unknown YDD drawable '{value}'")
        return entry

    def to_bytes(self, *, shader_library=None) -> bytes:
        from .writer import build_ydd_bytes

        return build_ydd_bytes(self, shader_library=shader_library)

    def save(self, destination: str | Path, *, shader_library=None) -> Path:
        from .writer import save_ydd

        return save_ydd(self, destination, shader_library=shader_library)


__all__ = [
    "Ydd",
    "YddDrawable",
    "YddDrawableCollection",
    "YddDrawableInput",
]
