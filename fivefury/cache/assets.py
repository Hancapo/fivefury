from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from ..common import hash_value
from ..gamefile import GameFileType
from ..metahash import MetaHash
from ..assets import RESOURCE_TEXTURE_ASSET_TYPES, ResourceTextureAsset, open_resource_texture_asset
from ..rpf import RpfFileEntry
from ..ytyp.archetypes import ArchetypeAssetType, coerce_archetype_asset_type
from ..ytd import Texture, Ytd, read_ytd

_EMBEDDED_TEXTURE_RESOURCE_TYPES = frozenset(RESOURCE_TEXTURE_ASSET_TYPES)


def _asset_kind_from_archetype_type(asset_type: int | ArchetypeAssetType) -> GameFileType | None:
    asset_kind = coerce_archetype_asset_type(asset_type)
    if asset_kind is ArchetypeAssetType.FRAGMENT:
        return GameFileType.YFT
    if asset_kind is ArchetypeAssetType.DRAWABLE:
        return GameFileType.YDR
    if asset_kind is ArchetypeAssetType.DRAWABLE_DICTIONARY:
        return GameFileType.YDD
    return None


@dataclass(slots=True)
class TextureRef:
    texture: Texture
    container_path: str = ""
    container_name: str = ""
    origin: str = "ytd"
    parent_depth: int = 0


