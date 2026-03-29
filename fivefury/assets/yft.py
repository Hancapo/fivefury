from __future__ import annotations

import dataclasses
from typing import ClassVar, Iterator

from ..gamefile import GameFileType
from .base import (
    _drawable_texture_dictionary_pointer,
    _read_pointer_array,
    _u32,
    _u64,
    ResourceTextureAsset,
)


@dataclasses.dataclass(slots=True)
class YftAsset(ResourceTextureAsset):
    kind: ClassVar[GameFileType] = GameFileType.YFT

    def iter_texture_dictionary_pointers(self) -> Iterator[tuple[str, int]]:
        seen: set[int] = set()

        def emit(label: str, drawable_pointer: int) -> Iterator[tuple[str, int]]:
            texture_dictionary_pointer = _drawable_texture_dictionary_pointer(self.system_data, drawable_pointer)
            if texture_dictionary_pointer and texture_dictionary_pointer not in seen:
                seen.add(texture_dictionary_pointer)
                yield label, texture_dictionary_pointer

        main_drawable_pointer = _u64(self.system_data, 0x30)
        yield from emit("drawable", main_drawable_pointer)

        drawable_array_pointer = _u64(self.system_data, 0x38)
        drawable_array_count = _u32(self.system_data, 0x48)
        for index, drawable_pointer in enumerate(
            _read_pointer_array(self.system_data, drawable_array_pointer, drawable_array_count)
        ):
            yield from emit(f"drawable_array_{index}", drawable_pointer)

        drawable_cloth_pointer = _u64(self.system_data, 0xF8)
        yield from emit("drawable_cloth", drawable_cloth_pointer)


__all__ = ["YftAsset"]
