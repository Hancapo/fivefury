from __future__ import annotations

from pathlib import Path


def path_name(path: str) -> str:
    slash = path.rfind("/")
    return path[slash + 1 :] if slash >= 0 else path


def path_stem(path: str) -> str:
    name = path_name(path)
    dot = name.rfind(".")
    return name[:dot] if dot > 0 else name


def split_archive_asset_path(path: str | Path) -> tuple[str, str] | None:
    normalized = str(path).replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    for index, part in enumerate(parts):
        if part.lower().endswith(".rpf"):
            archive_rel = "/".join(parts[: index + 1])
            entry_path = "/".join(parts[index + 1 :])
            return archive_rel, entry_path
    return None


__all__ = ["path_name", "path_stem", "split_archive_asset_path"]
