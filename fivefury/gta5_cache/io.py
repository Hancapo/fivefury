from __future__ import annotations

import struct
from pathlib import Path

from ..common import ByteSource, atomic_write_bytes, read_source_bytes
from ..vector import Quaternion, Vector3
from .model import (
    GTA5_CACHE_BOUND_ENTRY_SIZE,
    GTA5_CACHE_HEADER_SIZE,
    GTA5_CACHE_INTERIOR_PROXY_ENTRY_SIZE,
    GTA5_CACHE_MAP_DATA_ENTRY_SIZE,
    GTA5_CACHE_VERSION,
    Gta5CacheBound,
    Gta5CacheFileDate,
    Gta5CacheInteriorProxy,
    Gta5CacheMapData,
    Gta5CacheMode,
    Gta5CacheY,
)

_HEADER = f"[VERSION]\n{GTA5_CACHE_VERSION}\n".encode("ascii")
_FILE_DATES_START = b"<fileDates>\n"
_FILE_DATES_END = b"</fileDates>\n"
_MODULE_START = b"<module>\n"
_MODULE_END = b"</module>\n"
_MAP_DATA_STRUCT = struct.Struct("<III12f4B")
_INTERIOR_PROXY_STRUCT = struct.Struct("<IIIII13f32s")
_BOUND_STRUCT = struct.Struct("<I6fB3s")


