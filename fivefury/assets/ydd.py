from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import ClassVar

from ..gamefile import GameFileType
from .base import (
    ResourceTextureAsset,
    _drawable_texture_dictionary_pointer,
    _read_pointer_array,
    _u16,
    _u64,
)


@dataclasses.dataclass(slots=True)
class YddAsset(ResourceTextureAsset):
    kind: ClassVar[GameFileType] = GameFileType.YDD

    def iter_texture_dictionary_pointers(self) -> Iterator[tuple[str, int]]:
        count = _u16(self.system_data, 0x38)
        drawables_pointer = _u64(self.system_data, 0x30)
        for index, drawable_pointer in enumerate(_read_pointer_array(self.system_data, drawables_pointer, count)):
            texture_dictionary_pointer = _drawable_texture_dictionary_pointer(self.system_data, drawable_pointer)
            if texture_dictionary_pointer:
                yield f"drawable_{index}", texture_dictionary_pointer


__all__ = ["YddAsset"]
