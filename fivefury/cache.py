from __future__ import annotations

import gc
import hashlib
import importlib
import os
import pickle
import re
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from collections.abc import Iterator as AbcIterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from .crypto import GameCrypto, load_game_keys
from .gamefile import GameFile, GameFileType, guess_game_file_type
from .hashing import _get_lut, jenk_hash
from .metahash import MetaHash
from .resolver import HashResolver, get_hash_resolver
from .rpf import RpfArchive, RpfEntry, RpfFileEntry, _normalize_key
from .resource_assets import RESOURCE_TEXTURE_ASSET_TYPES, ResourceTextureAsset, open_resource_texture_asset
from .ytd import Texture, Ytd, read_ytd

try:
    from ._native import CompactIndex, NativeCryptoContext, scan_rpf_batch_into_index, scan_rpf_into_index
except ImportError as exc:
    raise ImportError("fivefury native backend is required; rebuild/install the wheel with the bundled extension") from exc

_SCAN_INDEX_VERSION = 4
_SCAN_GC_INTERVAL = 8

_FLAG_LOOSE = 1
_FLAG_RESOURCE = 2
_FLAG_ENCRYPTED = 4

_SKIP_AUDIO = 1 << 0
_SKIP_VEHICLES = 1 << 1
_SKIP_PEDS = 1 << 2
_EMBEDDED_TEXTURE_RESOURCE_TYPES = frozenset(RESOURCE_TEXTURE_ASSET_TYPES)


def _try_load_decoder(module_name: str, attribute: str) -> Any | None:
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None
    return getattr(module, attribute, None)


def _decode_payload(path: str, data: bytes, *, raw: bytes | None = None) -> tuple[Any, GameFileType]:
    ext = Path(path).suffix.lower()
    if ext == ".ymap":
        decoder = _try_load_decoder("fivefury.ymap", "read_ymap")
        if decoder is not None:
            try:
                return decoder(data), GameFileType.YMAP
            except Exception:
                pass
        return data, GameFileType.YMAP
    if ext == ".ytyp":
        decoder = _try_load_decoder("fivefury.ytyp", "read_ytyp")
        if decoder is not None:
            try:
                return decoder(data), GameFileType.YTYP
            except Exception:
                pass
        return data, GameFileType.YTYP
    if ext == ".ytd":
        source = raw if raw is not None else data
        try:
            return read_ytd(source), GameFileType.YTD
        except Exception:
            return source, GameFileType.YTD
    if ext == ".rpf":
        try:
            return RpfArchive.from_bytes(data), GameFileType.RPF
        except Exception:
            return data, GameFileType.RPF
    return data, guess_game_file_type(path, GameFileType.UNKNOWN)


def _coerce_kind(value: GameFileType | str | int | None) -> GameFileType | None:
    if value is None:
        return None
    if isinstance(value, GameFileType):
        return value
    if isinstance(value, int):
        return GameFileType(int(value))
    text = str(value).strip().lower()
    if not text:
        return None
    if text.startswith("."):
        return guess_game_file_type(f"x{text}", GameFileType.UNKNOWN)
    if text in GameFileType.__members__:
        return GameFileType[text.upper()]
    try:
        return GameFileType[text.upper()]
    except KeyError:
        guessed = guess_game_file_type(f"x.{text}", GameFileType.UNKNOWN)
        return guessed if guessed is not GameFileType.UNKNOWN else None


def _path_name(path: str) -> str:
    slash = path.rfind("/")
    return path[slash + 1 :] if slash >= 0 else path


def _path_stem(path: str) -> str:
    name = _path_name(path)
    dot = name.rfind(".")
    return name[:dot] if dot > 0 else name


def _coerce_hash_value(value: int | MetaHash | str) -> int:
    return int(value) if not isinstance(value, str) else jenk_hash(value)


def _asset_kind_from_archetype_type(asset_type: int) -> GameFileType | None:
    if int(asset_type) == 1:
        return GameFileType.YFT
    if int(asset_type) == 2:
        return GameFileType.YDR
    if int(asset_type) == 3:
        return GameFileType.YDD
    return None


def _asset_category_mask(path: str | Path) -> int:
    normalized = _normalize_key(path)
    name = _path_name(normalized)
    ext = Path(name).suffix.lower()
    mask = 0

    if (
        ext in {".awc", ".rel", ".nametable"}
        or "/audio/" in normalized
        or "/audioconfig/" in normalized
        or name.startswith("audioconfig")
        or name == "audio_rel.rpf"
    ):
        mask |= _SKIP_AUDIO

    if (
        name == "vehicles.rpf"
        or
        "/vehicles.rpf/" in normalized
        or "/vehicles/" in normalized
        or "/vehiclemods/" in normalized
        or "/streamedvehicles/" in normalized
        or name.startswith("streamedvehicles")
        or name.startswith("vehiclemods")
        or name == "vehicles.meta"
        or name.startswith("vehiclelayouts")
        or name.startswith("carvariations")
        or name.startswith("carcols")
        or name == "handling.meta"
        or name == "vfxvehicleinfo.ymt"
    ):
        mask |= _SKIP_VEHICLES

    if (
        name == "peds.rpf"
        or name == "pedprops.rpf"
        or
        "/peds.rpf/" in normalized
        or "/streamedpeds_" in normalized
        or "/componentpeds_" in normalized
        or "/pedprops/" in normalized
        or "/peds/" in normalized
        or name.startswith("streamedpeds_")
        or name.startswith("componentpeds_")
        or name in {"peds.meta", "peds.ymt"}
    ):
        mask |= _SKIP_PEDS

    return mask


def _maybe_hash_name(value: str) -> tuple[int, int]:
    lower_name = _path_name(value).lower()
    stem = _path_stem(lower_name)
    return jenk_hash(lower_name), jenk_hash(stem)


def _normalize_folder_prefix(value: str | Path) -> str:
    text = str(value).replace("\\", "/").strip().strip("/").lower()
    while "//" in text:
        text = text.replace("//", "/")
    return text


def _coerce_folder_prefixes(value: str | Path | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, Path)):
        parts = str(value).replace("\n", ";").split(";")
    else:
        parts = list(value)
    return tuple(prefix for prefix in (_normalize_folder_prefix(part) for part in parts) if prefix)


def _parse_dlc_names_from_text(data: bytes) -> list[str]:
    text = data.decode("utf-8", errors="ignore")
    names: list[str] = []
    for item in re.findall(r"<item>\s*([^<]+)\s*</item>", text, flags=re.IGNORECASE):
        normalized = _normalize_folder_prefix(item.replace("platform:", "x64"))
        if normalized.startswith("dlcpacks:"):
            suffix = normalized.split(":", 1)[1].strip("/")
            if suffix:
                names.append(suffix.split("/", 1)[0])
    return names


def _split_archive_asset_path(path: str | Path) -> tuple[str, str] | None:
    normalized = str(path).replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    for index, part in enumerate(parts):
        if part.lower().endswith(".rpf"):
            archive_rel = "/".join(parts[: index + 1])
            entry_path = "/".join(parts[index + 1 :])
            return archive_rel, entry_path
    return None


def _default_index_cache_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else (Path.home() / ".cache")
    return base / "fivefury" / "scan-index"


def _scan_archive_source(
    path: str | Path,
    source_prefix: str,
    index: CompactIndex,
    crypto: NativeCryptoContext | None,
    hash_lut: bytes,
    skip_mask: int = 0,
    verbose: bool = False,
) -> int:
    return int(scan_rpf_into_index(index, str(path), source_prefix, hash_lut, crypto, int(skip_mask), bool(verbose)))


def _scan_archive_sources_batch(
    sources: Sequence[tuple[str | Path, str]],
    index: CompactIndex,
    crypto: NativeCryptoContext | None,
    hash_lut: bytes,
    skip_mask: int = 0,
    workers: int = 0,
    verbose: bool = False,
) -> list[tuple[str, int, str | None]]:
    normalized = [(str(path), str(source_prefix)) for path, source_prefix in sources]
    return list(
        scan_rpf_batch_into_index(
            index,
            normalized,
            hash_lut,
            crypto,
            int(skip_mask),
            int(workers),
            bool(verbose),
        )
    )