def _read_module(
    data: bytes, offset: int, expected_name: str, entry_size: int
) -> tuple[memoryview, int]:
    if data[offset : offset + len(_MODULE_START)] != _MODULE_START:
        raise ValueError(f"missing <module> marker for {expected_name}")
    offset += len(_MODULE_START)
    line_end = data.find(b"\n", offset)
    if line_end < 0:
        raise ValueError(f"unterminated module name for {expected_name}")
    try:
        module_name = data[offset:line_end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("module name is not ASCII") from exc
    if module_name != expected_name:
        raise ValueError(f"expected module {expected_name}, found {module_name}")
    offset = line_end + 1
    if offset + 4 > len(data):
        raise ValueError(f"missing payload size for {expected_name}")
    payload_size = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    payload_end = offset + payload_size
    if payload_end > len(data):
        raise ValueError(f"{expected_name} payload extends past the file")
    if payload_size % entry_size:
        raise ValueError(
            f"{expected_name} payload size is not divisible by {entry_size}"
        )
    if data[payload_end : payload_end + len(_MODULE_END)] != _MODULE_END:
        raise ValueError(f"missing </module> marker for {expected_name}")
    return memoryview(data)[offset:payload_end], payload_end + len(_MODULE_END)


def _parse_file_dates(data: bytes, offset: int) -> tuple[list[Gta5CacheFileDate], int]:
    if data[offset : offset + len(_FILE_DATES_START)] != _FILE_DATES_START:
        raise ValueError("missing <fileDates> section")
    offset += len(_FILE_DATES_START)
    end = data.find(_FILE_DATES_END, offset)
    if end < 0:
        raise ValueError("missing </fileDates> marker")
    dates: list[Gta5CacheFileDate] = []
    for line_number, line in enumerate(data[offset:end].splitlines(), start=1):
        if not line:
            continue
        try:
            values = tuple(int(value) for value in line.split())
        except ValueError as exc:
            raise ValueError(f"invalid file date line {line_number}") from exc
        if len(values) < 2:
            raise ValueError(f"file date line {line_number} has fewer than two values")
        dates.append(Gta5CacheFileDate(values[0], values[1], values[2:]))
    return dates, end + len(_FILE_DATES_END)


def read_gta5_cache_y(
    source: ByteSource, *, mode: Gta5CacheMode = Gta5CacheMode.STANDARD
) -> Gta5CacheY:
    data = read_source_bytes(source)
    mode = mode if isinstance(mode, Gta5CacheMode) else Gta5CacheMode(mode)
    if len(data) < GTA5_CACHE_HEADER_SIZE:
        raise ValueError("GTA5 cache data is shorter than its header")
    if len(data) > mode.maximum_size:
        raise ValueError(
            f"GTA5 {mode.value} cache exceeds its {mode.maximum_size}-byte runtime limit"
        )
    if not data.startswith(_HEADER):
        raise ValueError(
            f"GTA5 cache must use unencrypted version {GTA5_CACHE_VERSION}"
        )
    if any(data[len(_HEADER) : GTA5_CACHE_HEADER_SIZE]):
        raise ValueError("encrypted or unsupported GTA5 cache header")

    file_dates, offset = _parse_file_dates(data, GTA5_CACHE_HEADER_SIZE)
    map_payload, offset = _read_module(
        data, offset, "fwMapDataStore", GTA5_CACHE_MAP_DATA_ENTRY_SIZE
    )
    proxy_payload, offset = _read_module(
        data, offset, "CInteriorProxy", GTA5_CACHE_INTERIOR_PROXY_ENTRY_SIZE
    )
    bound_payload, offset = _read_module(
        data, offset, "BoundsStore", GTA5_CACHE_BOUND_ENTRY_SIZE
    )
    if offset != len(data):
        raise ValueError(f"GTA5 cache has {len(data) - offset} trailing bytes")

    map_data: list[Gta5CacheMapData] = []
    for values in _MAP_DATA_STRUCT.iter_unpack(map_payload):
        map_data.append(
            Gta5CacheMapData(
                name_hash=values[0],
                parent_name_hash=values[1],
                content_flags=values[2],
                streaming_min=Vector3.from_iterable(values[3:6]),
                streaming_max=Vector3.from_iterable(values[6:9]),
                physics_min=Vector3.from_iterable(values[9:12]),
                physics_max=Vector3.from_iterable(values[12:15]),
                dynamic_streaming=bool(values[15]),
                contains_block_info=bool(values[16]),
                is_parent=bool(values[17]),
                reserved=values[18],
            )
        )

    interior_proxies: list[Gta5CacheInteriorProxy] = []
    for values in _INTERIOR_PROXY_STRUCT.iter_unpack(proxy_payload):
        raw_name = values[18]
        try:
            proxy_name = raw_name.split(b"\0", 1)[0].decode("ascii")
        except UnicodeDecodeError:
            proxy_name = ""
        interior_proxies.append(
            Gta5CacheInteriorProxy(
                group_id=values[0],
                floor_id=values[1],
                exit_portal_count=values[2],
                archetype_hash=values[3],
                ymap_hash=values[4],
                position=Vector3.from_iterable(values[5:8]),
                rotation=Quaternion.from_iterable(values[8:12]),
                bounds_min=Vector3.from_iterable(values[12:15]),
                bounds_max=Vector3.from_iterable(values[15:18]),
                proxy_name=proxy_name,
                reserved_name_data=raw_name,
            )
        )

    bounds = [
        Gta5CacheBound(
            name_hash=values[0],
            minimum=Vector3.from_iterable(values[1:4]),
            maximum=Vector3.from_iterable(values[4:7]),
            asset_type=values[7],
            reserved=values[8],
        )
        for values in _BOUND_STRUCT.iter_unpack(bound_payload)
    ]
    cache = Gta5CacheY(
        version=GTA5_CACHE_VERSION,
        mode=mode,
        file_dates=file_dates,
        map_data=map_data,
        interior_proxies=interior_proxies,
        bounds=bounds,
    )
    cache.validate().raise_for_errors()
    return cache


def _module(name: str, payload: bytes) -> bytes:
    return (
        _MODULE_START
        + name.encode("ascii")
        + b"\n"
        + struct.pack("<I", len(payload))
        + payload
        + _MODULE_END
    )


def build_gta5_cache_y_bytes(cache: Gta5CacheY) -> bytes:
    cache.validate().raise_for_errors()

    file_dates = bytearray(_FILE_DATES_START)
    for item in cache.file_dates:
        values = (
            int(item.name_hash),
            int(item.timestamp),
            *(int(value) for value in item.extra_values),
        )
        file_dates.extend(
            (" ".join(str(value) for value in values) + "\n").encode("ascii")
        )
    file_dates.extend(_FILE_DATES_END)

    map_payload = b"".join(
        _MAP_DATA_STRUCT.pack(
            int(item.name_hash),
            int(item.parent_name_hash),
            int(item.content_flags),
            *item.streaming_min,
            *item.streaming_max,
            *item.physics_min,
            *item.physics_max,
            int(bool(item.dynamic_streaming)),
            int(bool(item.contains_block_info)),
            int(bool(item.is_parent)),
            int(item.reserved),
        )
        for item in cache.map_data
    )
    proxy_payload = b"".join(
        _INTERIOR_PROXY_STRUCT.pack(
            int(item.group_id),
            int(item.floor_id),
            int(item.exit_portal_count),
            int(item.archetype_hash),
            int(item.ymap_hash),
            *item.position,
            *item.rotation,
            *item.bounds_min,
            *item.bounds_max,
            item.reserved_name_data
            if item.reserved_name_data is not None
            else item.proxy_name.encode("ascii").ljust(32, b"\0"),
        )
        for item in cache.interior_proxies
    )
    bound_payload = b"".join(
        _BOUND_STRUCT.pack(
            int(item.name_hash),
            *item.minimum,
            *item.maximum,
            int(item.asset_type),
            item.reserved,
        )
        for item in cache.bounds
    )
    data = (
        _HEADER.ljust(GTA5_CACHE_HEADER_SIZE, b"\0")
        + bytes(file_dates)
        + _module("fwMapDataStore", map_payload)
        + _module("CInteriorProxy", proxy_payload)
        + _module("BoundsStore", bound_payload)
    )
    if len(data) > cache.mode.maximum_size:
        raise ValueError(
            f"GTA5 {cache.mode.value} cache exceeds its {cache.mode.maximum_size}-byte runtime limit"
        )
    return data


def save_gta5_cache_y(cache: Gta5CacheY, destination: str | Path) -> Path:
    return atomic_write_bytes(destination, build_gta5_cache_y_bytes(cache))


__all__ = ["build_gta5_cache_y_bytes", "read_gta5_cache_y", "save_gta5_cache_y"]
