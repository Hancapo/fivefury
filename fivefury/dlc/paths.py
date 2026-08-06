from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


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


__all__ = ["iter_dlc_folder_files"]
