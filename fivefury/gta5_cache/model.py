from __future__ import annotations

import dataclasses
import enum
import math
from pathlib import Path
from typing import Any

from ..authoring.context import BuildContext
from ..authoring.diagnostics import ValidationReport
from ..authoring.invariants import check_finite_aabb, check_unsigned
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

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        del context
        issues = ValidationReport()
        check_unsigned(issues, int(self.name_hash), 32, code="cache.file_date.name_hash.range", path="name_hash")
        check_unsigned(issues, self.timestamp, 63, code="cache.file_date.timestamp.range", path="timestamp")
        for index, value in enumerate(self.extra_values):
            check_unsigned(issues, value, 64, code="cache.file_date.extra_value.range", path=f"extra_values[{index}]")
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

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        del context
        issues = ValidationReport()
        for path, value, bits in (
            ("name_hash", int(self.name_hash), 32),
            ("parent_name_hash", int(self.parent_name_hash), 32),
            ("content_flags", self.content_flags, 32),
            ("reserved", self.reserved, 8),
        ):
            check_unsigned(issues, value, bits, code=f"cache.map_data.{path}.range", path=path)
        check_finite_aabb(issues, self.streaming_min, self.streaming_max, code="cache.map_data.streaming_bounds", path="streaming_bounds")
        check_finite_aabb(issues, self.physics_min, self.physics_max, code="cache.map_data.physics_bounds", path="physics_bounds")
        if self.content_flags > 0xFFFF:
            issues.issue("cache.map_data.content_flags.runtime_mask", "content_flags exceeds the runtime uint16 mask", path="content_flags")
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

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        del context
        issues = ValidationReport()
        for path, value, bits in (
            ("group_id", self.group_id, 8),
            ("floor_id", self.floor_id, 32),
            ("exit_portal_count", self.exit_portal_count, 32),
            ("archetype_hash", int(self.archetype_hash), 32),
            ("ymap_hash", int(self.ymap_hash), 32),
        ):
            check_unsigned(issues, value, bits, code=f"cache.interior_proxy.{path}.range", path=path)
        if self.group_id >= 255:
            issues.issue("cache.interior_proxy.group_id.runtime_limit", "group_id must be below 255", path="group_id")
        if self.floor_id >= 10:
            issues.issue("cache.interior_proxy.floor_id.runtime_limit", "floor_id must be below 10", path="floor_id")
        if not all(math.isfinite(value) for value in (*self.position, *self.rotation)):
            issues.issue("cache.interior_proxy.transform.non_finite", "transform contains non-finite values", path="transform")
        check_finite_aabb(issues, self.bounds_min, self.bounds_max, code="cache.interior_proxy.bounds", path="bounds")
        if (
            math.isfinite(self.bounds_min[0])
            and math.isfinite(self.bounds_max[0])
            and abs(self.bounds_max[0] - self.bounds_min[0]) >= 650.0
        ):
            issues.issue("cache.interior_proxy.bounds.x_size", "proxy bounds must be narrower than 650 units on X", path="bounds")
        try:
            encoded_name = self.proxy_name.encode("ascii")
        except UnicodeEncodeError:
            issues.issue("cache.interior_proxy.name.ascii", "proxy_name must be ASCII", path="proxy_name")
        else:
            if len(encoded_name) >= 32:
                issues.issue("cache.interior_proxy.name.length", "proxy_name must fit in 31 ASCII bytes", path="proxy_name")
        if self.reserved_name_data is not None and len(self.reserved_name_data) != 32:
            issues.issue("cache.interior_proxy.reserved_name_data.length", "reserved_name_data must contain exactly 32 bytes", path="reserved_name_data")
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

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        del context
        issues = ValidationReport()
        check_unsigned(issues, int(self.name_hash), 32, code="cache.bound.name_hash.range", path="name_hash")
        check_unsigned(issues, int(self.asset_type), 8, code="cache.bound.asset_type.range", path="asset_type")
        check_finite_aabb(issues, self.minimum, self.maximum, code="cache.bound.aabb", path="bounds")
        if len(self.reserved) != 3:
            issues.issue("cache.bound.reserved.length", "reserved must contain exactly three bytes", path="reserved")
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

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        issues = ValidationReport()
        if self.version != GTA5_CACHE_VERSION:
            issues.issue("cache.version.unsupported", f"version must be {GTA5_CACHE_VERSION}", path="version")
        if self.mode is Gta5CacheMode.DLC and not self.file_dates:
            issues.issue("cache.dlc.file_dates.empty", "DLC caches require at least one RPF file date", path="file_dates")
        for collection_name, collection in (
            ("file_dates", self.file_dates),
            ("map_data", self.map_data),
            ("interior_proxies", self.interior_proxies),
            ("bounds", self.bounds),
        ):
            for index, item in enumerate(collection):
                issues.extend(item.validate(context=context), path=f"{collection_name}[{index}]")
        for collection_name, collection, attribute in (
            ("file_dates", self.file_dates, "name_hash"),
            ("map_data", self.map_data, "name_hash"),
            ("bounds", self.bounds, "name_hash"),
        ):
            seen: set[int] = set()
            for index, item in enumerate(collection):
                value = int(getattr(item, attribute))
                if value in seen:
                    issues.issue(
                        "cache.hash.duplicate",
                        f"duplicate hash 0x{value:08X}",
                        path=f"{collection_name}[{index}].{attribute}",
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
