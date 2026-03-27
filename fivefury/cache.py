from __future__ import annotations

import hashlib
import importlib
import os
import pickle
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from .crypto import GameCrypto, load_game_keys
from .gamefile import GameFile, GameFileType, guess_game_file_type
from .hashing import jenk_hash
from .metahash import MetaHash
from .resolver import HashResolver, get_hash_resolver
from .rpf import RpfArchive, RpfEntry, RpfFileEntry, _normalize_key

_SCAN_INDEX_VERSION = 1
_WORKER_STATE = threading.local()


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


def _get_worker_crypto(crypto: GameCrypto | None) -> GameCrypto | None:
    if crypto is None:
        return None
    cached_source = getattr(_WORKER_STATE, "crypto_source", None)
    cached_crypto = getattr(_WORKER_STATE, "crypto_instance", None)
    if cached_source is crypto and cached_crypto is not None:
        return cached_crypto
    worker_crypto = crypto.clone_for_worker()
    _WORKER_STATE.crypto_source = crypto
    _WORKER_STATE.crypto_instance = worker_crypto
    return worker_crypto


def _collect_archive_payloads(archive: RpfArchive, source_prefix: str) -> list[tuple[Any, ...]]:
    prefix = source_prefix.replace("\\", "/").strip("/")
    records: list[tuple[Any, ...]] = []
    stack = [archive]
    while stack:
        current = stack.pop()
        for entry in current.iter_entries(include_directories=False):
            if not isinstance(entry, RpfFileEntry):
                continue
            logical_path = f"{prefix}/{entry.full_path}".strip("/") if prefix else entry.full_path
            size = entry.get_file_size()
            name_hash, short_hash = _maybe_hash_name(Path(logical_path).name)
            records.append(
                (
                    logical_path,
                    int(guess_game_file_type(entry.full_path, GameFileType.UNKNOWN)),
                    int(size),
                    int(size),
                    int(getattr(entry, "file_uncompressed_size", size) or size),
                    False,
                    isinstance(entry, RpfFileEntry) and entry.__class__.__name__.lower().startswith("rpfresource"),
                    bool(entry.is_encrypted),
                    int(current.encryption),
                    int(name_hash),
                    int(short_hash),
                )
            )
        stack.extend(reversed(current.children))
    return records


def _scan_archive_source(path: str | Path, source_prefix: str, crypto: GameCrypto | None) -> tuple[str, list[tuple[Any, ...]]]:
    archive = RpfArchive.from_path(path, crypto=_get_worker_crypto(crypto))
    return source_prefix, _collect_archive_payloads(archive, source_prefix)


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


