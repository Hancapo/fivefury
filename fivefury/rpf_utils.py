from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .resource import get_resource_flags_from_size, get_resource_size_from_flags, parse_rsc7

RPF_MAGIC = 0x52504637
RSC7_MAGIC = 0x37435352
RPF_BLOCK_SIZE = 512


def _normalize_path(path: str | Path) -> str:
    text = str(path).replace("\\", "/").strip()
    while "//" in text:
        text = text.replace("//", "/")
    return text.strip("/")


def _normalize_key(path: str | Path) -> str:
    return _normalize_path(path).lower()


def _archive_name(name: str) -> str:
    return name if name.lower().endswith(".rpf") else f"{name}.rpf"


def _coerce_file_bytes(data: bytes | bytearray | memoryview | object) -> bytes:
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    if hasattr(data, "to_bytes"):
        payload = data.to_bytes()  # type: ignore[assignment]
    elif hasattr(data, "build"):
        payload = data.build()  # type: ignore[assignment]
    else:
        raise TypeError("data must be bytes-like or expose to_bytes()/build()")
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("to_bytes()/build() must return bytes-like data")
    return bytes(payload)


def _ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def _pad(data: bytes, block_size: int) -> bytes:
    rem = len(data) % block_size
    if rem == 0:
        return data
    return data + (b"\x00" * (block_size - rem))


def _compress_deflate(data: bytes, level: int = 9) -> bytes:
    comp = zlib.compressobj(level=level, method=zlib.DEFLATED, wbits=-15)
    return comp.compress(data) + comp.flush()


def _decompress_deflate(data: bytes) -> bytes:
    if not data:
        return b""
    for wbits in (-15, zlib.MAX_WBITS, zlib.MAX_WBITS | 32):
        try:
            return zlib.decompress(data, wbits)
        except zlib.error:
            pass
    raise ValueError("Unable to decompress deflate payload")


def _is_rsc7(data: bytes) -> bool:
    return len(data) >= 4 and struct.unpack_from("<I", data, 0)[0] == RSC7_MAGIC


def _resource_version_from_flags(system_flags: int, graphics_flags: int) -> int:
    return (((system_flags >> 28) & 0xF) << 4) | ((graphics_flags >> 28) & 0xF)


def _resource_flags_from_size(size: int, version: int = 0) -> int:
    return get_resource_flags_from_size(size, version)


def _size_from_resource_flags(flags: int) -> int:
    return get_resource_size_from_flags(flags)


def _split_rsc7(data: bytes) -> tuple[int, int, int, bytes]:
    header, payload = parse_rsc7(data)
    return header.version, header.system_flags, header.graphics_flags, payload


def _build_rsc7(system_data: bytes, *, version: int = 0, sys_flags: int | None = None, gfx_flags: int = 0) -> bytes:
    if sys_flags is None:
        sys_flags = _resource_flags_from_size(len(system_data), version)
    header = struct.pack("<4I", RSC7_MAGIC, version, sys_flags, gfx_flags)
    return header + _compress_deflate(system_data)


__all__ = [
    "RPF_BLOCK_SIZE",
    "RPF_MAGIC",
    "RSC7_MAGIC",
    "_archive_name",
    "_build_rsc7",
    "_ceil_div",
    "_coerce_file_bytes",
    "_compress_deflate",
    "_decompress_deflate",
    "_is_rsc7",
    "_normalize_key",
    "_normalize_path",
    "_pad",
    "_resource_flags_from_size",
    "_resource_version_from_flags",
    "_size_from_resource_flags",
    "_split_rsc7",
]
