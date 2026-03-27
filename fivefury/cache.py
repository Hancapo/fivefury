from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from .crypto import GameCrypto, load_game_keys
from .gamefile import GameFile, GameFileType, guess_game_file_type
from .hashing import jenk_hash
from .metahash import MetaHash
from .resolver import HashResolver, get_hash_resolver
from .rpf import RpfArchive, RpfEntry, RpfFileEntry, _normalize_key


def _try_load_decoder(module_name: str, attribute: str) -> Any | None:
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None
    return getattr(module, attribute, None)


def _decode_payload(path: str, data: bytes) -> tuple[Any, GameFileType]:
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


def _append_index(index: dict[Any, list[int]], key: Any, value: int) -> None:
    bucket = index.get(key)
    if bucket is None:
        index[key] = [value]
        return
    if not bucket or bucket[-1] != value:
        bucket.append(value)


def _maybe_hash_name(value: str) -> tuple[int, int]:
    lower_name = value.lower()
    stem = Path(lower_name).stem
    return jenk_hash(lower_name), jenk_hash(stem)


@dataclass(slots=True)
class AssetRecord:
    id: int
    path: str
    kind: GameFileType = GameFileType.UNKNOWN
    size: int = 0
    stored_size: int = 0
    uncompressed_size: int = 0
    entry: Optional[RpfFileEntry] = None
    archive: Optional[RpfArchive] = None
    loose_path: Optional[Path] = None
    is_resource: bool = False
    is_encrypted: bool = False
    archive_encryption: int = 0
    name_hash: int = 0
    short_hash: int = 0

    @property
    def key(self) -> str:
        return _normalize_key(self.path)

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def extension(self) -> str:
        return Path(self.path).suffix.lower()

    @property
    def stem(self) -> str:
        return Path(self.path).stem

    @property
    def is_loose(self) -> bool:
        return self.loose_path is not None

    @property
    def is_archive_entry(self) -> bool:
        return self.entry is not None and self.archive is not None

    @property
    def source_path(self) -> str:
        if self.loose_path is not None:
            return str(self.loose_path)
        if self.archive is not None and self.archive.source_path:
            return self.archive.source_path
        return self.path


