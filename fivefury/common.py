from __future__ import annotations

import os
import tempfile
from enum import IntEnum
from pathlib import Path
from typing import TypeAlias

from .hashing import jenk_hash
from .metahash import MetaHash

ByteSource: TypeAlias = bytes | bytearray | memoryview | str | Path


def read_source_bytes(source: ByteSource) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    return bytes(source)


def atomic_write_bytes(destination: str | Path, data: bytes) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return target


def hash_value(value: int | MetaHash | str) -> int:
    return int(value) if not isinstance(value, str) else jenk_hash(value)


def clip_short_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    return normalized.lower()


class FlexibleIntEnum(IntEnum):
    @classmethod
    def _missing_(cls, value: object) -> "FlexibleIntEnum":
        if not isinstance(value, int):
            raise ValueError(f"{value!r} is not a valid {cls.__name__}")
        member = int.__new__(cls, value)
        member._name_ = f"UNKNOWN_{value}"
        member._value_ = value
        return member


__all__ = [
    "ByteSource",
    "FlexibleIntEnum",
    "atomic_write_bytes",
    "clip_short_name",
    "hash_value",
    "read_source_bytes",
]
