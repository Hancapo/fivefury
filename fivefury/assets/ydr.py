from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import ClassVar

from ..gamefile import GameFileType
from .base import (
    _DAT_VIRTUAL_BASE,
    ResourceTextureAsset,
    _drawable_texture_dictionary_pointer,
)


@dataclasses.dataclass(slots=True)
class YdrAsset(ResourceTextureAsset):
    kind: ClassVar[GameFileType] = GameFileType.YDR

    def iter_texture_dictionary_pointers(self) -> Iterator[tuple[str, int]]:
        texture_dictionary_pointer = _drawable_texture_dictionary_pointer(self.system_data, _DAT_VIRTUAL_BASE)
        if texture_dictionary_pointer:
            yield "embedded", texture_dictionary_pointer


__all__ = ["YdrAsset"]