@dataclass
class GameFileCache:
    root: str | Path | None = None
    resolver: HashResolver | None = None
    crypto: GameCrypto | None = None
    archives: list[RpfArchive] = field(default_factory=list)
    files: dict[str, GameFile] = field(default_factory=dict)
    entries: dict[str, RpfEntry] = field(default_factory=dict)
    loose_files: dict[str, Path] = field(default_factory=dict)
    assets: dict[str, AssetRecord] = field(default_factory=dict)
    records: list[AssetRecord] = field(default_factory=list)
    scan_errors: dict[str, str] = field(default_factory=dict)
    _assets_by_name: dict[str, list[int]] = field(default_factory=dict, repr=False)
    _assets_by_stem: dict[str, list[int]] = field(default_factory=dict, repr=False)
    _assets_by_name_hash: dict[int, list[int]] = field(default_factory=dict, repr=False)
    _assets_by_short_hash: dict[int, list[int]] = field(default_factory=dict, repr=False)
    _assets_by_type: dict[GameFileType, list[int]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.resolver is None:
            self.resolver = get_hash_resolver()

    @property
    def asset_count(self) -> int:
        return len(self.records)

    def clear(self) -> None:
        self.archives.clear()
        self.files.clear()
        self.entries.clear()
        self.loose_files.clear()
        self.assets.clear()
        self.records.clear()
        self.scan_errors.clear()
        self._assets_by_name.clear()
        self._assets_by_stem.clear()
        self._assets_by_name_hash.clear()
        self._assets_by_short_hash.clear()
        self._assets_by_type.clear()

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
        exe_path: str | Path | None = None,
        magic_path: str | Path | None = None,
        aes_key: bytes | str | None = None,
        gen9: bool = False,
        cache_path: str | Path | None = None,
        use_cache: bool = True,
    ) -> None:
        if root is not None:
            self.root = root
        if self.root is None:
            raise ValueError("A root directory is required")

        root_path = Path(self.root)
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
        for rel, path in self._iter_files(root_path):
            if path.suffix.lower() == ".rpf":
                try:
                    archive = RpfArchive.from_path(path, crypto=self.crypto)
                except Exception as exc:
                    self.scan_errors[_normalize_key(rel)] = str(exc)
                    continue
                self.register_archive(archive, source_prefix=rel)
                continue
            key = _normalize_key(rel)
            self.loose_files[key] = path
            if self.resolver is not None:
                self.resolver.register_path_name(rel)
            stat = path.stat()
            self._register_asset(
                path=rel,
                kind=guess_game_file_type(rel, GameFileType.UNKNOWN),
                size=stat.st_size,
                stored_size=stat.st_size,
                uncompressed_size=stat.st_size,
                loose_path=path,
            )

    def scan_game(self, root: str | Path | None = None, **kwargs: Any) -> None:
        self.scan(root, load_keys=True, **kwargs)

    def _iter_files(self, root: Path) -> Iterator[tuple[str, Path]]:
        for base, dirnames, filenames in os.walk(root):
            dirnames.sort(key=str.lower)
            filenames.sort(key=str.lower)
            base_path = Path(base)
            for filename in filenames:
                path = base_path / filename
                yield path.relative_to(root).as_posix(), path

    def register_archive(self, archive: RpfArchive, *, source_prefix: str | None = None) -> None:
        self.archives.append(archive)
        prefix = (source_prefix or "").replace("\\", "/").strip("/")
        for entry in archive.iter_entries(include_directories=False):
            logical_path = f"{prefix}/{entry.full_path}".strip("/") if prefix else entry.full_path
            key = _normalize_key(logical_path)
            self.entries[key] = entry
            if self.resolver is not None:
                self.resolver.register_path_name(entry.full_path)
            if isinstance(entry, RpfFileEntry):
                size = entry.get_file_size()
                self._register_asset(
                    path=logical_path,
                    kind=guess_game_file_type(entry.full_path, GameFileType.UNKNOWN),
                    size=size,
                    stored_size=size,
                    uncompressed_size=getattr(entry, "file_uncompressed_size", size) or size,
                    entry=entry,
                    archive=entry._archive,
                    is_resource=entry.__class__.__name__.lower().startswith("rpfresource"),
                    is_encrypted=entry.is_encrypted,
                    archive_encryption=archive.encryption,
                )
        for child in archive.children:
            self.register_archive(child, source_prefix=prefix)

    def _register_asset(
        self,
        *,
        path: str,
        kind: GameFileType,
        size: int,
        stored_size: int,
        uncompressed_size: int,
        entry: RpfFileEntry | None = None,
        archive: RpfArchive | None = None,
        loose_path: Path | None = None,
        is_resource: bool = False,
        is_encrypted: bool = False,
        archive_encryption: int = 0,
    ) -> AssetRecord:
        name_hash, short_hash = _maybe_hash_name(Path(path).name)
        record = AssetRecord(
            id=len(self.records),
            path=path,
            kind=kind,
            size=size,
            stored_size=stored_size,
            uncompressed_size=uncompressed_size,
            entry=entry,
            archive=archive,
            loose_path=loose_path,
            is_resource=is_resource,
            is_encrypted=is_encrypted,
            archive_encryption=archive_encryption,
            name_hash=name_hash,
            short_hash=short_hash,
        )
        self.records.append(record)
        self.assets[record.key] = record
        _append_index(self._assets_by_name, record.name.lower(), record.id)
        _append_index(self._assets_by_stem, record.stem.lower(), record.id)
        _append_index(self._assets_by_name_hash, record.name_hash, record.id)
        _append_index(self._assets_by_short_hash, record.short_hash, record.id)
        _append_index(self._assets_by_type, record.kind, record.id)
        return record

    def _iter_ids(self, ids: list[int], *, kind: GameFileType | str | int | None = None) -> Iterator[AssetRecord]:
        kind_value = _coerce_kind(kind)
        seen: set[int] = set()
        for asset_id in ids:
            if asset_id in seen or asset_id < 0 or asset_id >= len(self.records):
                continue
            asset = self.records[asset_id]
            if kind_value is not None and asset.kind is not kind_value:
                continue
            seen.add(asset_id)
            yield asset

    def iter_assets(self, kind: GameFileType | str | int | None = None) -> Iterator[AssetRecord]:
        kind_value = _coerce_kind(kind)
        if kind_value is None:
            yield from self.records
            return
        for asset_id in self._assets_by_type.get(kind_value, []):
            yield self.records[asset_id]

    def iter_paths(self, kind: GameFileType | str | int | None = None) -> Iterator[str]:
        for asset in self.iter_assets(kind=kind):
            yield asset.path

    def find_path(self, path: str | Path, *, kind: GameFileType | str | int | None = None) -> AssetRecord | None:
        asset = self.assets.get(_normalize_key(path))
        if asset is None:
            return None
        kind_value = _coerce_kind(kind)
        if kind_value is not None and asset.kind is not kind_value:
            return None
        return asset

    def find_hash(self, value: int | MetaHash | str, *, kind: GameFileType | str | int | None = None, limit: int | None = None) -> list[AssetRecord]:
        if isinstance(value, str):
            name_hash = jenk_hash(Path(value).name.lower())
            short_hash = jenk_hash(Path(value).stem.lower())
        else:
            name_hash = int(value)
            short_hash = int(value)
        ids = [*self._assets_by_short_hash.get(short_hash, []), *self._assets_by_name_hash.get(name_hash, [])]
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
        text = Path(str(name)).name
        if not text:
            return []
        if exact:
            ids = [*self._assets_by_name.get(text.lower(), []), *self._assets_by_stem.get(Path(text).stem.lower(), [])]
            result = list(self._iter_ids(ids, kind=kind))
            if not result:
                result = self.find_hash(text, kind=kind, limit=limit)
            return result[:limit] if limit is not None else result
        lower = text.lower()
        result: list[AssetRecord] = []
        for asset in self.iter_assets(kind=kind):
            if lower in asset.stem.lower() or lower in asset.name.lower() or lower in asset.path.lower():
                result.append(asset)
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

    def get_entry(self, path: str | Path | AssetRecord) -> Optional[RpfEntry]:
        key = path.key if isinstance(path, AssetRecord) else _normalize_key(path)
        return self.entries.get(key)

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
            return cached

        entry = self.entries.get(asset.key)
        if entry is not None:
            if entry._archive is None:
                raise ValueError(f"Entry is detached from archive: {asset.path}")
            stored = entry.read(logical=False)
            logical = entry.read(logical=True)
            parsed, kind = _decode_payload(asset.path, logical)
            game_file = GameFile(
                path=asset.path,
                kind=kind,
                entry=entry if isinstance(entry, RpfFileEntry) else None,
                archive=entry._archive,
                raw=stored,
                parsed=parsed,
                loaded=True,
            )
            self.files[asset.key] = game_file
            return game_file

        loose = self.loose_files.get(asset.key)
        if loose is None:
            return None
        data = loose.read_bytes()
        parsed, kind = _decode_payload(asset.path, data)
        game_file = GameFile(path=asset.path, kind=kind, raw=data, parsed=parsed, loaded=True)
        self.files[asset.key] = game_file
        return game_file

    def load_asset(self, query: str | Path | int | MetaHash | AssetRecord) -> GameFile | None:
        return self.get_file(query)

    def read_bytes(self, query: str | Path | AssetRecord | int | MetaHash, *, logical: bool = True) -> bytes | None:
        asset = self._coerce_asset(query)
        if asset is None:
            return None
        if asset.entry is not None and asset.archive is not None:
            return asset.entry.read(logical=logical)
        if asset.loose_path is not None:
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
        logical: bool = True,
    ) -> Path | None:
        asset = self._coerce_asset(query) if not isinstance(query, (str, Path)) else self.get_asset(query)
        if asset is None:
            return None
        data = self.read_bytes(asset, logical=logical)
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
        gf = self.get_file(path)
        if gf is None:
            return None
        return gf.parsed if isinstance(gf.parsed, RpfArchive) else None

    search = search_assets
    find = find_assets
    get = get_asset
    read = read_asset
    extract = extract_asset


__all__ = [
    "AssetRecord",
    "GameFileCache",
]