@dataclass
class GameFileCache:
    root: str | Path | None = None
    resolver: HashResolver | None = None
    crypto: GameCrypto | None = None
    dlc_level: str | int | None = None
    exclude_folders: str | Path | list[str] | tuple[str, ...] | None = None
    use_index_cache: bool = True
    index_cache_path: str | Path | None = None
    scan_workers: int | None = None
    max_open_archives: int = 8
    archives: list[RpfArchive] = field(default_factory=list)
    files: dict[str, GameFile] = field(default_factory=dict)
    entries: dict[str, RpfEntry] = field(default_factory=dict)
    loose_files: dict[str, Path] = field(default_factory=dict)
    assets: dict[str, AssetRecord] = field(default_factory=dict)
    records: list[AssetRecord] = field(default_factory=list)
    scan_errors: dict[str, str] = field(default_factory=dict)
    dlc_names: list[str] = field(default_factory=list)
    active_dlc_names: list[str] = field(default_factory=list)
    last_scan: ScanStats | None = None
    _assets_by_name: dict[str, list[int]] = field(default_factory=dict, repr=False)
    _assets_by_stem: dict[str, list[int]] = field(default_factory=dict, repr=False)
    _assets_by_name_hash: dict[int, list[int]] = field(default_factory=dict, repr=False)
    _assets_by_short_hash: dict[int, list[int]] = field(default_factory=dict, repr=False)
    _assets_by_type: dict[GameFileType, list[int]] = field(default_factory=dict, repr=False)
    _exclude_prefixes: tuple[str, ...] = field(default_factory=tuple, init=False, repr=False)
    _active_dlc_filter: set[str] | None = field(default=None, init=False, repr=False)
    _archive_lookup: OrderedDict[str, RpfArchive] = field(default_factory=OrderedDict, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.resolver is None:
            self.resolver = get_hash_resolver()
        self._exclude_prefixes = _coerce_folder_prefixes(self.exclude_folders)

    @property
    def asset_count(self) -> int:
        return len(self.records)

    @property
    def open_archive_count(self) -> int:
        return len(self._archive_lookup)

    def clear(self) -> None:
        self.archives.clear()
        self.files.clear()
        self.entries.clear()
        self.loose_files.clear()
        self.assets.clear()
        self.records.clear()
        self.scan_errors.clear()
        self.dlc_names.clear()
        self.active_dlc_names.clear()
        self._active_dlc_filter = None
        self._assets_by_name.clear()
        self._assets_by_stem.clear()
        self._assets_by_name_hash.clear()
        self._assets_by_short_hash.clear()
        self._assets_by_type.clear()
        self._archive_lookup.clear()

    def clear_runtime_cache(self, *, loaded_files: bool = False) -> None:
        self.archives.clear()
        self.entries.clear()
        self._archive_lookup.clear()
        if loaded_files:
            self.files.clear()

    def set_dlc_level(self, value: str | int | None) -> str | int | None:
        self.dlc_level = value
        return self.dlc_level

    def set_exclude_folders(self, value: str | Path | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
        self.exclude_folders = value
        self._exclude_prefixes = _coerce_folder_prefixes(value)
        return self._exclude_prefixes

    def get_index_cache_path(self) -> Path:
        if self.index_cache_path is not None:
            return Path(self.index_cache_path)
        root_text = str(Path(self.root or ".").resolve()).lower()
        config_text = f"{self._normalized_dlc_level()}|{';'.join(self._exclude_prefixes)}"
        digest = hashlib.sha1(f"{root_text}|{config_text}".encode("utf-8")).hexdigest()
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
            stat = path.stat()
            manifest.append((rel, stat.st_size, stat.st_mtime_ns))
        return manifest

    def _serialize_record(self, record: AssetRecord, root: Path) -> tuple[Any, ...]:
        is_loose = record.loose_path is not None and _split_archive_asset_path(record.path) is None
        return (
            record.path,
            int(record.kind),
            int(record.size),
            int(record.stored_size),
            int(record.uncompressed_size),
            bool(is_loose),
            bool(record.is_resource),
            bool(record.is_encrypted),
            int(record.archive_encryption),
            int(record.name_hash),
            int(record.short_hash),
        )

    def _deserialize_record(self, payload: tuple[Any, ...], root: Path) -> AssetRecord:
        (
            path,
            kind_value,
            size,
            stored_size,
            uncompressed_size,
            is_loose,
            is_resource,
            is_encrypted,
            archive_encryption,
            name_hash,
            short_hash,
        ) = payload
        return AssetRecord(
            id=0,
            path=str(path),
            kind=GameFileType(int(kind_value)),
            size=int(size),
            stored_size=int(stored_size),
            uncompressed_size=int(uncompressed_size),
            loose_path=(root / str(path)) if bool(is_loose) else None,
            is_resource=bool(is_resource),
            is_encrypted=bool(is_encrypted),
            archive_encryption=int(archive_encryption),
            name_hash=int(name_hash),
            short_hash=int(short_hash),
        )

    def _load_index_payload(self, path: Path) -> dict[str, Any] | None:
        try:
            return pickle.loads(path.read_bytes())
        except Exception:
            return None

    def _save_index_payload(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))

    def _restore_records(self, records: list[AssetRecord]) -> None:
        self.records = []
        self.assets.clear()
        self.loose_files.clear()
        self._assets_by_name.clear()
        self._assets_by_stem.clear()
        self._assets_by_name_hash.clear()
        self._assets_by_short_hash.clear()
        self._assets_by_type.clear()
        for record in records:
            record.id = len(self.records)
            self.records.append(record)
            self.assets[record.key] = record
            if record.loose_path is not None:
                self.loose_files[record.key] = record.loose_path
            _append_index(self._assets_by_name, record.name.lower(), record.id)
            _append_index(self._assets_by_stem, record.stem.lower(), record.id)
            _append_index(self._assets_by_name_hash, record.name_hash, record.id)
            _append_index(self._assets_by_short_hash, record.short_hash, record.id)
            _append_index(self._assets_by_type, record.kind, record.id)

    def _load_index_cache(self, root: Path, manifest: list[tuple[str, int, int]], cache_path: Path) -> bool:
        payload = self._load_index_payload(cache_path)
        if not isinstance(payload, dict):
            return False
        config = payload.get("config")
        expected_config = {
            "root": str(root.resolve()).lower(),
            "dlc_level": self._normalized_dlc_level(),
            "exclude_folders": list(self._exclude_prefixes),
        }
        if payload.get("version") != _SCAN_INDEX_VERSION or config != expected_config:
            return False
        if payload.get("manifest") != manifest:
            return False
        cached_records = payload.get("records")
        if not isinstance(cached_records, list):
            return False
        self.scan_errors = dict(payload.get("scan_errors") or {})
        self.dlc_names = list(payload.get("dlc_names") or self.dlc_names)
        self.active_dlc_names = self._resolve_active_dlc_names()
        records = [self._deserialize_record(item, root) for item in cached_records]
        self._restore_records(records)
        if self.resolver is not None:
            for asset in self.records:
                self.resolver.register_path_name(asset.path)
        return True

    def _save_index_cache(self, root: Path, manifest: list[tuple[str, int, int]], cache_path: Path) -> None:
        payload = {
            "version": _SCAN_INDEX_VERSION,
            "config": {
                "root": str(root.resolve()).lower(),
                "dlc_level": self._normalized_dlc_level(),
                "exclude_folders": list(self._exclude_prefixes),
            },
            "manifest": manifest,
            "records": [self._serialize_record(record, root) for record in self.records],
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
        use_index_cache: bool | None = None,
        refresh_index_cache: bool = False,
        index_cache_path: str | Path | None = None,
        scan_workers: int | None = None,
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
        if index_cache_path is not None:
            self.index_cache_path = index_cache_path
        if scan_workers is not None:
            self.scan_workers = scan_workers
        cache_enabled = self.use_index_cache if use_index_cache is None else bool(use_index_cache)

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
        self.dlc_names = self._discover_dlc_names(root_path)
        self.active_dlc_names = self._resolve_active_dlc_names()
        self._active_dlc_filter = set(self.active_dlc_names) if self._should_restrict_dlc() else None
        manifest = self._build_source_manifest(root_path)
        rpf_count = sum(1 for rel, _, _ in manifest if rel.lower().endswith(".rpf"))
        loose_count = len(manifest) - rpf_count
        index_path = self.get_index_cache_path()
        if cache_enabled and not refresh_index_cache and self._load_index_cache(root_path, manifest, index_path):
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
        archive_futures: dict[str, Future[tuple[str, list[tuple[Any, ...]]]]] = {}
        executor: ThreadPoolExecutor | None = None
        try:
            if archive_workers > 1:
                executor = ThreadPoolExecutor(max_workers=archive_workers, thread_name_prefix="fivefury-scan")
                for rel, _, _ in manifest:
                    path = root_path / rel
                    if path.suffix.lower() == ".rpf":
                        archive_futures[rel] = executor.submit(_scan_archive_source, path, rel, self.crypto)

            for rel, _, _ in manifest:
                path = root_path / rel
                if path.suffix.lower() == ".rpf":
                    try:
                        if executor is None:
                            _, payloads = _scan_archive_source(path, rel, self.crypto)
                        else:
                            _, payloads = archive_futures[rel].result()
                    except Exception as exc:
                        self.scan_errors[_normalize_key(rel)] = str(exc)
                        continue
                    for payload in payloads:
                        self._register_asset(
                            path=str(payload[0]),
                            kind=GameFileType(int(payload[1])),
                            size=int(payload[2]),
                            stored_size=int(payload[3]),
                            uncompressed_size=int(payload[4]),
                            is_resource=bool(payload[6]),
                            is_encrypted=bool(payload[7]),
                            archive_encryption=int(payload[8]),
                            name_hash=int(payload[9]),
                            short_hash=int(payload[10]),
                        )
                    continue
                key = _normalize_key(rel)
                self.loose_files[key] = path
                stat = path.stat()
                self._register_asset(
                    path=rel,
                    kind=guess_game_file_type(rel, GameFileType.UNKNOWN),
                    size=stat.st_size,
                    stored_size=stat.st_size,
                    uncompressed_size=stat.st_size,
                    loose_path=path,
                )
        finally:
            if executor is not None:
                executor.shutdown(wait=True)
        if self.resolver is not None:
            for asset in self.records:
                self.resolver.register_path_name(asset.path)
        saved_index_cache = False
        if cache_enabled:
            self._save_index_cache(root_path, manifest, index_path)
            saved_index_cache = True
        self.last_scan = self._make_scan_stats(
            started_at=started_at,
            used_index_cache=False,
            saved_index_cache=saved_index_cache,
            source_count=len(manifest),
            rpf_count=rpf_count,
            loose_count=loose_count,
            archive_workers=archive_workers,
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
        stored_size: int,
        uncompressed_size: int,
        entry: RpfFileEntry | None = None,
        archive: RpfArchive | None = None,
        loose_path: Path | None = None,
        is_resource: bool = False,
        is_encrypted: bool = False,
        archive_encryption: int = 0,
        name_hash: int | None = None,
        short_hash: int | None = None,
    ) -> AssetRecord:
        if name_hash is None or short_hash is None:
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

    def _open_archive_for_asset(self, asset: AssetRecord) -> RpfArchive | None:
        archive_rel = asset.archive_rel
        if archive_rel is None or self.root is None:
            return None
        key = _normalize_key(archive_rel)
        cached = self._archive_lookup.get(key)
        if cached is not None:
            self._archive_lookup.move_to_end(key)
            return cached
        archive_path = Path(self.root) / archive_rel
        if not archive_path.is_file():
            return None
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
            return cached

        entry = self._get_entry_for_asset(asset)
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

        loose = self.loose_files.get(asset.key) or asset.loose_path
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
        entry = self._get_entry_for_asset(asset)
        if isinstance(entry, RpfFileEntry):
            return entry.read(logical=logical)
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


__all__ = [
    "AssetRecord",
    "GameFileCache",
    "ScanStats",
]