class AssetRecord:
    __slots__ = ("_cache", "id")

    def __init__(self, cache: GameFileCache, asset_id: int) -> None:
        self._cache = cache
        self.id = int(asset_id)

    def __repr__(self) -> str:
        return (
            "AssetRecord("
            f"id={self.id}, path={self.path!r}, kind={self.kind.name}, size={self.size}, "
            f"stored_size={self.stored_size}, uncompressed_size={self.uncompressed_size})"
        )

    @classmethod
    def from_cache(cls, cache: GameFileCache, asset_id: int) -> AssetRecord:
        return cls(cache, asset_id)

    @property
    def path(self) -> str:
        return self._cache._index.get_path(self.id)

    @property
    def kind(self) -> GameFileType:
        return GameFileType(int(self._cache._index.get_kind(self.id)))

    @property
    def size(self) -> int:
        return int(self._cache._index.get_size(self.id))

    @property
    def stored_size(self) -> int:
        return self.size

    @property
    def uncompressed_size(self) -> int:
        return int(self._cache._index.get_uncompressed_size(self.id))

    @property
    def entry(self) -> Optional[RpfFileEntry]:
        return self._cache._live_entries.get(self.id)

    @property
    def archive(self) -> Optional[RpfArchive]:
        return self._cache._live_archives.get(self.id)

    @property
    def loose_path(self) -> Optional[Path]:
        return self._cache._loose_path_for_id(self.id)

    @property
    def is_resource(self) -> bool:
        return self._cache._flag_is_set(self.id, _FLAG_RESOURCE)

    @property
    def is_encrypted(self) -> bool:
        return self._cache._flag_is_set(self.id, _FLAG_ENCRYPTED)

    @property
    def archive_encryption(self) -> int:
        return int(self._cache._index.get_archive_encryption(self.id))

    @property
    def name_hash(self) -> int:
        return int(self._cache._index.get_name_hash(self.id))

    @property
    def short_hash(self) -> int:
        return int(self._cache._index.get_short_hash(self.id))

    @property
    def short_name_hash(self) -> int:
        return self.short_hash

    @property
    def key(self) -> str:
        return self.path

    @property
    def name(self) -> str:
        return _path_name(self.path)

    @property
    def extension(self) -> str:
        name = self.name
        dot = name.rfind(".")
        return name[dot:].lower() if dot >= 0 else ""

    @property
    def stem(self) -> str:
        return _path_stem(self.path)

    @property
    def is_loose(self) -> bool:
        return self._cache._flag_is_set(self.id, _FLAG_LOOSE)

    @property
    def is_archive_entry(self) -> bool:
        return self.entry is not None and self.archive is not None

    @property
    def source_path(self) -> str:
        loose = self.loose_path
        if loose is not None:
            return str(loose)
        archive = self.archive
        if archive is not None and archive.source_path:
            return archive.source_path
        return self.path

    @property
    def archive_rel(self) -> str | None:
        split = _split_archive_asset_path(self.path)
        return split[0] if split is not None else None

    @property
    def entry_path(self) -> str | None:
        split = _split_archive_asset_path(self.path)
        if split is None or not split[1]:
            return None
        return split[1]


class _AssetRecordList(Sequence[AssetRecord]):
    __slots__ = ("_cache",)

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache

    def __len__(self) -> int:
        return self._cache.asset_count

    def __getitem__(self, index: int | slice) -> AssetRecord | list[AssetRecord]:
        if isinstance(index, slice):
            return [self._cache._record_from_id(i) for i in range(*index.indices(len(self)))]
        return self._cache._record_from_id(index)

    def __iter__(self) -> AbcIterator[AssetRecord]:
        for asset_id in range(len(self)):
            yield self._cache._record_from_id(asset_id)


class _AssetRecordMap(Mapping[str, AssetRecord]):
    __slots__ = ("_cache",)

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache

    def __len__(self) -> int:
        return self._cache.asset_count

    def __iter__(self) -> AbcIterator[str]:
        yield from self._cache.iter_paths()

    def __getitem__(self, key: str) -> AssetRecord:
        asset_id = self._cache._index.find_path_id(_normalize_key(key))
        if asset_id is None:
            raise KeyError(key)
        return self._cache._record_from_id(asset_id)

    def get(self, key: str | Path, default: AssetRecord | None = None) -> AssetRecord | None:
        asset_id = self._cache._index.find_path_id(_normalize_key(key))
        if asset_id is None:
            return default
        return self._cache._record_from_id(asset_id)


class _KindHashRecordMap(Mapping[int, AssetRecord]):
    __slots__ = ("_cache", "_kind", "_generation", "_hash_to_id")

    def __init__(self, cache: GameFileCache, kind: GameFileType) -> None:
        self._cache = cache
        self._kind = kind
        self._generation = -1
        self._hash_to_id: dict[int, int] = {}

    def _ensure_index(self) -> None:
        if self._generation == self._cache._view_generation:
            return
        hash_to_id: dict[int, int] = {}
        for asset_id in self._cache._index.find_kind_ids(int(self._kind)):
            hash_to_id[int(self._cache._index.get_short_hash(asset_id))] = int(asset_id)
        self._hash_to_id = hash_to_id
        self._generation = self._cache._view_generation

    def __len__(self) -> int:
        self._ensure_index()
        return len(self._hash_to_id)

    def __iter__(self) -> AbcIterator[int]:
        self._ensure_index()
        yield from self._hash_to_id

    def __getitem__(self, key: int) -> AssetRecord:
        self._ensure_index()
        try:
            asset_id = self._hash_to_id[int(key)]
        except KeyError as exc:
            raise KeyError(key) from exc
        return self._cache._record_from_id(asset_id)

    def get(self, key: int, default: AssetRecord | None = None) -> AssetRecord | None:
        self._ensure_index()
        asset_id = self._hash_to_id.get(int(key))
        if asset_id is None:
            return default
        return self._cache._record_from_id(asset_id)


class _ArchetypeMap(Mapping[int, Any]):
    __slots__ = ("_cache", "_generation", "_hash_to_archetype")

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache
        self._generation = -1
        self._hash_to_archetype: dict[int, Any] = {}

    def _ensure_index(self) -> None:
        if self._generation == self._cache._view_generation:
            return
        hash_to_archetype: dict[int, Any] = {}
        for asset in self._cache.iter_assets(kind=GameFileType.YTYP):
            game_file = self._cache.get_file(asset)
            if game_file is None:
                continue
            parsed = game_file.parsed
            archetypes = getattr(parsed, "archetypes", None)
            if not isinstance(archetypes, list):
                continue
            for archetype in archetypes:
                name = getattr(archetype, "name", None)
                if name in (None, "", 0):
                    continue
                try:
                    name_hash = int(name)
                except Exception:
                    continue
                if name_hash == 0:
                    continue
                hash_to_archetype[name_hash] = archetype
        self._hash_to_archetype = hash_to_archetype
        self._generation = self._cache._view_generation

    def __len__(self) -> int:
        self._ensure_index()
        return len(self._hash_to_archetype)

    def __iter__(self) -> AbcIterator[int]:
        self._ensure_index()
        yield from self._hash_to_archetype

    def __getitem__(self, key: int) -> Any:
        self._ensure_index()
        try:
            return self._hash_to_archetype[int(key)]
        except KeyError as exc:
            raise KeyError(key) from exc

    def get(self, key: int | str | MetaHash, default: Any = None) -> Any:
        self._ensure_index()
        try:
            return self._hash_to_archetype[_coerce_hash_value(key)]
        except KeyError:
            return default


