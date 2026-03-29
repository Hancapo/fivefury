from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from .utils import _normalize_path

if TYPE_CHECKING:  # pragma: no cover
    from . import RpfArchive, RpfExportMode


def _ensure_container_path(current: "RpfArchive", parts: list[str]) -> tuple["RpfArchive", str]:
    archive = current
    relative_path = ""
    for segment in parts:
        if segment.lower().endswith(".rpf"):
            full = f"{relative_path}/{segment}" if relative_path else segment
            _, archive = archive.add_nested_archive(full)
            relative_path = ""
            continue
        relative_path = f"{relative_path}/{segment}" if relative_path else segment
        archive.add_directory(relative_path)
    return archive, relative_path


def _insert_file_path(current: "RpfArchive", parts: list[str], data: bytes) -> None:
    if not parts:
        return
    archive, relative_path = _ensure_container_path(current, parts[:-1])
    leaf = parts[-1]
    full = f"{relative_path}/{leaf}" if relative_path else leaf
    archive.add_file(full, data)


def _ensure_directory_path(current: "RpfArchive", parts: list[str]) -> None:
    _ensure_container_path(current, parts)


def _zip_to_rpf(zf: zipfile.ZipFile, *, name: str) -> "RpfArchive":
    from . import RpfArchive

    archive = RpfArchive.empty(name)
    for info in sorted(zf.infolist(), key=lambda i: i.filename.lower()):
        path = _normalize_path(info.filename)
        if not path:
            continue
        parts = path.split("/")
        if info.is_dir():
            _ensure_directory_path(archive, parts)
            continue
        _insert_file_path(archive, parts, zf.read(info.filename))
    return archive


def _directory_to_rpf(source_dir: str | Path, *, name: str) -> "RpfArchive":
    from . import RpfArchive

    root = Path(source_dir)
    archive = RpfArchive.empty(name or root.name)
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().lower()):
        rel = path.relative_to(root).as_posix()
        parts = rel.split("/")
        if path.is_dir():
            _ensure_directory_path(archive, parts)
            continue
        _insert_file_path(archive, parts, path.read_bytes())
    return archive


def _coerce_archive(source: str | Path | bytes | BinaryIO | "RpfArchive") -> "RpfArchive":
    from . import RpfArchive

    if isinstance(source, RpfArchive):
        return source
    if isinstance(source, (str, Path)):
        return RpfArchive.from_path(source)
    if isinstance(source, (bytes, bytearray)):
        return RpfArchive.from_bytes(bytes(source))
    return RpfArchive.from_bytes(source.read())


def load_rpf(source: str | Path | bytes | BinaryIO) -> "RpfArchive":
    return _coerce_archive(source)


def create_rpf(name: str = "archive.rpf") -> "RpfArchive":
    from . import RpfArchive

    return RpfArchive.empty(name)


def rpf_to_zip(
    rpf_source: str | Path | bytes | BinaryIO | "RpfArchive",
    output: str | Path | None = None,
    *,
    mode: "RpfExportMode | None" = None,
    recurse_nested: bool = True,
) -> bytes:
    from . import RpfExportMode

    archive = _coerce_archive(rpf_source)
    return archive.to_zip(output, mode=mode or RpfExportMode.STANDALONE, recurse_nested=recurse_nested)


def rpf_to_folder(
    rpf_source: str | Path | bytes | BinaryIO | "RpfArchive",
    output_dir: str | Path,
    *,
    mode: "RpfExportMode | None" = None,
    recurse_nested: bool = True,
) -> list[Path]:
    from . import RpfExportMode

    archive = _coerce_archive(rpf_source)
    return archive.to_folder(output_dir, mode=mode or RpfExportMode.STANDALONE, recurse_nested=recurse_nested)


def zip_to_rpf(
    zip_source: str | Path | bytes | BinaryIO,
    output: str | Path | None = None,
    *,
    name: str = "archive",
) -> "RpfArchive" | bytes:
    if isinstance(zip_source, (str, Path)):
        path = Path(zip_source)
        if path.is_dir():
            archive = _directory_to_rpf(path, name=name or path.name)
        else:
            with zipfile.ZipFile(path, "r") as zf:
                archive = _zip_to_rpf(zf, name=name)
    elif isinstance(zip_source, (bytes, bytearray)):
        with zipfile.ZipFile(io.BytesIO(zip_source), "r") as zf:
            archive = _zip_to_rpf(zf, name=name)
    else:
        with zipfile.ZipFile(io.BytesIO(zip_source.read()), "r") as zf:
            archive = _zip_to_rpf(zf, name=name)
    if output is not None:
        archive.save(output)
        return Path(output).read_bytes()
    return archive


__all__ = [
    "create_rpf",
    "load_rpf",
    "rpf_to_folder",
    "rpf_to_zip",
    "zip_to_rpf",
    "_coerce_archive",
    "_directory_to_rpf",
    "_ensure_container_path",
    "_ensure_directory_path",
    "_insert_file_path",
    "_zip_to_rpf",
]


