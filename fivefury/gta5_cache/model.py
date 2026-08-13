from __future__ import annotations

import dataclasses
import enum
import math
from pathlib import Path
from typing import Any

from ..binary import fits_unsigned
from ..common import atomic_write_bytes
from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin

GTA5_CACHE_VERSION = 46
GTA5_CACHE_HEADER_SIZE = 100
GTA5_CACHE_STANDARD_MAX_SIZE = 1500 * 1024
GTA5_CACHE_DLC_MAX_SIZE = 256 * 1024
GTA5_CACHE_MAP_DATA_ENTRY_SIZE = 64
GTA5_CACHE_INTERIOR_PROXY_ENTRY_SIZE = 104
GTA5_CACHE_BOUND_ENTRY_SIZE = 32


class Gta5CacheMode(enum.Enum):
    STANDARD = "standard"
    DLC = "dlc"

    @property
    def maximum_size(self) -> int:
        return (
            GTA5_CACHE_DLC_MAX_SIZE
            if self is Gta5CacheMode.DLC
            else GTA5_CACHE_STANDARD_MAX_SIZE
        )


class Gta5CacheBoundAssetType(enum.IntEnum):
    MOVER = 0
    WEAPON = 1
    MATERIAL = 2


def _vector3(value: Any) -> tuple[float, float, float]:
    try:
        x, y, z = value
    except (TypeError, ValueError) as exc:
        raise ValueError("expected three vector components") from exc
    return (float(x), float(y), float(z))


def _aabb_issues(
    label: str, minimum: tuple[float, float, float], maximum: tuple[float, float, float]
) -> list[str]:
    if not all(math.isfinite(value) for value in (*minimum, *maximum)):
        return [f"{label} contains non-finite values"]
    if any(minimum[axis] > maximum[axis] for axis in range(3)):
        return [f"{label} is inverted"]
    return []


def _uint_issue(label: str, value: int, bits: int) -> str | None:
    if not fits_unsigned(value, bits):
        return f"{label} is outside the uint{bits} range"
    return None


@dataclasses.dataclass(slots=True)
class Gta5CacheFileDate(MetaHashFieldsMixin):
    _hash_fields = ("name_hash",)

    name_hash: MetaHash | HashLike
    timestamp: int
    extra_values: tuple[int, ...] = ()

    @classmethod
    def from_file(cls, image_name: HashLike, path: str | Path) -> Gta5CacheFileDate:
        timestamp = Path(path).stat().st_mtime_ns // 100 + 116_444_736_000_000_000
        return cls(name_hash=image_name, timestamp=timestamp)

    def validate(self) -> list[str]:
        issues = [
            issue
            for issue in (
                _uint_issue("name_hash", int(self.name_hash), 32),
                _uint_issue("timestamp", self.timestamp, 63),
            )
            if issue
        ]
        for index, value in enumerate(self.extra_values):
            issue = _uint_issue(f"extra_values[{index}]", value, 64)
            if issue:
                issues.append(issue)
        return issues


@dataclasses.dataclass(slots=True)
class Gta5CacheMapData(MetaHashFieldsMixin):
    _hash_fields = ("name_hash", "parent_name_hash")

    name_hash: MetaHash | HashLike
    parent_name_hash: MetaHash | HashLike = 0
    content_flags: int = 0
    streaming_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    streaming_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    physics_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    physics_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    dynamic_streaming: bool = True
    contains_block_info: bool = False
    is_parent: bool = False
    reserved: int = 0

    def __post_init__(self) -> None:
        self.streaming_min = _vector3(self.streaming_min)
        self.streaming_max = _vector3(self.streaming_max)
        self.physics_min = _vector3(self.physics_min)
        self.physics_max = _vector3(self.physics_max)

    def validate(self) -> list[str]:
        issues = [
            issue
            for issue in (
                _uint_issue("name_hash", int(self.name_hash), 32),
                _uint_issue("parent_name_hash", int(self.parent_name_hash), 32),
                _uint_issue("content_flags", self.content_flags, 32),
                _uint_issue("reserved", self.reserved, 8),
            )
            if issue
        ]
        issues.extend(
            _aabb_issues("streaming bounds", self.streaming_min, self.streaming_max)
        )
        issues.extend(
            _aabb_issues("physics bounds", self.physics_min, self.physics_max)
        )
        if self.content_flags > 0xFFFF:
            issues.append("content_flags exceeds the runtime uint16 mask")
        return issues