class _TextureParentMap(Mapping[int, int]):
    __slots__ = ("_cache", "_generation", "_hash_to_parent")

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache
        self._generation = -1
        self._hash_to_parent: dict[int, int] = {}

    def _add_relation(self, child: str, parent: str, mapping: dict[int, int]) -> None:
        child_name = str(child).strip().lower()
        parent_name = str(parent).strip().lower()
        if not child_name or not parent_name:
            return
        mapping[jenk_hash(child_name)] = jenk_hash(parent_name)

    def _load_xml_relations(self, xml_text: str, mapping: dict[int, int]) -> None:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return
        for item in root.findall(".//txdRelationships/Item") + root.findall(".//txdRelationships/item"):
            parent = item.findtext("parent", default="").strip()
            child = item.findtext("child", default="").strip()
            self._add_relation(child, parent, mapping)

    def _ensure_index(self) -> None:
        if self._generation == self._cache._view_generation:
            return
        hash_to_parent: dict[int, int] = {}
        for asset in self._cache.iter_assets():
            if asset.name.lower() not in {"gtxd.meta", "vehicles.meta", "peds.meta", "peds.ymt"}:
                continue
            data = self._cache.read_bytes(asset, logical=True)
            if not data:
                continue
            text = data.decode("utf-8", errors="ignore")
            if "<" not in text:
                continue
            self._load_xml_relations(text, hash_to_parent)
        self._hash_to_parent = hash_to_parent
        self._generation = self._cache._view_generation

    def __len__(self) -> int:
        self._ensure_index()
        return len(self._hash_to_parent)

    def __iter__(self) -> AbcIterator[int]:
        self._ensure_index()
        yield from self._hash_to_parent

    def __getitem__(self, key: int) -> int:
        self._ensure_index()
        try:
            return self._hash_to_parent[int(key)]
        except KeyError as exc:
            raise KeyError(key) from exc

    def get(self, key: int | str | MetaHash, default: int | None = None) -> int | None:
        self._ensure_index()
        return self._hash_to_parent.get(_coerce_hash_value(key), default)


class _KindCountsView(Mapping[GameFileType, int]):
    __slots__ = ("_cache", "_generation", "_counts")

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache
        self._generation = -1
        self._counts: dict[GameFileType, int] = {}

    def _ensure_index(self) -> None:
        if self._generation == self._cache._view_generation:
            return
        counts: dict[GameFileType, int] = {}
        for asset_id in range(self._cache.asset_count):
            kind = GameFileType(int(self._cache._index.get_kind(asset_id)))
            counts[kind] = counts.get(kind, 0) + 1
        self._counts = counts
        self._generation = self._cache._view_generation

    def __len__(self) -> int:
        self._ensure_index()
        return len(self._counts)

    def __iter__(self) -> AbcIterator[GameFileType]:
        self._ensure_index()
        yield from self._counts

    def __getitem__(self, key: GameFileType | str | int) -> int:
        self._ensure_index()
        kind = _coerce_kind(key)
        if kind is None:
            raise KeyError(key)
        try:
            return self._counts[kind]
        except KeyError as exc:
            raise KeyError(key) from exc

    def get(self, key: GameFileType | str | int, default: int | None = None) -> int | None:
        self._ensure_index()
        kind = _coerce_kind(key)
        if kind is None:
            return default
        return self._counts.get(kind, default)


@dataclass(slots=True)
class ScanStats:
    elapsed_seconds: float = 0.0
    used_index_cache: bool = False
    saved_index_cache: bool = False
    source_count: int = 0
    rpf_count: int = 0
    loose_count: int = 0
    asset_count: int = 0
    archive_workers: int = 0


@dataclass(slots=True)
class TextureRef:
    texture: Texture
    container_path: str = ""
    container_name: str = ""
    origin: str = "ytd"
    parent_depth: int = 0


