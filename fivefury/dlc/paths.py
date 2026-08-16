from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path, PurePosixPath

DLC_PLATFORM_ROOT = PurePosixPath("%PLATFORM%")


def dlc_platform_path(path: str | PurePosixPath) -> PurePosixPath:
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"DLC platform path must be relative: {path!r}")
    if relative.parts[:1] == DLC_PLATFORM_ROOT.parts:
        return relative
    return DLC_PLATFORM_ROOT / relative


def iter_dlc_folder_files(
    folder: str | Path,
    *,
    include_dot_dirs: bool = False,
) -> Iterator[tuple[str, Path]]:
    root = Path(folder)
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().lower()
    ):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if not include_dot_dirs and any(
            part.startswith(".") for part in relative.parts
        ):
            continue
        yield relative.as_posix(), path


__all__ = ["DLC_PLATFORM_ROOT", "dlc_platform_path", "iter_dlc_folder_files"]