@dataclasses.dataclass(slots=True)
class Gta5CacheInteriorProxy(MetaHashFieldsMixin):
    _hash_fields = ("archetype_hash", "ymap_hash")

    group_id: int
    floor_id: int
    exit_portal_count: int
    archetype_hash: MetaHash | HashLike
    ymap_hash: MetaHash | HashLike
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    bounds_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounds_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    proxy_name: str = ""
    reserved_name_data: bytes | None = None

    def __post_init__(self) -> None:
        self.position = _vector3(self.position)
        self.bounds_min = _vector3(self.bounds_min)
        self.bounds_max = _vector3(self.bounds_max)
        try:
            x, y, z, w = self.rotation
        except (TypeError, ValueError) as exc:
            raise ValueError("expected four quaternion components") from exc
        self.rotation = (float(x), float(y), float(z), float(w))
        if self.reserved_name_data is not None:
            self.reserved_name_data = bytes(self.reserved_name_data)

    def validate(self) -> list[str]:
        issues = [
            issue
            for issue in (
                _uint_issue("group_id", self.group_id, 8),
                _uint_issue("floor_id", self.floor_id, 32),
                _uint_issue("exit_portal_count", self.exit_portal_count, 32),
                _uint_issue("archetype_hash", int(self.archetype_hash), 32),
                _uint_issue("ymap_hash", int(self.ymap_hash), 32),
            )
            if issue
        ]
        if self.group_id >= 255:
            issues.append("group_id must be below 255")
        if self.floor_id >= 10:
            issues.append("floor_id must be below 10")
        if not all(math.isfinite(value) for value in (*self.position, *self.rotation)):
            issues.append("transform contains non-finite values")
        issues.extend(_aabb_issues("proxy bounds", self.bounds_min, self.bounds_max))
        if (
            math.isfinite(self.bounds_min[0])
            and math.isfinite(self.bounds_max[0])
            and abs(self.bounds_max[0] - self.bounds_min[0]) >= 650.0
        ):
            issues.append("proxy bounds must be narrower than 650 units on X")
        try:
            encoded_name = self.proxy_name.encode("ascii")
        except UnicodeEncodeError:
            issues.append("proxy_name must be ASCII")
        else:
            if len(encoded_name) >= 32:
                issues.append("proxy_name must fit in 31 ASCII bytes")
        if self.reserved_name_data is not None and len(self.reserved_name_data) != 32:
            issues.append("reserved_name_data must contain exactly 32 bytes")
        return issues


@dataclasses.dataclass(slots=True)
class Gta5CacheBound(MetaHashFieldsMixin):
    _hash_fields = ("name_hash",)

    name_hash: MetaHash | HashLike
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    asset_type: Gta5CacheBoundAssetType | int = Gta5CacheBoundAssetType.MOVER
    reserved: bytes = b"\0\0\0"

    def __post_init__(self) -> None:
        self.minimum = _vector3(self.minimum)
        self.maximum = _vector3(self.maximum)
        self.asset_type = Gta5CacheBoundAssetType(int(self.asset_type))
        self.reserved = bytes(self.reserved)

    @classmethod
    def from_bound(
        cls,
        name: HashLike,
        bound: Any,
        *,
        asset_type: Gta5CacheBoundAssetType | int = Gta5CacheBoundAssetType.MOVER,
    ) -> Gta5CacheBound:
        return cls(
            name_hash=name,
            minimum=bound.box_min,
            maximum=bound.box_max,
            asset_type=asset_type,
        )

    @classmethod
    def from_ybn(
        cls,
        name: HashLike,
        ybn: Any,
        *,
        asset_type: Gta5CacheBoundAssetType | int = Gta5CacheBoundAssetType.MOVER,
    ) -> Gta5CacheBound:
        return cls.from_bound(name, ybn.bound, asset_type=asset_type)

    def validate(self) -> list[str]:
        issues = [
            issue
            for issue in (
                _uint_issue("name_hash", int(self.name_hash), 32),
                _uint_issue("asset_type", int(self.asset_type), 8),
            )
            if issue
        ]
        issues.extend(_aabb_issues("bound", self.minimum, self.maximum))
        if len(self.reserved) != 3:
            issues.append("reserved must contain exactly three bytes")
        return issues


