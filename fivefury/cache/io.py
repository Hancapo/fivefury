from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Optional

from .paths import split_archive_asset_path as _split_archive_asset_path
from .views import AssetRecord
from ..cut import read_cut, read_cutxml
from ..gamefile import GameFile, GameFileType, guess_game_file_type
from ..hashing import _get_lut
from ..metahash import MetaHash
from ..resource import parse_rsc7
from ..rpf import RpfArchive, RpfEntry, RpfFileEntry, _decompress_deflate, _normalize_key
from ..ycd import read_ycd
from ..ybn import read_ybn
from ..ydd import read_ydd
from ..ydr import read_ydr
from ..ynd import read_ynd
from ..ynv import read_ynv
from ..ytd import read_ytd

try:
    from .._native import read_rpf_entry, read_rpf_entry_variants
except ImportError as exc:
    raise ImportError("fivefury native backend is required; rebuild/install the wheel with the bundled extension") from exc


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
    if ext == ".ydr":
        source = raw if raw is not None else data
        try:
            return read_ydr(source, path=path), GameFileType.YDR
        except Exception:
            return source, GameFileType.YDR
    if ext == ".ydd":
        source = raw if raw is not None else data
        try:
            return read_ydd(source, path=path), GameFileType.YDD
        except Exception:
            return source, GameFileType.YDD
    if ext == ".ytd":
        source = raw if raw is not None else data
        try:
            return read_ytd(source), GameFileType.YTD
        except Exception:
            return source, GameFileType.YTD
    if ext == ".ycd":
        source = raw if raw is not None else data
        try:
            return read_ycd(source, path=path), GameFileType.YCD
        except Exception:
            return source, GameFileType.YCD
    if ext == ".ybn":
        source = raw if raw is not None else data
        try:
            return read_ybn(source, path=path), GameFileType.YBN
        except Exception:
            return source, GameFileType.YBN
    if ext == ".ynd":
        source = raw if raw is not None else data
        try:
            return read_ynd(source, path=path), GameFileType.YND
        except Exception:
            return source, GameFileType.YND
    if ext == ".ynv":
        source = raw if raw is not None else data
        try:
            return read_ynv(source, path=path), GameFileType.YNV
        except Exception:
            return source, GameFileType.YNV
    if ext == ".cut":
        source = raw if raw is not None else data
        try:
            return read_cut(source), GameFileType.CUT
        except Exception:
            return source, GameFileType.CUT
    if ext == ".cutxml":
        try:
            return read_cutxml(data.decode("utf-8")), GameFileType.CUT
        except Exception:
            return data, GameFileType.CUT
    if ext == ".rpf":
        try:
            return RpfArchive.from_bytes(data), GameFileType.RPF
        except Exception:
            return data, GameFileType.RPF
    return data, guess_game_file_type(path, GameFileType.UNKNOWN)

class GameFileCacheIOMixin:
    def iter_files(self):
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

    def _native_crypto_context(self) -> Any | None:
        if self.crypto is None:
            return None
        try:
            return self.crypto.native_context()
        except Exception:
            return None

    def _read_archive_asset_native(self, asset: AssetRecord, *, standalone: bool) -> bytes | None:
        archive_rel = asset.archive_rel
        entry_path = asset.entry_path
        if archive_rel is None or entry_path is None or self.root is None:
            return None
        archive_path = Path(self.root) / archive_rel
        if not archive_path.is_file():
            return None
        try:
            return read_rpf_entry(
                archive_path,
                entry_path,
                _get_lut(),
                self._native_crypto_context(),
                standalone=standalone,
            )
        except Exception:
            return None

    def _read_archive_asset_native_variants(self, asset: AssetRecord) -> tuple[bytes, bytes] | None:
        archive_rel = asset.archive_rel
        entry_path = asset.entry_path
        if archive_rel is None or entry_path is None or self.root is None:
            return None
        archive_path = Path(self.root) / archive_rel
        if not archive_path.is_file():
            return None
        try:
            return read_rpf_entry_variants(
                archive_path,
                entry_path,
                _get_lut(),
                self._native_crypto_context(),
            )
        except Exception:
            return None

    def _logical_archive_bytes_from_standalone(self, asset: AssetRecord, standalone: bytes) -> bytes:
        if asset.is_resource:
            try:
                return parse_rsc7(standalone)[1]
            except Exception:
                return standalone
        if asset.uncompressed_size != asset.stored_size:
            try:
                return _decompress_deflate(standalone)
            except Exception:
                return standalone
        return standalone

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

        native_variants = self._read_archive_asset_native_variants(asset)
        if native_variants is not None:
            stored_native, standalone_native = native_variants
            self._log(f"read file {asset.path}")
            logical_native = self._logical_archive_bytes_from_standalone(asset, standalone_native)
            ext = Path(asset.path).suffix.lower()
            raw_source = standalone_native if ext in {".ytd", ".ydr", ".ydd", ".ycd", ".ybn", ".ynd", ".ynv"} else stored_native
            parsed, kind = _decode_payload(asset.path, logical_native, raw=raw_source)
            entry = asset.entry if isinstance(asset.entry, RpfFileEntry) else None
            archive = asset.archive if isinstance(asset.archive, RpfArchive) else None
            game_file = GameFile(
                path=asset.path,
                kind=kind,
                entry=entry,
                archive=archive,
                raw=stored_native,
                parsed=parsed,
                loaded=True,
            )
            self._remember_file(asset.key, game_file)
            return game_file

        entry = self._get_entry_for_asset(asset)
        if entry is not None:
            if entry._archive is None:
                raise ValueError(f"Entry is detached from archive: {asset.path}")
            self._log(f"read file {asset.path}")
            stored = entry.read(logical=False)
            logical = entry.read(logical=True)
            raw_source = None
            if asset.path.lower().endswith((".ytd", ".ydr", ".ydd", ".ycd", ".ybn", ".ynd", ".ynv")):
                raw_source = entry._archive.read_entry_standalone(entry)
            parsed, kind = _decode_payload(asset.path, logical, raw=raw_source)
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
        native = self._read_archive_asset_native(asset, standalone=logical)
        if native is not None:
            self._log(f"read bytes {asset.path} logical={logical}")
            if logical:
                return self._logical_archive_bytes_from_standalone(asset, native)
            return native
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
                    except Exception:
                        pass
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
