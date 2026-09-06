from __future__ import annotations

import dataclasses
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from enum import IntEnum
from pathlib import Path
from typing import Any, TypeAlias

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


def atomic_write_files(
    files: Mapping[Path, bytes],
    *,
    prepare: Callable[[Path, int, int], None] | None = None,
) -> list[Path]:
    """Stage a batch before replacement; roll back replacements on failure.

    Preparation can cancel. The commit phase is non-cancellable and rolls back
    ordinary exceptions; it is not a filesystem-wide power-loss transaction.
    """
    with ExitStack() as cleanup:
        staged: list[tuple[Path, Path, Path]] = []
        for index, (target, data) in enumerate(files.items()):
            if prepare is not None:
                prepare(target, index, len(files))
            target.parent.mkdir(parents=True, exist_ok=True)
            folder = Path(
                tempfile.mkdtemp(
                    prefix=f".{target.name}.",
                    dir=target.parent,
                )
            )
            cleanup.callback(shutil.rmtree, folder)
            staged.append(
                (target, atomic_write_bytes(folder / "new", data), folder / "old")
            )
        if prepare is not None and staged:
            prepare(staged[-1][0], len(files), len(files))
        committed: list[tuple[Path, Path | None]] = []
        try:
            for target, temporary, backup in staged:
                original = backup if target.exists() else None
                if original is not None:
                    os.replace(target, original)
                committed.append((target, original))
                os.replace(temporary, target)
        except BaseException:
            try:
                for target, original in reversed(committed):
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        os.replace(original, target)
            except BaseException:
                # Keep recovery files if the filesystem also rejects rollback.
                cleanup.pop_all()
                raise
            raise
    return list(files)


def hash_value(value: int | MetaHash | str) -> int:
    return int(value) if not isinstance(value, str) else jenk_hash(value)


def dataclass_init_values(value: Any, model_type: type[Any]) -> dict[str, Any]:
    return {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(model_type)
        if field.init
    }


def clip_short_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    return normalized.lower()


class JsonReport:
    __slots__ = ()

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def save_json(self, path: str | Path) -> Path:
        return atomic_write_bytes(path, (self.to_json() + "\n").encode())


class FlexibleIntEnum(IntEnum):
    @classmethod
    def _missing_(cls, value: object) -> FlexibleIntEnum:
        if not isinstance(value, int):
            raise TypeError(f"{value!r} is not a valid {cls.__name__}")
        member = int.__new__(cls, value)
        member._name_ = f"UNKNOWN_{value}"
        member._value_ = value
        return member


__all__ = [
    "ByteSource",
    "FlexibleIntEnum",
    "JsonReport",
    "atomic_write_bytes",
    "atomic_write_files",
    "clip_short_name",
    "dataclass_init_values",
    "hash_value",
    "read_source_bytes",
]
