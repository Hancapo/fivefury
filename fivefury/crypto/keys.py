from __future__ import annotations

import hashlib
import importlib.resources
import json
import mmap
import os
import struct
from pathlib import Path
from typing import Final

from .backends import DotNetRandom, _AesEcbCipher, _decompress_any, _to_signed_i32
from ..hashing import jenk_hash

_AES_KEY_SHA1: Final[bytes] = bytes(
    [0xA0, 0x79, 0x61, 0x28, 0xA7, 0x75, 0x72, 0x0A, 0xC2, 0x04, 0xD9, 0x81, 0x9F, 0x68, 0xC1, 0x72, 0xE3, 0x95, 0x2C, 0x6D]
)
_DEFAULT_AES_KEY_B64: Final[str] = "s4lzr4ueJjqN8XAyFEKzk4vT8h+k0E3/iC4EZg/5nf0="
_NG_KEYS_SIZE: Final[int] = 27472
_NG_TABLES_SIZE: Final[int] = 278528
_NG_BLOB_SIZE: Final[int] = _NG_KEYS_SIZE + _NG_TABLES_SIZE


def _search_sha1_window(exe_path: Path, digest: bytes, *, length: int, align: int = 8) -> bytes:
    with exe_path.open("rb") as fh:
        with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            limit = max(0, len(mm) - length + 1)
            for offset in range(0, limit, align):
                block = mm[offset : offset + length]
                if hashlib.sha1(block).digest() == digest:
                    return bytes(block)
    raise ValueError(f"Unable to locate AES key in {exe_path}")


def _default_magic_path() -> Path:
    package_magic = importlib.resources.files("fivefury").joinpath("data", "magic.dat")
    if package_magic.is_file():
        return Path(str(package_magic))
    fallback = Path(__file__).resolve().parents[1] / "references" / "CodeWalker.Core" / "Resources" / "magic.dat"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError("magic.dat was not found")


def _read_packaged_data(name: str) -> tuple[bytes, str] | None:
    resource = importlib.resources.files("fivefury").joinpath("data", name)
    if resource.is_file():
        return resource.read_bytes(), str(resource)
    fallback = Path(__file__).resolve().parent / "data" / name
    if fallback.is_file():
        return fallback.read_bytes(), str(fallback)
    return None


def _default_cache_path() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else (Path.home() / ".cache")
    return base / "fivefury" / "keys.json"


def _load_cache(path: Path) -> dict[str, dict[str, object]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(path: Path, payload: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _resolve_exe_path(root_or_exe: str | Path | None, *, gen9: bool = False) -> Path:
    if root_or_exe is None:
        raise ValueError("game root or exe path is required")
    path = Path(root_or_exe)
    if path.is_file():
        return path
    candidates = ["gta5_enhanced.exe", "gta5.exe"] if gen9 else ["gta5.exe", "gta5_enhanced.exe"]
    for name in candidates:
        candidate = path / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not locate a GTA V executable in {path}")


def _decode_magic_payload(aes_key: bytes, magic_bytes: bytes) -> bytes:
    random_bytes = []
    rng = DotNetRandom(_to_signed_i32(jenk_hash(aes_key)))
    for _ in range(4):
        block = bytearray(len(magic_bytes))
        rng.next_bytes(block)
        random_bytes.append(block)
    decoded = bytearray(len(magic_bytes))
    rb1, rb2, rb3, rb4 = random_bytes
    for i, value in enumerate(magic_bytes):
        decoded[i] = (value - rb1[i] - rb2[i] - rb3[i] - rb4[i]) & 0xFF
    decrypted = _AesEcbCipher(aes_key).decrypt(bytes(decoded))
    return _decompress_any(decrypted)


def _decode_ng_blob(payload: bytes) -> tuple[tuple[bytes, ...], tuple[tuple[tuple[int, ...], ...], ...]]:
    if len(payload) < _NG_BLOB_SIZE:
        raise ValueError(f"NG payload is truncated: expected at least {_NG_BLOB_SIZE} bytes, got {len(payload)}")
    keys_data = payload[:_NG_KEYS_SIZE]
    tables_data = payload[_NG_KEYS_SIZE : _NG_KEYS_SIZE + _NG_TABLES_SIZE]
    ng_keys = tuple(keys_data[i : i + 272] for i in range(0, len(keys_data), 272))
    tables: list[tuple[tuple[int, ...], ...]] = []
    offset = 0
    for _ in range(17):
        round_tables: list[tuple[int, ...]] = []
        for _ in range(16):
            round_tables.append(struct.unpack_from("<256I", tables_data, offset))
            offset += 1024
        tables.append(tuple(round_tables))
    return ng_keys, tuple(tables)


__all__ = [
    "_AES_KEY_SHA1",
    "_DEFAULT_AES_KEY_B64",
    "_NG_BLOB_SIZE",
    "_decode_magic_payload",
    "_decode_ng_blob",
    "_default_cache_path",
    "_default_magic_path",
    "_load_cache",
    "_read_packaged_data",
    "_resolve_exe_path",
    "_save_cache",
    "_search_sha1_window",
]


