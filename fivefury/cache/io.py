from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from ..authoring.diagnostics import ValidationReport
from ..awc.io import read_awc
from ..cdr.reader import read_cdr
from ..cut.pso import read_cut
from ..gamefile import GameFile, GameFileType, guess_game_file_type
from ..gta5_cache import read_gta5_cache_y
from ..gtxd import read_gtxd
from ..gxt2 import read_gxt2
from ..hashing import _get_lut
from ..heightmap import read_heightmap
from ..metahash import MetaHash
from ..rel.io import read_rel
from ..resource import parse_rsc7
from ..rpf import (
    RpfArchive,
    RpfEntry,
    RpfFileEntry,
)
from ..rpf.utils import _decompress_deflate, _normalize_key
from ..vehiclemeta.resource import read_vehicle_meta
from ..water.io import read_water
from ..ybn import read_ybn
from ..ycd.reader import read_ycd
from ..ydd.reader import read_ydd
from ..ydr.reader import read_ydr
from ..yed.expression_sets import read_ped_expression_sets
from ..yed.reader import read_yed
from ..yft.reader import read_yft
from ..ynd.reader import read_ynd
from ..ynv.reader import read_ynv
from ..ytd import read_ytd
from .kinds import coerce_game_file_kind
from .paths import split_archive_asset_path as _split_archive_asset_path
from .views import AssetRecord

_STANDALONE_RESOURCE_EXTENSIONS = frozenset({
    ".ydr", ".cdr", ".ydd", ".yft", ".ytd", ".ycd", ".yed", ".ybn", ".ynd", ".ynv",
})
try:
    from .._native import RpfReader
except ImportError as exc:
    raise ImportError("fivefury native backend is required; rebuild/install the wheel with the bundled extension") from exc


def _decode_dynamic(data: bytes, *, module_name: str, attribute: str, kind: GameFileType) -> tuple[Any, GameFileType]:
    decoder = getattr(importlib.import_module(module_name), attribute)
    return decoder(data), kind


def decode_game_file_payload(
    path: str,
    data: bytes,
    *,
    raw: bytes | None = None,
    diagnostics: ValidationReport | None = None,
) -> tuple[Any, GameFileType]:
    try:
        return _decode_game_file_payload(path, data, raw=raw)
    except Exception as exc:  # noqa: BLE001 - decoder failures become structured diagnostics.
        report = ValidationReport() if diagnostics is None else diagnostics
        report.issue(
            "asset.decode.failed", f"{type(exc).__name__}: {exc}", asset=path, path="parsed"
        )
        if diagnostics is None:
            report.raise_for_errors()
        return None, guess_game_file_type(path)


def _decode_game_file_payload(
    path: str,
    data: bytes,
    *,
    raw: bytes | None = None,
) -> tuple[Any, GameFileType]:
    ext = Path(path).suffix.lower()
    name = Path(path).name.lower()
    match name:
        case "gta5_cache_y.dat":
            return read_gta5_cache_y(data), GameFileType.GTA5_CACHE
        case value if value.startswith("heightmap") and value.endswith(".dat"):
            return read_heightmap(data), GameFileType.HEIGHTMAP
        case "water.xml":
            return read_water(data), GameFileType.WATER
        case "expression_sets.xml":
            return read_ped_expression_sets(data, source_path=path), GameFileType.EXPRESSION_SETS
        case "gtxd.meta":
            return read_gtxd(data), GameFileType.GTXD
    vehicle_meta_type = guess_game_file_type(path)
    if vehicle_meta_type is GameFileType.REL:
        return read_rel(data, path=path), GameFileType.REL
    if vehicle_meta_type in {
        GameFileType.VEHICLES,
        GameFileType.HANDLING,
        GameFileType.CAR_COLS,
        GameFileType.CAR_MOD_COLS,
        GameFileType.CAR_VARIATIONS,
    }:
        return read_vehicle_meta(data, source=path), vehicle_meta_type
    if ext == ".ymap":
        return _decode_dynamic(data, module_name="fivefury.ymap", attribute="read_ymap", kind=GameFileType.YMAP)
    if ext == ".ymf":
        return _decode_dynamic(data, module_name="fivefury.ymf", attribute="read_ymf", kind=GameFileType.YMF)
    if ext == ".ymt":
        return _decode_dynamic(data, module_name="fivefury.ymt", attribute="read_ymt", kind=GameFileType.YMT)
    if ext == ".ytyp":
        return _decode_dynamic(data, module_name="fivefury.ytyp", attribute="read_ytyp", kind=GameFileType.YTYP)

    source = raw if raw is not None else data
    resource_decoders = {
        ".ydr": (GameFileType.YDR, lambda payload: read_ydr(payload, path=path)),
        ".cdr": (GameFileType.CDR, lambda payload: read_cdr(payload, path=path)),
        ".ydd": (GameFileType.YDD, lambda payload: read_ydd(payload, path=path)),
        ".yft": (GameFileType.YFT, lambda payload: read_yft(payload, path=path)),
        ".ytd": (GameFileType.YTD, read_ytd),
        ".ycd": (GameFileType.YCD, lambda payload: read_ycd(payload, path=path)),
        ".yed": (GameFileType.YED, lambda payload: read_yed(payload, path=path)),
        ".ybn": (GameFileType.YBN, lambda payload: read_ybn(payload, path=path)),
        ".ynd": (GameFileType.YND, lambda payload: read_ynd(payload, path=path)),
        ".ynv": (GameFileType.YNV, lambda payload: read_ynv(payload, path=path)),
    }
    if ext in resource_decoders:
        kind, decoder = resource_decoders[ext]
        return decoder(source), kind

    direct_decoders = {
        ".gxt2": (GameFileType.GXT2, lambda payload: read_gxt2(payload, path=path)),
        ".awc": (GameFileType.AWC, lambda payload: read_awc(payload, path=path)),
        ".rel": (GameFileType.REL, lambda payload: read_rel(payload, path=path)),
        ".rpf": (GameFileType.RPF, RpfArchive.from_bytes),
        ".cut": (GameFileType.CUT, read_cut),
    }
    if ext in direct_decoders:
        kind, decoder = direct_decoders[ext]
        return decoder(data), kind
    return data, guess_game_file_type(path, GameFileType.UNKNOWN)


