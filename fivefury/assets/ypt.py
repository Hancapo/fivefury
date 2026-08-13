from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import ClassVar

from ..gamefile import GameFileType
from .base import ResourceTextureAsset, _u64


@dataclasses.dataclass(slots=True)
class YptAsset(ResourceTextureAsset):
    kind: ClassVar[GameFileType] = GameFileType.YPT

    def iter_texture_dictionary_pointers(self) -> Iterator[tuple[str, int]]:
        texture_dictionary_pointer = _u64(self.system_data, 0x20)
        if texture_dictionary_pointer:
            yield "embedded", texture_dictionary_pointer


__all__ = ["YptAsset"]