@dataclasses.dataclass(slots=True)
class Gta5CacheY:
    file_dates: list[Gta5CacheFileDate] = dataclasses.field(default_factory=list)
    map_data: list[Gta5CacheMapData] = dataclasses.field(default_factory=list)
    interior_proxies: list[Gta5CacheInteriorProxy] = dataclasses.field(
        default_factory=list
    )
    bounds: list[Gta5CacheBound] = dataclasses.field(default_factory=list)
    version: int = GTA5_CACHE_VERSION
    mode: Gta5CacheMode = Gta5CacheMode.STANDARD

    def __post_init__(self) -> None:
        if not isinstance(self.mode, Gta5CacheMode):
            self.mode = Gta5CacheMode(self.mode)

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.version != GTA5_CACHE_VERSION:
            issues.append(f"version must be {GTA5_CACHE_VERSION}")
        if self.mode is Gta5CacheMode.DLC and not self.file_dates:
            issues.append("DLC caches require at least one RPF file date")
        for collection_name, collection in (
            ("file_dates", self.file_dates),
            ("map_data", self.map_data),
            ("interior_proxies", self.interior_proxies),
            ("bounds", self.bounds),
        ):
            for index, item in enumerate(collection):
                issues.extend(
                    f"{collection_name}[{index}]: {issue}" for issue in item.validate()
                )
        for collection_name, collection, attribute in (
            ("file_dates", self.file_dates, "name_hash"),
            ("map_data", self.map_data, "name_hash"),
            ("bounds", self.bounds, "name_hash"),
        ):
            seen: set[int] = set()
            for index, item in enumerate(collection):
                value = int(getattr(item, attribute))
                if value in seen:
                    issues.append(
                        f"{collection_name}[{index}]: duplicate hash 0x{value:08X}"
                    )
                seen.add(value)
        return issues

    def to_bytes(self) -> bytes:
        from .io import build_gta5_cache_y_bytes

        return build_gta5_cache_y_bytes(self)

    @classmethod
    def from_bytes(
        cls,
        data: bytes | bytearray | memoryview,
        *,
        mode: Gta5CacheMode = Gta5CacheMode.STANDARD,
    ) -> Gta5CacheY:
        from .io import read_gta5_cache_y

        return read_gta5_cache_y(data, mode=mode)

    def save(self, destination: str | Path) -> Path:
        return atomic_write_bytes(destination, self.to_bytes())


__all__ = [
    "GTA5_CACHE_BOUND_ENTRY_SIZE",
    "GTA5_CACHE_DLC_MAX_SIZE",
    "GTA5_CACHE_HEADER_SIZE",
    "GTA5_CACHE_INTERIOR_PROXY_ENTRY_SIZE",
    "GTA5_CACHE_MAP_DATA_ENTRY_SIZE",
    "GTA5_CACHE_STANDARD_MAX_SIZE",
    "GTA5_CACHE_VERSION",
    "Gta5CacheBound",
    "Gta5CacheBoundAssetType",
    "Gta5CacheFileDate",
    "Gta5CacheInteriorProxy",
    "Gta5CacheMapData",
    "Gta5CacheMode",
    "Gta5CacheY",
]