@dataclass(slots=True)
class GameFileCache:
    root: str | Path | None = None
    resolver: HashResolver | None = None
    crypto: GameCrypto | None = None
    dlc_level: str | int | None = None
    exclude_folders: str | Path | list[str] | tuple[str, ...] | None = None
    load_vehicles: bool = True
    load_peds: bool = True
    load_audio: bool = True
    use_index_cache: bool = True
    index_cache_path: str | Path | None = None
    scan_workers: int | None = None
    max_open_archives: int = 8
    max_loaded_files: int = 32
    register_resolver_names: bool = False
    verbose: bool = False
    archives: list[RpfArchive] = field(default_factory=list)
    files: OrderedDict[str, GameFile] = field(default_factory=OrderedDict)
    entries: dict[str, RpfEntry] = field(default_factory=dict)
    assets: Mapping[str, AssetRecord] = field(init=False, repr=False)
    records: Sequence[AssetRecord] = field(init=False, repr=False)
    scan_errors: dict[str, str] = field(default_factory=dict)
    dlc_names: list[str] = field(default_factory=list)
    active_dlc_names: list[str] = field(default_factory=list)
    last_scan: ScanStats | None = None
    _index: CompactIndex = field(default_factory=CompactIndex, init=False, repr=False)
    _live_entries: dict[int, RpfFileEntry] = field(default_factory=dict, init=False, repr=False)
    _live_archives: dict[int, RpfArchive] = field(default_factory=dict, init=False, repr=False)
    _explicit_loose_paths: dict[int, str] = field(default_factory=dict, init=False, repr=False)
    _exclude_prefixes: tuple[str, ...] = field(default_factory=tuple, init=False, repr=False)
    _active_dlc_filter: set[str] | None = field(default=None, init=False, repr=False)
    _archive_lookup: OrderedDict[str, RpfArchive] = field(default_factory=OrderedDict, init=False, repr=False)
    _kind_dict_views: dict[int, _KindHashRecordMap] = field(default_factory=dict, init=False, repr=False)
    _archetype_view: _ArchetypeMap | None = field(default=None, init=False, repr=False)
    _texture_parent_view: _TextureParentMap | None = field(default=None, init=False, repr=False)
    _kind_counts_view: _KindCountsView | None = field(default=None, init=False, repr=False)
    _view_generation: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.resolver is None:
            self.resolver = get_hash_resolver()
        self._exclude_prefixes = _coerce_folder_prefixes(self.exclude_folders)
        self.assets = _AssetRecordMap(self)
        self.records = _AssetRecordList(self)

    @property
    def asset_count(self) -> int:
        return len(self._index)

    def __len__(self) -> int:
        return self.asset_count

    def __iter__(self) -> Iterator[AssetRecord]:
        return self.iter_assets()

    @property
    def scan_complete(self) -> bool:
        return self.last_scan is not None

    @property
    def has_assets(self) -> bool:
        return bool(len(self._index))

    @property
    def has_scan_errors(self) -> bool:
        return bool(self.scan_errors)

    @property
    def scan_ok(self) -> bool:
        return self.scan_complete and not self.has_scan_errors

    @property
    def used_index_cache(self) -> bool:
        return bool(self.last_scan.used_index_cache) if self.last_scan is not None else False

    @property
    def saved_index_cache(self) -> bool:
        return bool(self.last_scan.saved_index_cache) if self.last_scan is not None else False

    @property
    def open_archive_count(self) -> int:
        return len(self._archive_lookup)

    @property
    def open_file_count(self) -> int:
        return len(self.files)

    def _invalidate_views(self) -> None:
        self._view_generation += 1
        self._kind_dict_views.clear()
        self._archetype_view = None
        self._texture_parent_view = None
        self._kind_counts_view = None

    def clear(self) -> None:
        self.archives.clear()
        self.files.clear()
        self.entries.clear()
        self._index.clear()
        self._live_entries.clear()
        self._live_archives.clear()
        self._explicit_loose_paths.clear()
        self.scan_errors.clear()
        self.dlc_names.clear()
        self.active_dlc_names.clear()
        self._active_dlc_filter = None
        self._archive_lookup.clear()
        self._invalidate_views()

    def clear_runtime_cache(self, *, loaded_files: bool = False) -> None:
        self.archives.clear()
        self.entries.clear()
        self._archive_lookup.clear()
        self._live_entries.clear()
        self._live_archives.clear()
        if loaded_files:
            self.files.clear()

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[GameFileCache] {message}", flush=True)

    def _flag_is_set(self, asset_id: int, flag: int) -> bool:
        return bool(int(self._index.get_flags(asset_id)) & flag)

    def _loose_path_for_id(self, asset_id: int) -> Path | None:
        explicit = self._explicit_loose_paths.get(asset_id)
        if explicit is not None:
            return Path(explicit)
        if not self._flag_is_set(asset_id, _FLAG_LOOSE) or self.root is None:
            return None
        return Path(self.root) / self._index.get_path(asset_id)

    def summary(self) -> dict[str, Any]:
        stats = self.last_scan
        return {
            "root": str(self.root) if self.root is not None else None,
            "scan_complete": self.scan_complete,
            "scan_ok": self.scan_ok,
            "has_assets": self.has_assets,
            "has_scan_errors": self.has_scan_errors,
            "asset_count": self.asset_count,
            "scan_error_count": len(self.scan_errors),
            "used_index_cache": self.used_index_cache,
            "saved_index_cache": self.saved_index_cache,
            "open_archive_count": self.open_archive_count,
            "open_file_count": self.open_file_count,
            "kind_counts": self.stats_by_kind(),
            "dlc_level": self.dlc_level,
            "load_vehicles": self.load_vehicles,
            "load_peds": self.load_peds,
            "load_audio": self.load_audio,
            "elapsed_seconds": float(stats.elapsed_seconds) if stats is not None else None,
            "source_count": int(stats.source_count) if stats is not None else 0,
            "rpf_count": int(stats.rpf_count) if stats is not None else 0,
            "loose_count": int(stats.loose_count) if stats is not None else 0,
            "archive_workers": int(stats.archive_workers) if stats is not None else 0,
        }

    def get_kind_dict(self, kind: GameFileType | str | int) -> Mapping[int, AssetRecord]:
        kind_value = _coerce_kind(kind)
        if kind_value is None:
            raise ValueError(f"Unsupported game file kind: {kind!r}")
        key = int(kind_value)
        view = self._kind_dict_views.get(key)
        if view is None:
            view = _KindHashRecordMap(self, kind_value)
            self._kind_dict_views[key] = view
        return view

    def kind_dict(self, kind: GameFileType | str | int) -> Mapping[int, AssetRecord]:
        return self.get_kind_dict(kind)

    @property
    def archetype_dict(self) -> Mapping[int, Any]:
        if self._archetype_view is None:
            self._archetype_view = _ArchetypeMap(self)
        return self._archetype_view

    @property
    def ArchetypeDict(self) -> Mapping[int, Any]:
        return self.archetype_dict

    @property
    def texture_parent_dict(self) -> Mapping[int, int]:
        if self._texture_parent_view is None:
            self._texture_parent_view = _TextureParentMap(self)
        return self._texture_parent_view

    @property
    def TxdParentDict(self) -> Mapping[int, int]:
        return self.texture_parent_dict

    @property
    def kind_counts(self) -> Mapping[GameFileType, int]:
        if self._kind_counts_view is None:
            self._kind_counts_view = _KindCountsView(self)
        return self._kind_counts_view

    def stats_by_kind(self) -> dict[str, int]:
        return {
            kind.name: count
            for kind, count in sorted(self.kind_counts.items(), key=lambda item: item[0].name)
        }

    def populate_resolver(self, resolver: HashResolver | None = None) -> int:
        target = resolver or self.resolver
        if target is None:
            return 0
        before = len(target.hash_to_name)
        for asset_id in range(self.asset_count):
            target.register_path_name(self._index.get_path(asset_id))
        added = len(target.hash_to_name) - before
        self._log(f"resolver populated added={added}")
        return added

    def set_dlc_level(self, value: str | int | None) -> str | int | None:
        self.dlc_level = value
        return self.dlc_level

    def use_dlc(self, value: str | int | None) -> str | int | None:
        return self.set_dlc_level(value)

    def set_exclude_folders(self, value: str | Path | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
        self.exclude_folders = value
        self._exclude_prefixes = _coerce_folder_prefixes(value)
        return self._exclude_prefixes

    def ignore_folders(self, *values: str | Path) -> tuple[str, ...]:
        if len(values) == 1 and isinstance(values[0], (list, tuple)):
            raw_values = tuple(values[0])
        else:
            raw_values = values
        merged = [*self._exclude_prefixes, *_coerce_folder_prefixes(raw_values)]
        deduped = tuple(dict.fromkeys(merged))
        self.exclude_folders = list(deduped)
        self._exclude_prefixes = deduped
        return self._exclude_prefixes

    @property
    def ignored_folders(self) -> tuple[str, ...]:
        return self._exclude_prefixes

    def set_load_flags(
        self,
        *,
        load_vehicles: bool | None = None,
        load_peds: bool | None = None,
        load_audio: bool | None = None,
    ) -> tuple[bool, bool, bool]:
        if load_vehicles is not None:
            self.load_vehicles = bool(load_vehicles)
        if load_peds is not None:
            self.load_peds = bool(load_peds)
        if load_audio is not None:
            self.load_audio = bool(load_audio)
        return self.load_vehicles, self.load_peds, self.load_audio

    def _asset_skip_mask(self) -> int:
        mask = 0
        if not self.load_audio:
            mask |= _SKIP_AUDIO
        if not self.load_vehicles:
            mask |= _SKIP_VEHICLES
        if not self.load_peds:
            mask |= _SKIP_PEDS
        return mask

    def _should_index_asset(self, path: str | Path) -> bool:
        return (_asset_category_mask(path) & self._asset_skip_mask()) == 0

    def _should_scan_source(self, path: str | Path) -> bool:
        return (_asset_category_mask(path) & self._asset_skip_mask()) == 0

    def get_index_cache_path(self) -> Path:
        if self.index_cache_path is not None:
            return Path(self.index_cache_path)
        root_text = str(Path(self.root or ".").resolve()).lower()
        config_text = f"{self._normalized_dlc_level()}|{';'.join(self._exclude_prefixes)}"
        flags_text = f"{int(self.load_vehicles)}|{int(self.load_peds)}|{int(self.load_audio)}"
        digest = hashlib.sha1(f"{root_text}|{config_text}|{flags_text}".encode("utf-8")).hexdigest()
        return _default_index_cache_dir() / f"{digest}.ffindex"

    def clear_index_cache(self) -> None:
        path = self.get_index_cache_path()
        if path.is_file():
            path.unlink()

    def _normalized_dlc_level(self) -> str | int | None:
        value = self.dlc_level
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or None
        return value

    def _make_scan_stats(
        self,
        *,
        started_at: float,
        used_index_cache: bool,
        saved_index_cache: bool,
        source_count: int,
        rpf_count: int,
        loose_count: int,
        archive_workers: int,
    ) -> ScanStats:
        return ScanStats(
            elapsed_seconds=time.perf_counter() - started_at,
            used_index_cache=used_index_cache,
            saved_index_cache=saved_index_cache,
            source_count=source_count,
            rpf_count=rpf_count,
            loose_count=loose_count,
            asset_count=self.asset_count,
            archive_workers=archive_workers,
        )

    def _resolve_scan_workers(self, rpf_count: int) -> int:
        if rpf_count <= 0:
            return 0
        configured = self.scan_workers
        if configured is None:
            configured = min(16, max(1, os.cpu_count() or 1))
        try:
            workers = int(configured)
        except Exception:
            workers = 1
        return max(1, min(workers, rpf_count))

    def _index_cache_relative_path(self, root: Path) -> str | None:
        try:
            return Path(self.get_index_cache_path()).resolve().relative_to(root.resolve()).as_posix()
        except Exception:
            return None

    def _build_source_manifest(self, root: Path) -> list[tuple[str, int, int]]:
        manifest: list[tuple[str, int, int]] = []
        index_rel = self._index_cache_relative_path(root)
        for rel, path in self._iter_files(root):
            if index_rel is not None and _normalize_key(rel) == _normalize_key(index_rel):
                continue
            if not self._should_scan_source(rel):
                self._log(f"skip source {rel}")
                continue
            stat = path.stat()
            manifest.append((rel, stat.st_size, stat.st_mtime_ns))
        return manifest

    def _pack_index_columns(self) -> bytes:
        return bytes(self._index.export_state())

    def _restore_index_columns(self, payload: bytes | bytearray | memoryview) -> bool:
        try:
            self._index.import_state(bytes(payload))
        except Exception:
            return False
        self._live_entries.clear()
        self._live_archives.clear()
        self._explicit_loose_paths.clear()
        return True

    def _load_index_payload(self, path: Path) -> dict[str, Any] | None:
        try:
            return pickle.loads(path.read_bytes())
        except Exception:
            return None

    def _save_index_payload(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))

    def _record_from_id(self, asset_id: int) -> AssetRecord:
        if asset_id < 0 or asset_id >= self.asset_count:
            raise IndexError(asset_id)
        return AssetRecord.from_cache(self, asset_id)

    def _load_index_cache(self, root: Path, manifest: list[tuple[str, int, int]], cache_path: Path) -> bool:
        payload = self._load_index_payload(cache_path)
        if not isinstance(payload, dict):
            return False
        config = payload.get("config")
        expected_config = {
            "root": str(root.resolve()).lower(),
            "dlc_level": self._normalized_dlc_level(),
            "exclude_folders": list(self._exclude_prefixes),
            "load_vehicles": self.load_vehicles,
            "load_peds": self.load_peds,
            "load_audio": self.load_audio,
        }
        if payload.get("version") != _SCAN_INDEX_VERSION or config != expected_config:
            return False
        if payload.get("manifest") != manifest:
            return False
        columns = payload.get("columns")
        if not isinstance(columns, (bytes, bytearray, memoryview)):
            return False
        self.scan_errors = dict(payload.get("scan_errors") or {})
        self.dlc_names = list(payload.get("dlc_names") or self.dlc_names)
        self.active_dlc_names = self._resolve_active_dlc_names()
        if not self._restore_index_columns(columns):
            return False
        if self.register_resolver_names and self.resolver is not None:
            self.populate_resolver(self.resolver)
        return True

    def _save_index_cache(self, root: Path, manifest: list[tuple[str, int, int]], cache_path: Path) -> None:
        payload = {
            "version": _SCAN_INDEX_VERSION,
            "config": {
                "root": str(root.resolve()).lower(),
                "dlc_level": self._normalized_dlc_level(),
                "exclude_folders": list(self._exclude_prefixes),
                "load_vehicles": self.load_vehicles,
                "load_peds": self.load_peds,
                "load_audio": self.load_audio,
            },
            "manifest": manifest,
            "columns": self._pack_index_columns(),
            "scan_errors": dict(self.scan_errors),
            "dlc_names": list(self.dlc_names),
        }
        self._save_index_payload(cache_path, payload)

    def load_keys(
        self,
        root_or_exe: str | Path | None = None,
        *,
        exe_path: str | Path | None = None,
        magic_path: str | Path | None = None,
        aes_key: bytes | str | None = None,
        gen9: bool = False,
        cache_path: str | Path | None = None,
        use_cache: bool = True,
    ) -> GameCrypto:
        source = exe_path or root_or_exe or self.root
        if source is None:
            raise ValueError("A game root or executable path is required")
        self._log(f"loading keys source={source}")
        self.crypto = load_game_keys(
            source,
            magic_path=magic_path,
            aes_key=aes_key,
            gen9=gen9,
            cache_path=cache_path,
            use_cache=use_cache,
        )
        return self.crypto

    def scan(
        self,
        root: str | Path | None = None,
        *,
        load_keys: bool | None = None,
        dlc_level: str | int | None = None,
        exclude_folders: str | Path | list[str] | tuple[str, ...] | None = None,
        load_vehicles: bool | None = None,
        load_peds: bool | None = None,
        load_audio: bool | None = None,
        use_index_cache: bool | None = None,
        refresh_index_cache: bool = False,
        index_cache_path: str | Path | None = None,
        scan_workers: int | None = None,
        register_resolver_names: bool | None = None,
        verbose: bool | None = None,
        exe_path: str | Path | None = None,
        magic_path: str | Path | None = None,
        aes_key: bytes | str | None = None,
        gen9: bool = False,
        cache_path: str | Path | None = None,
        use_cache: bool = True,
    ) -> None:
        started_at = time.perf_counter()
        if root is not None:
            self.root = root
        if self.root is None:
            raise ValueError("A root directory is required")
        if dlc_level is not None:
            self.dlc_level = dlc_level
        if exclude_folders is not None:
            self.set_exclude_folders(exclude_folders)
        if load_vehicles is not None or load_peds is not None or load_audio is not None:
            self.set_load_flags(
                load_vehicles=load_vehicles,
                load_peds=load_peds,
                load_audio=load_audio,
            )
        if index_cache_path is not None:
            self.index_cache_path = index_cache_path
        if scan_workers is not None:
            self.scan_workers = scan_workers
        if register_resolver_names is not None:
            self.register_resolver_names = bool(register_resolver_names)
        if verbose is not None:
            self.verbose = bool(verbose)
        cache_enabled = self.use_index_cache if use_index_cache is None else bool(use_index_cache)

        root_path = Path(self.root)
        self._log(
            "scan start "
            f"root={root_path} "
            f"dlc_level={self.dlc_level!r} "
            f"exclude_folders={self._exclude_prefixes!r} "
            f"load_vehicles={self.load_vehicles} "
            f"load_peds={self.load_peds} "
            f"load_audio={self.load_audio} "
            f"use_index_cache={cache_enabled} "
            f"scan_workers={self.scan_workers}"
        )
        should_load_keys = bool(load_keys)
        if load_keys is None:
            should_load_keys = (root_path / "gta5.exe").is_file() or (root_path / "gta5_enhanced.exe").is_file() or exe_path is not None or aes_key is not None
        if should_load_keys:
            self.load_keys(
                root_path,
                exe_path=exe_path,
                magic_path=magic_path,
                aes_key=aes_key,
                gen9=gen9,
                cache_path=cache_path,
                use_cache=use_cache,
            )

        self.clear()
        self.dlc_names = self._discover_dlc_names(root_path)
        self.active_dlc_names = self._resolve_active_dlc_names()
        self._active_dlc_filter = set(self.active_dlc_names) if self._should_restrict_dlc() else None
        manifest = self._build_source_manifest(root_path)
        rpf_count = sum(1 for rel, _, _ in manifest if rel.lower().endswith(".rpf"))
        loose_count = len(manifest) - rpf_count
        index_path = self.get_index_cache_path()
        if cache_enabled and not refresh_index_cache and self._load_index_cache(root_path, manifest, index_path):
            self._log(f"index cache hit path={index_path}")
            self.last_scan = self._make_scan_stats(
                started_at=started_at,
                used_index_cache=True,
                saved_index_cache=False,
                source_count=len(manifest),
                rpf_count=rpf_count,
                loose_count=loose_count,
                archive_workers=0,
            )
            return

        archive_workers = self._resolve_scan_workers(rpf_count)
        asset_skip_mask = self._asset_skip_mask()
        processed_archives = 0
        total_sources = len(manifest)
        archive_rels = [rel for rel, _, _ in manifest if rel.lower().endswith(".rpf")]
        native_crypto = self.crypto.native_context() if self.crypto is not None else None
        hash_lut = _get_lut()

        try:
            if archive_rels:
                archive_sources = [(root_path / rel, rel) for rel in archive_rels]
                for rel, payload_count, error in _scan_archive_sources_batch(
                    archive_sources,
                    self._index,
                    native_crypto,
                    hash_lut,
                    asset_skip_mask,
                    archive_workers,
                    self.verbose,
                ):
                    if error:
                        self.scan_errors[_normalize_key(rel)] = error
                        continue
                    processed_archives += 1
                    if processed_archives % _SCAN_GC_INTERVAL == 0:
                        gc.collect()

            for source_index, (rel, _, _) in enumerate(manifest, start=1):
                path = root_path / rel
                if path.suffix.lower() == ".rpf":
                    continue
                self._log(f"scan file {rel} [source {source_index}/{total_sources}]")
                if not self._should_index_asset(rel):
                    continue
                stat = path.stat()
                self._register_asset(
                    path=rel,
                    kind=guess_game_file_type(rel, GameFileType.UNKNOWN),
                    size=stat.st_size,
                    uncompressed_size=stat.st_size,
                    flags=_FLAG_LOOSE,
                )
        finally:
            pass
        gc.collect()
        if self.register_resolver_names and self.resolver is not None:
            self.populate_resolver(self.resolver)
        saved_index_cache = False
        if cache_enabled:
            self._save_index_cache(root_path, manifest, index_path)
            saved_index_cache = True
            self._log(f"index cache saved path={index_path}")
        self.last_scan = self._make_scan_stats(
            started_at=started_at,
            used_index_cache=False,
            saved_index_cache=saved_index_cache,
            source_count=len(manifest),
            rpf_count=rpf_count,
            loose_count=loose_count,
            archive_workers=archive_workers,
        )
        self._log(
            "scan done "
            f"assets={self.asset_count} "
            f"errors={len(self.scan_errors)} "
            f"elapsed={self.last_scan.elapsed_seconds:.3f}s"
        )

    def scan_game(self, root: str | Path | None = None, **kwargs: Any) -> None:
        self.scan(root, load_keys=True, **kwargs)

    def _iter_files(self, root: Path) -> Iterator[tuple[str, Path]]:
        for base, dirnames, filenames in os.walk(root):
            rel_base = "" if Path(base) == root else Path(base).relative_to(root).as_posix()
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if not self._should_skip_path(f"{rel_base}/{dirname}" if rel_base else dirname)
            ]
            dirnames.sort(key=str.lower)
            filenames.sort(key=str.lower)
            base_path = Path(base)
            for filename in filenames:
                path = base_path / filename
                rel = path.relative_to(root).as_posix()
                if self._should_skip_path(rel):
                    continue
                yield rel, path

    def _discover_dlc_names(self, root: Path) -> list[str]:
        update_rpf = root / "update" / "update.rpf"
        if update_rpf.is_file():
            try:
                archive = RpfArchive.from_path(update_rpf, crypto=self.crypto)
                entry = archive.find_entry("common/data/dlclist.xml")
                if isinstance(entry, RpfFileEntry):
                    names = _parse_dlc_names_from_text(entry.read(logical=True))
                    if names:
                        return names
            except Exception:
                pass
        dlcpacks_dir = root / "update" / "x64" / "dlcpacks"
        if not dlcpacks_dir.is_dir():
            return []
        return sorted((item.name.lower() for item in dlcpacks_dir.iterdir() if item.is_dir()), key=str.lower)

    def _should_restrict_dlc(self) -> bool:
        level = self.dlc_level
        if level is None:
            return False
        if isinstance(level, str):
            return level.strip().lower() not in ("", "all")
        return True

    def _resolve_active_dlc_names(self) -> list[str]:
        if not self.dlc_names:
            return []
        level = self.dlc_level
        if level is None:
            return list(self.dlc_names)
        if isinstance(level, str):
            normalized = level.strip().lower()
            if normalized in ("", "all"):
                return list(self.dlc_names)
            if normalized == "base":
                return []
            try:
                index = self.dlc_names.index(normalized)
            except ValueError as exc:
                raise ValueError(f"Unknown DLC level: {level}") from exc
            return self.dlc_names[: index + 1]
        index = int(level)
        if index < 0:
            return []
        if index >= len(self.dlc_names):
            return list(self.dlc_names)
        return self.dlc_names[: index + 1]

    def _extract_dlc_name(self, rel_path: str) -> str | None:
        normalized = _normalize_folder_prefix(rel_path)
        prefix = "update/x64/dlcpacks/"
        if not normalized.startswith(prefix):
            return None
        suffix = normalized[len(prefix) :]
        if not suffix:
            return None
        return suffix.split("/", 1)[0]

    def _should_skip_path(self, rel_path: str | Path) -> bool:
        normalized = _normalize_folder_prefix(rel_path)
        if not normalized:
            return False
        for prefix in self._exclude_prefixes:
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
        if self._active_dlc_filter is None:
            return False
        dlc_name = self._extract_dlc_name(normalized)
        return dlc_name is not None and dlc_name not in self._active_dlc_filter

    def register_archive(self, archive: RpfArchive, *, source_prefix: str | None = None) -> None:
        self.archives.append(archive)
        prefix = (source_prefix or "").replace("\\", "/").strip("/")
        if prefix:
            self._remember_archive(_normalize_key(prefix), archive)
        for entry in archive.iter_entries(include_directories=False):
            if not isinstance(entry, RpfFileEntry):
                continue
            logical_path = f"{prefix}/{entry.full_path}".strip("/") if prefix else entry.full_path
            self.entries[_normalize_key(logical_path)] = entry
            size = entry.get_file_size()
            flags = 0
            if entry.__class__.__name__.lower().startswith("rpfresource"):
                flags |= _FLAG_RESOURCE
            if entry.is_encrypted:
                flags |= _FLAG_ENCRYPTED
            self._register_asset(
                path=logical_path,
                kind=guess_game_file_type(entry.full_path, GameFileType.UNKNOWN),
                size=size,
                uncompressed_size=getattr(entry, "file_uncompressed_size", size) or size,
                entry=entry,
                archive=entry._archive,
                flags=flags,
                archive_encryption=archive.encryption,
            )
        for child in archive.children:
            self.register_archive(child, source_prefix=prefix)

    def _remember_archive(self, key: str, archive: RpfArchive) -> None:
        normalized = _normalize_key(key)
        limit = max(0, int(self.max_open_archives))
        if limit <= 0:
            self._archive_lookup.clear()
            return
        self._archive_lookup.pop(normalized, None)
        self._archive_lookup[normalized] = archive
        while len(self._archive_lookup) > limit:
            self._archive_lookup.popitem(last=False)

    def _register_asset(
        self,
        *,
        path: str,
        kind: GameFileType,
        size: int,
        uncompressed_size: int,
        entry: RpfFileEntry | None = None,
        archive: RpfArchive | None = None,
        loose_path: Path | None = None,
        flags: int = 0,
        archive_encryption: int = 0,
        name_hash: int | None = None,
        short_hash: int | None = None,
    ) -> int:
        normalized_path = _normalize_key(path)
        if name_hash is None or short_hash is None:
            name_hash, short_hash = _maybe_hash_name(normalized_path)
        if loose_path is not None:
            flags |= _FLAG_LOOSE
        asset_id = int(
            self._index.add(
                normalized_path,
                int(kind),
                int(size),
                int(uncompressed_size),
                int(flags) & 0xFF,
                int(archive_encryption),
                int(name_hash),
                int(short_hash),
            )
        )
        if entry is not None:
            self._live_entries[asset_id] = entry
        if archive is not None:
            self._live_archives[asset_id] = archive
        if loose_path is not None:
            self._explicit_loose_paths[asset_id] = str(loose_path)
        return asset_id

    def _iter_ids(self, ids: list[int], *, kind: GameFileType | str | int | None = None) -> Iterator[AssetRecord]:
        kind_value = _coerce_kind(kind)
        seen: set[int] = set()
        for asset_id in ids:
            if asset_id in seen or asset_id < 0 or asset_id >= self.asset_count:
                continue
            if kind_value is not None and GameFileType(int(self._index.get_kind(asset_id))) is not kind_value:
                continue
            seen.add(asset_id)
            yield self._record_from_id(asset_id)

    def iter_assets(self, kind: GameFileType | str | int | None = None) -> Iterator[AssetRecord]:
        kind_value = _coerce_kind(kind)
        if kind_value is None:
            for asset_id in range(self.asset_count):
                yield self._record_from_id(asset_id)
            return
        for asset_id in self._index.find_kind_ids(int(kind_value)):
            yield self._record_from_id(asset_id)

    def iter_paths(self, kind: GameFileType | str | int | None = None) -> Iterator[str]:
        if kind is None:
            for asset_id in range(self.asset_count):
                yield self._index.get_path(asset_id)
            return
        for asset in self.iter_assets(kind=kind):
            yield asset.path

    def iter_kind(self, kind: GameFileType | str | int) -> Iterator[AssetRecord]:
        return self.iter_assets(kind=kind)

    def list_assets(self, kind: GameFileType | str | int | None = None) -> list[AssetRecord]:
        return list(self.iter_assets(kind=kind))

    def list_kind(self, kind: GameFileType | str | int) -> list[AssetRecord]:
        return self.list_assets(kind=kind)

    def list_paths(self, kind: GameFileType | str | int | None = None) -> list[str]:
        return list(self.iter_paths(kind=kind))

    def list_kind_paths(self, kind: GameFileType | str | int) -> list[str]:
        return self.list_paths(kind=kind)

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
        decoder = _try_load_decoder("fivefury.ymap", "read_ymap")
        if decoder is not None and isinstance(value, (bytes, bytearray, memoryview)):
            try:
                parsed = decoder(bytes(value))
            except Exception:
                parsed = None
            if parsed is not None and hasattr(parsed, "entities"):
                return parsed
        game_file = self.get_file(value)
        parsed = game_file.parsed if game_file is not None else None
        if parsed is None or not hasattr(parsed, "entities"):
            candidate = Path(str(value))
            if decoder is not None and candidate.is_file():
                try:
                    parsed = decoder(candidate.read_bytes())
                except Exception:
                    parsed = None
            if parsed is None or not hasattr(parsed, "entities"):
                return None
        return parsed

    def _coerce_ytd(self, value: Any) -> Any | None:
        if hasattr(value, "textures"):
            return value
        decoder = _try_load_decoder("fivefury.ytd", "read_ytd")
        if decoder is not None and isinstance(value, (bytes, bytearray, memoryview)):
            try:
                parsed = decoder(bytes(value))
            except Exception:
                parsed = None
            if parsed is not None and hasattr(parsed, "textures"):
                return parsed
        game_file = self.get_file(value)
        parsed = game_file.parsed if game_file is not None else None
        if parsed is None or not hasattr(parsed, "textures"):
            candidate = Path(str(value))
            if decoder is not None and candidate.is_file():
                try:
                    parsed = decoder(candidate.read_bytes())
                except Exception:
                    parsed = None
            if parsed is None or not hasattr(parsed, "textures"):
                return None
        return parsed

    def _find_archetypes_for_asset(self, value: Any) -> Iterator[Any]:
        yield from self._iter_archetypes_for_query(value)

    def iter_asset_texture_dictionaries(self, query: Any) -> Iterator[AssetRecord]:
        yield from self.iter_texture_dictionaries(query, include_parents=False)

    def list_asset_texture_dictionaries(self, query: Any) -> list[AssetRecord]:
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

    def _primary_asset_for_archetype(self, archetype: Any) -> AssetRecord | None:
        asset_name = getattr(archetype, "asset_name", None) or getattr(archetype, "name", None)
        if asset_name in (None, "", 0):
            return None
        kind = _asset_kind_from_archetype_type(int(getattr(archetype, "asset_type", 0) or 0))
        if kind is not None:
            asset = self.get_asset(asset_name, kind=kind)
            if asset is not None:
                return asset
        for fallback_kind in (GameFileType.YDR, GameFileType.YDD, GameFileType.YFT):
            asset = self.get_asset(asset_name, kind=fallback_kind)
            if asset is not None:
                return asset
        return None

    def _supporting_assets_for_archetype(self, archetype: Any) -> Iterator[AssetRecord]:
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

    def iter_ymap_entity_assets(self, query: Any, *, include_supporting: bool = True) -> Iterator[AssetRecord]:
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

    def list_ymap_entity_assets(self, query: Any, *, include_supporting: bool = True) -> list[AssetRecord]:
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

    def _iter_texture_dict_chain_assets(self, value: int | str | MetaHash) -> Iterator[tuple[AssetRecord, int]]:
        seen_hashes: set[int] = set()
        current_hash = _coerce_hash_value(value)
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

    def iter_texture_dictionaries(self, query: Any, *, include_parents: bool = True) -> Iterator[AssetRecord]:
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

    def list_texture_dictionaries(self, query: Any, *, include_parents: bool = True) -> list[AssetRecord]:
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

    def _read_standalone_resource_bytes(self, asset: AssetRecord) -> bytes | None:
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

    def _iter_primary_texture_assets(self, query: Any) -> Iterator[AssetRecord]:
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
                yield TextureRef(texture=texture, container_name=container_name, container_path="", origin="ytd", parent_depth=0)
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

    def find_path(self, path: str | Path, *, kind: GameFileType | str | int | None = None) -> AssetRecord | None:
        asset_id = self._index.find_path_id(_normalize_key(path))
        if asset_id is None:
            return None
        kind_value = _coerce_kind(kind)
        if kind_value is not None and GameFileType(int(self._index.get_kind(asset_id))) is not kind_value:
            return None
        return self._record_from_id(asset_id)

    def find_hash(self, value: int | MetaHash | str, *, kind: GameFileType | str | int | None = None, limit: int | None = None) -> list[AssetRecord]:
        if isinstance(value, str):
            name_hash = jenk_hash(_path_name(value).lower())
            short_hash = jenk_hash(_path_stem(value).lower())
            ids = [*self._index.find_hash_ids(short_hash), *self._index.find_hash_ids(name_hash)]
        else:
            ids = list(self._index.find_hash_ids(int(value)))
        result = list(self._iter_ids(ids, kind=kind))
        return result[:limit] if limit is not None else result

    def find_name(
        self,
        name: str | Path,
        *,
        kind: GameFileType | str | int | None = None,
        exact: bool = True,
        limit: int | None = None,
    ) -> list[AssetRecord]:
        text = _path_name(str(name)).lower()
        if not text:
            return []
        if exact:
            stem = _path_stem(text)
            ids = [*self._index.find_hash_ids(jenk_hash(stem)), *self._index.find_hash_ids(jenk_hash(text))]
            result: list[AssetRecord] = []
            seen: set[int] = set()
            kind_value = _coerce_kind(kind)
            for asset_id in ids:
                if asset_id in seen or asset_id < 0 or asset_id >= self.asset_count:
                    continue
                if kind_value is not None and GameFileType(int(self._index.get_kind(asset_id))) is not kind_value:
                    continue
                path_value = self._index.get_path(asset_id)
                if _path_name(path_value) != text and _path_stem(path_value) != stem:
                    continue
                seen.add(asset_id)
                result.append(self._record_from_id(asset_id))
                if limit is not None and len(result) >= limit:
                    break
            if not result:
                result = self.find_hash(text, kind=kind, limit=limit)
            return result[:limit] if limit is not None else result
        lower = text
        result: list[AssetRecord] = []
        kind_value = _coerce_kind(kind)
        for asset_id in range(self.asset_count):
            if kind_value is not None and GameFileType(int(self._index.get_kind(asset_id))) is not kind_value:
                continue
            path_value = self._index.get_path(asset_id)
            if lower in path_value:
                result.append(self._record_from_id(asset_id))
                if limit is not None and len(result) >= limit:
                    break
        return result

    def find_assets(
        self,
        query: str | Path | int | MetaHash,
        *,
        kind: GameFileType | str | int | None = None,
        exact: bool = True,
        limit: int | None = None,
    ) -> list[AssetRecord]:
        if isinstance(query, (int, MetaHash)):
            return self.find_hash(query, kind=kind, limit=limit)
        path_match = self.find_path(query, kind=kind)
        if path_match is not None:
            return [path_match]
        return self.find_name(query, kind=kind, exact=exact, limit=limit)

    def search_assets(
        self,
        query: str | Path,
        *,
        kind: GameFileType | str | int | None = None,
        limit: int | None = 100,
    ) -> list[AssetRecord]:
        return self.find_name(query, kind=kind, exact=False, limit=limit)

    def get_asset(self, query: str | Path | int | MetaHash, *, kind: GameFileType | str | int | None = None) -> AssetRecord | None:
        matches = self.find_assets(query, kind=kind, exact=True, limit=1)
        return matches[0] if matches else None

    def has_asset(self, query: str | Path | int | MetaHash, *, kind: GameFileType | str | int | None = None) -> bool:
        return self.get_asset(query, kind=kind) is not None

    def iter_files(self) -> Iterator[GameFile]:
        yield from self.files.values()

    def _remember_file(self, key: str, game_file: GameFile) -> None:
        limit = max(0, int(self.max_loaded_files))
        if limit <= 0:
            return
        self.files.pop(key, None)
        self.files[key] = game_file
        while len(self.files) > limit:
            evicted_key, _ = self.files.popitem(last=False)
            self._log(f"evict file {evicted_key}")

    def _open_archive_for_asset(self, asset: AssetRecord) -> RpfArchive | None:
        archive_rel = asset.archive_rel
        if archive_rel is None or self.root is None:
            return None
        key = _normalize_key(archive_rel)
        cached = self._archive_lookup.get(key)
        if cached is not None:
            self._archive_lookup.move_to_end(key)
            self._log(f"archive cache hit {archive_rel}")
            return cached
        archive_path = Path(self.root) / archive_rel
        if not archive_path.is_file():
            return None
        self._log(f"open archive {archive_rel}")
        archive = RpfArchive.from_path(archive_path, crypto=self.crypto)
        self._remember_archive(key, archive)
        return archive

    def _get_entry_for_asset(self, asset: AssetRecord) -> RpfEntry | None:
        if asset.entry is not None and asset.archive is not None:
            return asset.entry
        cached = self.entries.get(asset.key)
        if cached is not None:
            return cached
        entry_path = asset.entry_path
        if entry_path is None:
            return None
        archive = self._open_archive_for_asset(asset)
        if archive is None:
            return None
        return archive.find_entry(entry_path)

    def get_entry(self, path: str | Path | AssetRecord) -> Optional[RpfEntry]:
        asset = path if isinstance(path, AssetRecord) else self.find_path(path)
        if asset is None:
            return None
        return self._get_entry_for_asset(asset)

    def _coerce_asset(self, value: AssetRecord | str | Path | int | MetaHash, *, kind: GameFileType | str | int | None = None) -> AssetRecord | None:
        if isinstance(value, AssetRecord):
            return value
        return self.get_asset(value, kind=kind)

    def get_file(self, path: str | Path | AssetRecord | int | MetaHash) -> GameFile | None:
        asset = self._coerce_asset(path)
        if asset is None:
            return None
        cached = self.files.get(asset.key)
        if cached is not None:
            self.files.move_to_end(asset.key)
            self._log(f"file cache hit {asset.path}")
            return cached

        entry = self._get_entry_for_asset(asset)
        if entry is not None:
            if entry._archive is None:
                raise ValueError(f"Entry is detached from archive: {asset.path}")
            self._log(f"read file {asset.path}")
            stored = entry.read(logical=False)
            logical = entry.read(logical=True)
            decode_bytes = logical
            if asset.path.lower().endswith(".ytd"):
                decode_bytes = entry._archive.read_entry_standalone(entry)
            parsed, kind = _decode_payload(asset.path, decode_bytes)
            game_file = GameFile(
                path=asset.path,
                kind=kind,
                entry=entry if isinstance(entry, RpfFileEntry) else None,
                archive=entry._archive,
                raw=stored,
                parsed=parsed,
                loaded=True,
            )
            self._remember_file(asset.key, game_file)
            return game_file

        loose = asset.loose_path
        if loose is None:
            return None
        self._log(f"read file {asset.path}")
        data = loose.read_bytes()
        parsed, kind = _decode_payload(asset.path, data)
        game_file = GameFile(path=asset.path, kind=kind, raw=data, parsed=parsed, loaded=True)
        self._remember_file(asset.key, game_file)
        return game_file

    def load_asset(self, query: str | Path | int | MetaHash | AssetRecord) -> GameFile | None:
        return self.get_file(query)

    def read_bytes(self, query: str | Path | AssetRecord | int | MetaHash, *, logical: bool = True) -> bytes | None:
        asset = self._coerce_asset(query)
        if asset is None:
            return None
        entry = self._get_entry_for_asset(asset)
        if isinstance(entry, RpfFileEntry):
            self._log(f"read bytes {asset.path} logical={logical}")
            return entry.read(logical=logical)
        if asset.loose_path is not None:
            self._log(f"read bytes {asset.path} logical={logical}")
            return asset.loose_path.read_bytes()
        return None

    def get_bytes(self, path: str | Path | AssetRecord | int | MetaHash, *, logical: bool = True) -> bytes | None:
        return self.read_bytes(path, logical=logical)

    def read_asset(self, query: str | Path | int | MetaHash | AssetRecord, *, logical: bool = True) -> bytes | None:
        return self.read_bytes(query, logical=logical)

    def extract_asset(
        self,
        query: str | Path | int | MetaHash | AssetRecord,
        destination: str | Path,
        *,
        logical: bool = False,
    ) -> Path | None:
        asset = self._coerce_asset(query) if not isinstance(query, (str, Path)) else self.get_asset(query)
        if asset is None:
            return None
        data = self.read_bytes(asset, logical=logical)
        entry = self._get_entry_for_asset(asset)
        if not logical and isinstance(entry, RpfFileEntry) and entry._archive is not None:
            data = entry._archive.read_entry_standalone(entry)
        if data is None:
            return None
        target = Path(destination)
        if target.exists() and target.is_dir():
            target = target / asset.name
        elif not target.suffix:
            target.mkdir(parents=True, exist_ok=True)
            target = target / asset.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def get_archive(self, path: str | Path | AssetRecord | int | MetaHash) -> RpfArchive | None:
        asset = self._coerce_asset(path)
        if asset is not None:
            archive = self._open_archive_for_asset(asset)
            if archive is not None and asset.path.lower().endswith(".rpf"):
                split = _split_archive_asset_path(asset.path)
                if split is not None and split[1]:
                    entry = archive.find_entry(split[1])
                    if isinstance(entry, RpfFileEntry):
                        data = entry.read(logical=True)
                        try:
                            return RpfArchive.from_bytes(data, name=entry.name, crypto=self.crypto)
                        except Exception:
                            pass
                return archive
        gf = self.get_file(path)
        if gf is None:
            return None
        return gf.parsed if isinstance(gf.parsed, RpfArchive) else None

    search = search_assets
    find = find_assets
    get = get_asset
    read = read_asset
    extract = extract_asset


