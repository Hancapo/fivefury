from __future__ import annotations

import dataclasses
from typing import Any

from ..metahash import MetaHash
from ..pso import PsoHashedString, PsoNode


@dataclasses.dataclass(slots=True, frozen=True)
class YmtStreamingRequestCommonSet:
    requests: list[MetaHash] = dataclasses.field(default_factory=list)
    raw: Any = None

    @classmethod
    def from_value(cls, value: Any) -> "YmtStreamingRequestCommonSet":
        fields = _fields(value)
        return cls(requests=_hash_list(_field(fields, "Requests", "0xA3859DF2", "hash_A3859DF2")), raw=value)


@dataclasses.dataclass(slots=True, frozen=True)
class YmtStreamingRequestFrame:
    add_list: list[MetaHash] = dataclasses.field(default_factory=list)
    remove_list: list[MetaHash] = dataclasses.field(default_factory=list)
    promote_to_hd_list: list[MetaHash] = dataclasses.field(default_factory=list)
    camera_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    camera_direction: tuple[float, float, float] = (0.0, 0.0, 0.0)
    common_add_sets: list[int] = dataclasses.field(default_factory=list)
    flags: int = 0
    raw: Any = None

    @classmethod
    def from_value(cls, value: Any) -> "YmtStreamingRequestFrame":
        fields = _fields(value)
        return cls(
            add_list=_hash_list(_field(fields, "AddList", "0x1381EA1A", "hash_1381EA1A")),
            remove_list=_hash_list(_field(fields, "RemoveList", "0xC9027173", "hash_C9027173")),
            promote_to_hd_list=_hash_list(_field(fields, "PromoteToHDList", "0x356A8659", "hash_356A8659")),
            camera_position=_vec3(_field(fields, "CamPos", "0x1547E980", "hash_1547E980")),
            camera_direction=_vec3(_field(fields, "CamDir", "0x0C8908A1", "hash_0C8908A1")),
            common_add_sets=[int(item) for item in _list(_field(fields, "CommonAddSets", "0x690D1327", "hash_690D1327"))],
            flags=int(_field(fields, "Flags", "0x4B5C4FC2", "hash_4B5C4FC2", default=0) or 0),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class YmtStreamingRequestRecord:
    frames: list[YmtStreamingRequestFrame] = dataclasses.field(default_factory=list)
    common_sets: list[YmtStreamingRequestCommonSet] = dataclasses.field(default_factory=list)
    new_style: bool = False
    raw: Any = None

    @classmethod
    def from_value(cls, value: Any) -> "YmtStreamingRequestRecord":
        fields = _fields(value)
        return cls(
            frames=[YmtStreamingRequestFrame.from_value(item) for item in _list(_field(fields, "Frames", "0x18F9F2AF", "hash_18F9F2AF"))],
            common_sets=[
                YmtStreamingRequestCommonSet.from_value(item) for item in _list(_field(fields, "CommonSets", "0xFD3C228B", "hash_FD3C228B"))
            ],
            new_style=bool(_field(fields, "NewStyle", "0x8B15154C", "hash_8B15154C", default=False)),
            raw=value,
        )

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def iter_requested_hashes(self) -> list[MetaHash]:
        seen: set[int] = set()
        result: list[MetaHash] = []
        for frame in self.frames:
            for item in [*frame.add_list, *frame.promote_to_hd_list]:
                value = int(item)
                if value not in seen:
                    seen.add(value)
                    result.append(item)
        for common_set in self.common_sets:
            for item in common_set.requests:
                value = int(item)
                if value not in seen:
                    seen.add(value)
                    result.append(item)
        return result


def _fields(value: Any) -> dict[str, Any]:
    if isinstance(value, PsoNode):
        return value.fields or {}
    if isinstance(value, dict):
        return value
    return {}


def _field(fields: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in fields:
            return fields[name]
    return default


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _hash_value(value: Any) -> int:
    if isinstance(value, PsoHashedString):
        return value.hash
    if isinstance(value, MetaHash):
        return value.uint
    if isinstance(value, str):
        return MetaHash(value).uint
    return int(value or 0)


def _hash_list(value: Any) -> list[MetaHash]:
    return [MetaHash(_hash_value(item)) for item in _list(value)]


def _vec3(value: Any) -> tuple[float, float, float]:
    if isinstance(value, tuple | list):
        items = [float(item) for item in value[:3]]
        items.extend([0.0] * (3 - len(items)))
        return (items[0], items[1], items[2])
    return (0.0, 0.0, 0.0)


__all__ = [
    "YmtStreamingRequestCommonSet",
    "YmtStreamingRequestFrame",
    "YmtStreamingRequestRecord",
]
