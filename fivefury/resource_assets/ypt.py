from __future__ import annotations

import dataclasses
from typing import ClassVar, Iterator

from ..gamefile import GameFileType
from .base import _u64, ResourceTextureAsset


@dataclasses.dataclass(slots=True)
class YptAsset(ResourceTextureAsset):
    kind: ClassVar[GameFileType] = GameFileType.YPT

    def iter_texture_dictionary_pointers(self) -> Iterator[tuple[str, int]]:
        texture_dictionary_pointer = _u64(self.system_data, 0x20)
        if texture_dictionary_pointer:
            yield "embedded", texture_dictionary_pointer


__all__ = ["YptAsset"]