_KIND_DICT_TYPES: dict[str, GameFileType] = {
    "YddDict": GameFileType.YDD,
    "YdrDict": GameFileType.YDR,
    "YftDict": GameFileType.YFT,
    "YmapDict": GameFileType.YMAP,
    "YtdDict": GameFileType.YTD,
    "YtypDict": GameFileType.YTYP,
    "YbnDict": GameFileType.YBN,
    "YcdDict": GameFileType.YCD,
    "YptDict": GameFileType.YPT,
    "YndDict": GameFileType.YND,
    "YnvDict": GameFileType.YNV,
    "RelDict": GameFileType.REL,
    "YwrDict": GameFileType.YWR,
    "YvrDict": GameFileType.YVR,
    "Gxt2Dict": GameFileType.GTXD,
    "YedDict": GameFileType.YED,
}


def _make_kind_dict_property(kind: GameFileType, name: str) -> property:
    def getter(self: GameFileCache) -> Mapping[int, AssetRecord]:
        return self.get_kind_dict(kind)

    getter.__name__ = name
    return property(getter)


for _dict_name, _dict_kind in _KIND_DICT_TYPES.items():
    setattr(GameFileCache, _dict_name, _make_kind_dict_property(_dict_kind, _dict_name))


__all__ = [
    "AssetRecord",
    "GameFileCache",
    "ScanStats",
    "TextureRef",
]
