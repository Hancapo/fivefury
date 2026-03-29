from __future__ import annotations

import gc
import hashlib
import os
import pickle
import re
import time
from pathlib import Path
from typing import Any, Iterator, Sequence

from .._native import CompactIndex, NativeCryptoContext, scan_rpf_batch_into_index
from ..crypto import GameCrypto, load_game_keys
from ..gamefile import GameFileType, guess_game_file_type
from ..hashing import _get_lut
from ..rpf import RpfArchive, RpfFileEntry, _normalize_key

_SCAN_INDEX_VERSION = 4
_SCAN_GC_INTERVAL = 8

_FLAG_LOOSE = 1

_SKIP_AUDIO = 1 << 0
_SKIP_VEHICLES = 1 << 1
_SKIP_PEDS = 1 << 2


def _asset_category_mask(path: str | Path) -> int:
    normalized = _normalize_key(path)
    name = normalized.rsplit("/", 1)[-1]
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
        or "/vehicles.rpf/" in normalized
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
        or "/peds.rpf/" in normalized
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


def _default_index_cache_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else (Path.home() / ".cache")
    return base / "fivefury" / "scan-index"


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


class GameFileCacheScanMixin:
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
    ):
        from .views import ScanStats

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
            should_load_keys = (
                (root_path / "gta5.exe").is_file()
                or (root_path / "gta5_enhanced.exe").is_file()
                or exe_path is not None
                or aes_key is not None
            )
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
        from . import _scan_archive_sources_batch as scan_archive_sources_batch

        if archive_rels:
            archive_sources = [(root_path / rel, rel) for rel in archive_rels]
            for rel, _payload_count, error in scan_archive_sources_batch(
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


__all__ = ["GameFileCacheScanMixin"]
