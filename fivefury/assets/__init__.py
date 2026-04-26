from __future__ import annotations

from pathlib import Path
from typing import Iterator

from ..common import read_source_bytes
from ..gamefile import GameFileType
from .base import EmbeddedTextureDictionary, ResourceTextureAsset, _coerce_kind
from .ydd import YddAsset
from .ydr import YdrAsset
from .yft import YftAsset
from .ypt import YptAsset

RESOURCE_TEXTURE_ASSET_TYPES: dict[GameFileType, type[ResourceTextureAsset]] = {
    GameFileType.YDR: YdrAsset,
    GameFileType.YDD: YddAsset,
    GameFileType.YFT: YftAsset,
    GameFileType.YPT: YptAsset,
}


def open_resource_texture_asset(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    kind: GameFileType | str | None = None,
    path: str | Path = "",
) -> ResourceTextureAsset | None:
    data = read_source_bytes(source)
    kind_value = _coerce_kind(kind, source)
    asset_type = RESOURCE_TEXTURE_ASSET_TYPES.get(kind_value) if kind_value is not None else None
    if asset_type is None:
        return None
    asset_path = str(path or source) if isinstance(source, (str, Path)) or path else ""
    try:
        return asset_type.from_bytes(data, path=asset_path)
    except Exception:
        return None


def iter_embedded_texture_dictionaries(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    kind: GameFileType | str | None = None,
) -> Iterator[EmbeddedTextureDictionary]:
    asset = open_resource_texture_asset(source, kind=kind)
    if asset is None:
        return
    yield from asset.iter_embedded_texture_dictionaries()


def list_embedded_texture_dictionaries(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    kind: GameFileType | str | None = None,
) -> list[EmbeddedTextureDictionary]:
    asset = open_resource_texture_asset(source, kind=kind)
    return asset.list_embedded_texture_dictionaries() if asset is not None else []


__all__ = [
    "EmbeddedTextureDictionary",
    "ResourceTextureAsset",
    "RESOURCE_TEXTURE_ASSET_TYPES",
    "YddAsset",
    "YdrAsset",
    "YftAsset",
    "YptAsset",
    "iter_embedded_texture_dictionaries",
    "list_embedded_texture_dictionaries",
    "open_resource_texture_asset",
]
