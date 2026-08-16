from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path, PurePosixPath

DLC_PLATFORM_REGISTRATION_ROOT = PurePosixPath("%PLATFORM%")
DLC_PLATFORM_PAYLOAD_ROOT = PurePosixPath("x64")


def _platform_path(
    path: str | PurePosixPath,
    *,
    root: PurePosixPath,
    other_root: PurePosixPath,
) -> PurePosixPath:
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"DLC platform path must be relative: {path!r}")
    first_part = relative.parts[0].casefold() if relative.parts else ""
    if first_part == other_root.parts[0].casefold():
        raise ValueError(
            f"DLC platform path uses {other_root.as_posix()!r} where "
            f"{root.as_posix()!r} is required: {path!r}"
        )
    if first_part == root.parts[0].casefold():
        return relative
    return root / relative


def dlc_platform_registration_path(path: str | PurePosixPath) -> PurePosixPath:
    return _platform_path(
        path,
        root=DLC_PLATFORM_REGISTRATION_ROOT,
        other_root=DLC_PLATFORM_PAYLOAD_ROOT,
    )


def dlc_platform_payload_path(path: str | PurePosixPath) -> PurePosixPath:
    return _platform_path(
        path,
        root=DLC_PLATFORM_PAYLOAD_ROOT,
        other_root=DLC_PLATFORM_REGISTRATION_ROOT,
    )


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


__all__ = [
    "DLC_PLATFORM_PAYLOAD_ROOT",
    "DLC_PLATFORM_REGISTRATION_ROOT",
    "dlc_platform_payload_path",
    "dlc_platform_registration_path",
    "iter_dlc_folder_files",
]
