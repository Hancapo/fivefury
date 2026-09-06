from __future__ import annotations

import dataclasses
from typing import Any
from weakref import WeakSet

from ....matrix import Matrix4
from ....vector import Quaternion, Vector3, Vector4
from .flags import YDR_BONE_ANIMATABLE_FLAGS, YdrBoneFlags
from .lookups import _BoneLookups


def calculate_bone_tag(name: str) -> int:
    hash_value = 0
    for char in str(name):
        code = ord(char)
        if 97 <= code <= 122:
            code -= 32
        hash_value = ((hash_value << 4) + code) & 0xFFFFFFFF
        high = hash_value & 0xF0000000
        if high:
            hash_value ^= high >> 24
        hash_value &= ~high
    return int((hash_value % 0xFE8F) + 0x170)


@dataclasses.dataclass(slots=True)
class YdrBone:
    name: str = ""
    tag: int = 0
    index: int = 0
    parent_index: int = -1
    next_sibling_index: int = -1
    flags: YdrBoneFlags = YDR_BONE_ANIMATABLE_FLAGS
    rotation: Quaternion = dataclasses.field(default_factory=Quaternion)
    translation: Vector3 = dataclasses.field(default_factory=Vector3)
    scale: Vector3 = dataclasses.field(default_factory=lambda: Vector3(1.0, 1.0, 1.0))
    transform_unk: Vector4 = dataclasses.field(default_factory=Vector4)
    inverse_bind_transform: Matrix4 | None = None
    unknown_1ch: int = 0
    unknown_2ch: float = 1.0
    unknown_34h: int = 0
    unknown_48h: int = 0
    _lookup_owners: WeakSet[_BoneLookups] | None = dataclasses.field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        if name in ("name", "tag", "parent_index"):
            owners = getattr(self, "_lookup_owners", None)
            if owners:
                for lookups in owners:
                    lookups.dirty = True

    def __getstate__(self) -> dict[str, Any]:
        return {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
            if field.init
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        object.__setattr__(self, "_lookup_owners", None)
        for name, value in state.items():
            object.__setattr__(self, name, value)
