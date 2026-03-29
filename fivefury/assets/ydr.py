from __future__ import annotations

import dataclasses
from typing import ClassVar, Iterator

from ..gamefile import GameFileType
from .base import _DAT_VIRTUAL_BASE, _drawable_texture_dictionary_pointer, ResourceTextureAsset


@dataclasses.dataclass(slots=True)
class YdrAsset(ResourceTextureAsset):
    kind: ClassVar[GameFileType] = GameFileType.YDR

    def iter_texture_dictionary_pointers(self) -> Iterator[tuple[str, int]]:
        texture_dictionary_pointer = _drawable_texture_dictionary_pointer(self.system_data, _DAT_VIRTUAL_BASE)
        if texture_dictionary_pointer:
            yield "embedded", texture_dictionary_pointer


__all__ = ["YdrAsset"]