class GameFileCacheIOMixin:
    def iter_files(self):
        yield from self.files.values()

    def _remember_file(self, key: str, game_file: GameFile) -> None:
        with self._runtime_cache_lock:
            limit = max(0, int(self.max_loaded_files))
            if limit <= 0:
                return
            self.files.pop(key, None)
            self.files[key] = game_file
            while len(self.files) > limit:
                evicted_key, _ = self.files.popitem(last=False)
                self._log(f"evict file {evicted_key}")

    def _native_crypto_context(self) -> Any | None:
        if self.crypto is None:
            return None
        return self.crypto.native_context()

    def _native_archive_reader(self, asset: AssetRecord) -> RpfReader | None:
        archive_rel = asset.archive_rel
        if archive_rel is None or asset.entry_path is None or self.root is None:
            return None
        archive_path = Path(self.root) / archive_rel
        if not archive_path.is_file():
            return None
        crypto = self._native_crypto_context()
        with self._runtime_cache_lock:
            previous = self._native_readers.pop(archive_rel, None)
            reader = (previous[1] if previous is not None and previous[0] is crypto
                      else RpfReader(archive_path, _get_lut(), crypto))
            limit = max(0, int(self.max_open_archives))
            if limit:
                self._native_readers[archive_rel] = (crypto, reader)
            while len(self._native_readers) > limit:
                self._native_readers.popitem(last=False)
            return reader

    def _read_archive_asset_native(self, asset: AssetRecord, *, standalone: bool) -> bytes | None:
        try:
            reader = self._native_archive_reader(asset)
            return None if reader is None else reader.read(asset.entry_path, standalone=standalone)
        except (OSError, RuntimeError, ValueError):
            return None

    def _read_archive_asset_native_variants(self, asset: AssetRecord) -> tuple[bytes, bytes] | None:
        try:
            reader = self._native_archive_reader(asset)
            return None if reader is None else reader.read_variants(asset.entry_path)
        except (OSError, RuntimeError, ValueError):
            return None

    def _logical_archive_bytes_from_standalone(self, asset: AssetRecord, standalone: bytes) -> bytes:
        if asset.is_resource:
            try:
                return parse_rsc7(standalone)[1]
            except (ValueError, RuntimeError):
                return standalone
        if asset.uncompressed_size != asset.stored_size:
            try:
                return _decompress_deflate(standalone)
            except ValueError:
                return standalone
        return standalone

    def _open_archive_for_asset(self, asset: AssetRecord) -> RpfArchive | None:
        archive_rel = asset.archive_rel
        if archive_rel is None or self.root is None:
            return None
        key = _normalize_key(archive_rel)
        with self._runtime_cache_lock:
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

    def get_entry(self, path: str | Path | AssetRecord) -> RpfEntry | None:
        asset = path if isinstance(path, AssetRecord) else self.find_path(path)
        if asset is None:
            return None
        return self._get_entry_for_asset(asset)

    def _coerce_asset(self, value: AssetRecord | str | Path | int | MetaHash, *, kind: GameFileType | str | int | None = None) -> AssetRecord | None:
        if isinstance(value, AssetRecord):
            if kind is None:
                return value
            requested_kind = coerce_game_file_kind(kind)
            if requested_kind is None:
                return None
            if value.kind is requested_kind:
                return value
            return self.get_asset(value.short_hash, kind=requested_kind)
        return self.get_asset(value, kind=kind)

    def get_file(self, path: str | Path | AssetRecord | int | MetaHash) -> GameFile | None:
        asset = self._coerce_asset(path)
        if asset is None:
            return None
        with self._runtime_cache_lock:
            cached = self.files.get(asset.key)
            if cached is not None:
                self.files.move_to_end(asset.key)
                self._log(f"file cache hit {asset.path}")
                return cached

        native_variants = self._read_archive_asset_native_variants(asset)
        if native_variants is not None:
            stored_native, standalone_native = native_variants
            self._log(f"read file {asset.path}")
            standalone_resource = asset.extension in _STANDALONE_RESOURCE_EXTENSIONS
            logical_native = (standalone_native if standalone_resource else
                              self._logical_archive_bytes_from_standalone(asset, standalone_native))
            game_file = GameFile.from_bytes(logical_native, path=asset.path)
            entry = asset.entry if isinstance(asset.entry, RpfFileEntry) else None
            archive = asset.archive if isinstance(asset.archive, RpfArchive) else None
            game_file.entry = entry
            game_file.archive = archive
            game_file.raw = stored_native
            self._remember_file(asset.key, game_file)
            return game_file

        entry = self._get_entry_for_asset(asset)
        if entry is not None:
            if entry._archive is None:
                raise ValueError(f"Entry is detached from archive: {asset.path}")
            self._log(f"read file {asset.path}")
            stored = entry.read(logical=False)
            if asset.extension in _STANDALONE_RESOURCE_EXTENSIONS:
                logical = entry._archive.read_entry_standalone(entry)
            else:
                logical = entry.read(logical=True)
            game_file = GameFile.from_bytes(logical, path=asset.path)
            game_file.entry = entry if isinstance(entry, RpfFileEntry) else None
            game_file.archive = entry._archive
            game_file.raw = stored
            self._remember_file(asset.key, game_file)
            return game_file

        loose = asset.loose_path
        if loose is None:
            return None
        self._log(f"read file {asset.path}")
        data = loose.read_bytes()
        game_file = GameFile.from_bytes(data, path=asset.path)
        self._remember_file(asset.key, game_file)
        return game_file

    def load_asset(self, query: str | Path | int | MetaHash | AssetRecord) -> GameFile | None:
        return self.get_file(query)

    def read_bytes(self, query: str | Path | AssetRecord | int | MetaHash, *, logical: bool = True) -> bytes | None:
        asset = self._coerce_asset(query)
        if asset is None:
            return None
        cached = self._cached_payload(asset.id, logical)
        if cached is not None:
            return cached
        native = self._read_archive_asset_native(asset, standalone=logical)
        if native is not None:
            self._log(f"read bytes {asset.path} logical={logical}")
            if logical:
                native = self._logical_archive_bytes_from_standalone(asset, native)
            return self._remember_payload(asset.id, logical, native)
        entry = self._get_entry_for_asset(asset)
        if isinstance(entry, RpfFileEntry):
            self._log(f"read bytes {asset.path} logical={logical}")
            return self._remember_payload(asset.id, logical, entry.read(logical=logical))
        if asset.loose_path is not None:
            self._log(f"read bytes {asset.path} logical={logical}")
            return self._remember_payload(asset.id, logical, asset.loose_path.read_bytes())
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
        if logical:
            data = self.read_bytes(asset, logical=True)
        else:
            data = self._read_archive_asset_native(asset, standalone=True)
            if data is None:
                data = self.read_bytes(asset, logical=False)
                entry = self._get_entry_for_asset(asset)
                if isinstance(entry, RpfFileEntry) and entry._archive is not None:
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
            if asset.path.lower().endswith(".rpf"):
                nested_bytes = self._read_archive_asset_native(asset, standalone=True)
                if nested_bytes is not None:
                    try:
                        return RpfArchive.from_bytes(nested_bytes, name=asset.name, crypto=self.crypto)
                    except (OSError, ValueError, RuntimeError) as exc:
                        self._log(f"cannot decode archive {asset.path}: {exc}")
            archive = self._open_archive_for_asset(asset)
            if archive is not None and asset.path.lower().endswith(".rpf"):
                split = _split_archive_asset_path(asset.path)
                if split is not None and split[1]:
                    entry = archive.find_entry(split[1])
                    if isinstance(entry, RpfFileEntry):
                        data = entry.read(logical=True)
                        try:
                            return RpfArchive.from_bytes(data, name=entry.name, crypto=self.crypto)
                        except (OSError, ValueError, RuntimeError) as exc:
                            self._log(f"cannot decode nested archive {asset.path}: {exc}")
                return archive
        gf = self.get_file(path)
        if gf is None:
            return None
        return gf.parsed if isinstance(gf.parsed, RpfArchive) else None