class GameFileCacheAssetMixin:
    def iter_archetypes(self) -> Iterator[Any]:
        yield from self.archetype_dict.values()

    def archetype_items(self) -> Iterator[tuple[int, Any]]:
        yield from self.archetype_dict.items()

    def get_archetype(self, value: int | MetaHash | str) -> Any | None:
        return self.archetype_dict.get(value)

    def find_archetype(self, value: int | MetaHash | str) -> Any | None:
        return self.get_archetype(value)

    def has_archetype(self, value: int | MetaHash | str) -> bool:
        return self.get_archetype(value) is not None

    def _coerce_ymap(self, value: Any) -> Any | None:
        if hasattr(value, "entities"):
            return value
        if isinstance(value, (bytes, bytearray, memoryview)):
            try:
                from ..ymap import read_ymap

                parsed = read_ymap(bytes(value))
            except Exception:
                parsed = None
            if parsed is not None and hasattr(parsed, "entities"):
                return parsed
        game_file = self.get_file(value)
        parsed = game_file.parsed if game_file is not None else None
        if parsed is None or not hasattr(parsed, "entities"):
            candidate = Path(str(value))
            if candidate.is_file():
                try:
                    from ..ymap import read_ymap

                    parsed = read_ymap(candidate.read_bytes())
                except Exception:
                    parsed = None
            if parsed is None or not hasattr(parsed, "entities"):
                return None
        return parsed

    def _find_archetypes_for_asset(self, value: Any) -> Iterator[Any]:
        yield from self._iter_archetypes_for_query(value)

    def iter_asset_texture_dictionaries(self, query: Any) -> Iterator["AssetRecord"]:
        yield from self.iter_texture_dictionaries(query, include_parents=False)

    def list_asset_texture_dictionaries(self, query: Any) -> list["AssetRecord"]:
        return self.list_texture_dictionaries(query, include_parents=False)

    def _iter_ymap_entity_archetypes(self, ymap_value: Any) -> Iterator[Any]:
        ymap = self._coerce_ymap(ymap_value)
        if ymap is None:
            return
        seen: set[int] = set()
        for entity in getattr(ymap, "entities", []) or []:
            archetype_name = getattr(entity, "archetype_name", None)
            if archetype_name in (None, "", 0):
                continue
            archetype = self.get_archetype(archetype_name)
            if archetype is None:
                continue
            name_hash = int(getattr(archetype, "name", 0) or 0)
            if name_hash == 0 or name_hash in seen:
                continue
            seen.add(name_hash)
            yield archetype

    def _primary_asset_for_archetype(self, archetype: Any) -> "AssetRecord" | None:
        asset_name = getattr(archetype, "asset_name", None) or getattr(archetype, "name", None)
        if asset_name in (None, "", 0):
            return None
        kind = _asset_kind_from_archetype_type(getattr(archetype, "asset_type", ArchetypeAssetType.UNINITIALIZED) or ArchetypeAssetType.UNINITIALIZED)
        if kind is not None:
            asset = self.get_asset(asset_name, kind=kind)
            if asset is not None:
                return asset
        for fallback_kind in (GameFileType.YDR, GameFileType.YDD, GameFileType.YFT):
            asset = self.get_asset(asset_name, kind=fallback_kind)
            if asset is not None:
                return asset
        return None

    def _supporting_assets_for_archetype(self, archetype: Any) -> Iterator["AssetRecord"]:
        for field_name, kind in (
            ("texture_dictionary", GameFileType.YTD),
            ("physics_dictionary", GameFileType.YBN),
            ("clip_dictionary", GameFileType.YCD),
        ):
            value = getattr(archetype, field_name, None)
            if value in (None, "", 0):
                continue
            asset = self.get_asset(value, kind=kind)
            if asset is not None:
                yield asset

    def iter_ymap_entity_assets(self, query: Any, *, include_supporting: bool = True) -> Iterator["AssetRecord"]:
        seen_paths: set[str] = set()
        for archetype in self._iter_ymap_entity_archetypes(query):
            primary = self._primary_asset_for_archetype(archetype)
            if primary is not None and primary.path not in seen_paths:
                seen_paths.add(primary.path)
                yield primary
            if not include_supporting:
                continue
            for asset in self._supporting_assets_for_archetype(archetype):
                if asset.path in seen_paths:
                    continue
                seen_paths.add(asset.path)
                yield asset

    def list_ymap_entity_assets(self, query: Any, *, include_supporting: bool = True) -> list["AssetRecord"]:
        return list(self.iter_ymap_entity_assets(query, include_supporting=include_supporting))

    def extract_ymap_assets(
        self,
        query: Any,
        destination: str | Path,
        *,
        include_supporting: bool = True,
        logical: bool = False,
    ) -> list[Path]:
        output_dir = Path(destination)
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted: list[Path] = []
        for asset in self.iter_ymap_entity_assets(query, include_supporting=include_supporting):
            result = self.extract_asset(asset, output_dir / asset.name, logical=logical)
            if result is not None:
                extracted.append(result)
        return extracted

    def _coerce_ytd(self, value: Any) -> Ytd | None:
        if isinstance(value, Ytd):
            return value
        if hasattr(value, "textures") and hasattr(value, "to_bytes"):
            return value if isinstance(value, Ytd) else None
        if isinstance(value, (bytes, bytearray, memoryview)):
            try:
                return read_ytd(value)
            except Exception:
                return None
        asset = self._coerce_asset(value, kind=GameFileType.YTD)
        if asset is not None:
            game_file = self.get_file(asset)
            if game_file is not None and isinstance(game_file.parsed, Ytd):
                return game_file.parsed
            standalone = self.read_bytes(asset, logical=False)
            if standalone is not None:
                try:
                    return read_ytd(standalone)
                except Exception:
                    pass
        candidate = Path(str(value))
        if candidate.is_file():
            try:
                return read_ytd(candidate.read_bytes())
            except Exception:
                return None
        return None

    def _iter_archetypes_for_query(self, query: Any) -> Iterator[Any]:
        if hasattr(query, "texture_dictionary"):
            yield query
            return

        ymap = self._coerce_ymap(query)
        if ymap is not None:
            yield from self._iter_ymap_entity_archetypes(ymap)
            return

        asset = self._coerce_asset(query)
        if asset is not None and asset.kind is GameFileType.YTYP:
            game_file = self.get_file(asset)
            parsed = game_file.parsed if game_file is not None else None
            archetypes = getattr(parsed, "archetypes", None)
            if isinstance(archetypes, list):
                yield from archetypes
                return

        direct = None
        try:
            direct = self.get_archetype(query)
        except Exception:
            direct = None
        if direct is not None:
            yield direct
            return

        if asset is None:
            return
        if asset.kind not in {GameFileType.YDR, GameFileType.YDD, GameFileType.YFT}:
            return

        target_hashes = {asset.short_hash, asset.name_hash}
        for archetype in self.archetype_dict.values():
            try:
                asset_name_hash = int(getattr(archetype, "asset_name", 0) or 0)
            except Exception:
                asset_name_hash = 0
            try:
                name_hash = int(getattr(archetype, "name", 0) or 0)
            except Exception:
                name_hash = 0
            if asset_name_hash in target_hashes or name_hash in target_hashes:
                yield archetype

    def _iter_texture_dict_chain_assets(self, value: int | str | MetaHash) -> Iterator[tuple["AssetRecord", int]]:
        seen_hashes: set[int] = set()
        current_hash = hash_value(value)
        depth = 0
        while current_hash and current_hash not in seen_hashes:
            seen_hashes.add(current_hash)
            asset = self.get_asset(current_hash, kind=GameFileType.YTD)
            if asset is not None:
                yield asset, depth
            next_hash = self.texture_parent_dict.get(current_hash)
            if not next_hash:
                break
            current_hash = int(next_hash)
            depth += 1

    def iter_texture_dictionaries(self, query: Any, *, include_parents: bool = True) -> Iterator["AssetRecord"]:
        seen_paths: set[str] = set()

        direct_ytd = self._coerce_asset(query, kind=GameFileType.YTD)
        if direct_ytd is not None:
            for asset, _ in self._iter_texture_dict_chain_assets(direct_ytd.short_hash if include_parents else direct_ytd.short_hash):
                if not include_parents and asset.path != direct_ytd.path:
                    continue
                if asset.path not in seen_paths:
                    seen_paths.add(asset.path)
                    yield asset
            return

        ymap = self._coerce_ymap(query)
        if ymap is not None:
            for asset in self.iter_ymap_entity_assets(ymap, include_supporting=True):
                if asset.kind is not GameFileType.YTD:
                    continue
                chain = self._iter_texture_dict_chain_assets(asset.short_hash) if include_parents else [(asset, 0)]
                for ytd_asset, _ in chain:
                    if ytd_asset.path in seen_paths:
                        continue
                    seen_paths.add(ytd_asset.path)
                    yield ytd_asset
            return

        for archetype in self._iter_archetypes_for_query(query):
            texture_dictionary = getattr(archetype, "texture_dictionary", None)
            if texture_dictionary in (None, "", 0):
                continue
            chain = self._iter_texture_dict_chain_assets(texture_dictionary) if include_parents else []
            if include_parents:
                for asset, _ in chain:
                    if asset.path in seen_paths:
                        continue
                    seen_paths.add(asset.path)
                    yield asset
                continue
            asset = self.get_asset(texture_dictionary, kind=GameFileType.YTD)
            if asset is not None and asset.path not in seen_paths:
                seen_paths.add(asset.path)
                yield asset

    def list_texture_dictionaries(self, query: Any, *, include_parents: bool = True) -> list["AssetRecord"]:
        return list(self.iter_texture_dictionaries(query, include_parents=include_parents))

    def iter_ytd_textures(self, query: Any) -> Iterator[Texture]:
        ytd = self._coerce_ytd(query)
        if ytd is None:
            return
        yield from ytd.textures

    def list_ytd_textures(self, query: Any) -> list[Texture]:
        return list(self.iter_ytd_textures(query))

    def extract_ytd_textures(self, query: Any, destination: str | Path) -> list[Path]:
        ytd = self._coerce_ytd(query)
        if ytd is None:
            return []
        output_dir = Path(destination)
        output_dir.mkdir(parents=True, exist_ok=True)
        return ytd.extract(output_dir)

    def _read_standalone_resource_bytes(self, asset: "AssetRecord") -> bytes | None:
        entry = self._get_entry_for_asset(asset)
        if isinstance(entry, RpfFileEntry):
            if entry._archive is None:
                return None
            return entry._archive.read_entry_standalone(entry)
        if asset.loose_path is not None and asset.loose_path.is_file():
            return asset.loose_path.read_bytes()
        return None

    def get_resource_asset(self, query: Any) -> ResourceTextureAsset | None:
        if isinstance(query, ResourceTextureAsset):
            return query
        candidate = Path(str(query)) if isinstance(query, (str, Path)) else None
        if candidate is not None and candidate.is_file():
            return open_resource_texture_asset(candidate)
        asset = self._coerce_asset(query)
        if asset is None or asset.kind not in _EMBEDDED_TEXTURE_RESOURCE_TYPES:
            return None
        standalone = self._read_standalone_resource_bytes(asset)
        if standalone is None:
            return None
        return open_resource_texture_asset(standalone, kind=asset.kind, path=asset.path)

    def _iter_primary_texture_assets(self, query: Any) -> Iterator["AssetRecord"]:
        seen_paths: set[str] = set()
        direct_asset = self._coerce_asset(query)
        if direct_asset is not None and direct_asset.kind in _EMBEDDED_TEXTURE_RESOURCE_TYPES:
            seen_paths.add(direct_asset.path)
            yield direct_asset
        for archetype in self._iter_archetypes_for_query(query):
            asset = self._primary_asset_for_archetype(archetype)
            if asset is None or asset.kind not in _EMBEDDED_TEXTURE_RESOURCE_TYPES or asset.path in seen_paths:
                continue
            seen_paths.add(asset.path)
            yield asset

    def _embedded_container_name(self, stem: str, label: str) -> str:
        normalized_label = str(label or "embedded").strip().lower()
        if normalized_label in {"embedded", "drawable"}:
            return stem
        return f"{stem}_{normalized_label}"

    def _iter_embedded_texture_refs(self, query: Any) -> Iterator[TextureRef]:
        direct_resource = self.get_resource_asset(query)
        if direct_resource is not None:
            for dictionary in direct_resource.iter_embedded_texture_dictionaries():
                container_name = self._embedded_container_name(direct_resource.stem, dictionary.label)
                for texture in dictionary.ytd.textures:
                    yield TextureRef(
                        texture=texture,
                        container_path=direct_resource.path,
                        container_name=container_name,
                        origin="embedded",
                        parent_depth=0,
                    )
            return

        for asset in self._iter_primary_texture_assets(query):
            resource_asset = self.get_resource_asset(asset)
            if resource_asset is None:
                continue
            for dictionary in resource_asset.iter_embedded_texture_dictionaries():
                container_name = self._embedded_container_name(resource_asset.stem, dictionary.label)
                for texture in dictionary.ytd.textures:
                    yield TextureRef(
                        texture=texture,
                        container_path=resource_asset.path,
                        container_name=container_name,
                        origin="embedded",
                        parent_depth=0,
                    )

    def iter_asset_textures(self, query: Any, *, include_parents: bool = True) -> Iterator[TextureRef]:
        seen: set[tuple[str, str]] = set()

        direct_ytd = self._coerce_ytd(query)
        if direct_ytd is not None and self._coerce_asset(query, kind=GameFileType.YTD) is None:
            if isinstance(query, (str, Path)):
                container_name = Path(str(query)).stem
            else:
                container_name = "textures"
            for texture in direct_ytd.textures:
                key = (container_name.lower(), texture.name.lower())
                if key in seen:
                    continue
                seen.add(key)
                yield TextureRef(
                    texture=texture,
                    container_name=container_name,
                    container_path="",
                    origin="ytd",
                    parent_depth=0,
                )
            return

        for item in self._iter_embedded_texture_refs(query):
            key = ((item.container_path or item.container_name).lower(), item.texture.name.lower())
            if key in seen:
                continue
            seen.add(key)
            yield item

        for ytd_asset in self.iter_texture_dictionaries(query, include_parents=include_parents):
            ytd = self._coerce_ytd(ytd_asset)
            if ytd is None:
                continue
            for texture in ytd.textures:
                key = (ytd_asset.path.lower(), texture.name.lower())
                if key in seen:
                    continue
                seen.add(key)
                yield TextureRef(
                    texture=texture,
                    container_path=ytd_asset.path,
                    container_name=ytd_asset.stem,
                    origin="ytd",
                    parent_depth=0,
                )

    def list_asset_textures(self, query: Any, *, include_parents: bool = True) -> list[TextureRef]:
        return list(self.iter_asset_textures(query, include_parents=include_parents))

    def extract_asset_textures(self, query: Any, destination: str | Path, *, include_parents: bool = True) -> list[Path]:
        output_dir = Path(destination)
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted: list[Path] = []
        for item in self.iter_asset_textures(query, include_parents=include_parents):
            container_dir = output_dir / (item.container_name or "textures")
            result = item.texture.save_dds(container_dir / f"{item.texture.name}.dds")
            extracted.append(result)
        return extracted


__all__ = ["GameFileCacheAssetMixin", "TextureRef"]


