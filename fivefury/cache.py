from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from .gamefile import GameFile, GameFileType, guess_game_file_type
from .resolver import HashResolver, get_hash_resolver
from .rpf import RpfArchive, RpfEntry, RpfFileEntry, load_rpf, _normalize_key


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
            return load_rpf(data), GameFileType.RPF
        except Exception:
            return data, GameFileType.RPF
    return data, guess_game_file_type(path, GameFileType.UNKNOWN)


@dataclass
class GameFileCache:
    root: str | Path | None = None
    resolver: HashResolver | None = None
    archives: list[RpfArchive] = field(default_factory=list)
    files: dict[str, GameFile] = field(default_factory=dict)
    entries: dict[str, RpfEntry] = field(default_factory=dict)
    loose_files: dict[str, Path] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.resolver is None:
            self.resolver = get_hash_resolver()

    def clear(self) -> None:
        self.archives.clear()
        self.files.clear()
        self.entries.clear()
        self.loose_files.clear()

    def scan(self, root: str | Path | None = None) -> None:
        if root is not None:
            self.root = root
        if self.root is None:
            raise ValueError("A root directory is required")

        self.clear()
        root_path = Path(self.root)
        for path in root_path.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root_path).as_posix()
            if path.suffix.lower() == ".rpf":
                archive = RpfArchive.from_path(path)
                self.register_archive(archive, source_prefix=rel)
            else:
                self.loose_files[_normalize_key(rel)] = path
                if self.resolver is not None:
                    self.resolver.register_path_name(rel)

    def register_archive(self, archive: RpfArchive, *, source_prefix: str | None = None) -> None:
        self.archives.append(archive)
        prefix = (source_prefix or "").replace("\\", "/").strip("/")
        for entry in archive.iter_entries(include_directories=False):
            key = _normalize_key(f"{prefix}/{entry.full_path}" if prefix else entry.full_path)
            self.entries[key] = entry
            if self.resolver is not None:
                self.resolver.register_path_name(entry.full_path)
        for child in archive.children:
            self.register_archive(child, source_prefix=prefix)

    def iter_files(self) -> Iterator[GameFile]:
        yield from self.files.values()

    def get_entry(self, path: str | Path) -> Optional[RpfEntry]:
        return self.entries.get(_normalize_key(path))

    def get_file(self, path: str | Path) -> GameFile | None:
        key = _normalize_key(path)
        cached = self.files.get(key)
        if cached is not None:
            return cached

        entry = self.entries.get(key)
        if entry is not None:
            if entry._archive is None:
                raise ValueError(f"Entry is detached from archive: {path}")
            stored = entry.read(logical=False)
            logical = entry.read(logical=True)
            parsed, kind = _decode_payload(str(path), logical)
            game_file = GameFile(path=str(path), kind=kind, entry=entry if isinstance(entry, RpfFileEntry) else None, archive=entry._archive, raw=stored, parsed=parsed, loaded=True)
            self.files[key] = game_file
            return game_file

        loose = self.loose_files.get(key)
        if loose is None:
            return None
        data = loose.read_bytes()
        parsed, kind = _decode_payload(str(path), data)
        game_file = GameFile(path=str(path), kind=kind, raw=data, parsed=parsed, loaded=True)
        self.files[key] = game_file
        return game_file

    def get_bytes(self, path: str | Path, *, logical: bool = True) -> bytes | None:
        gf = self.get_file(path)
        if gf is None:
            return None
        if logical:
            if isinstance(gf.parsed, (bytes, bytearray)):
                return bytes(gf.parsed)
            if hasattr(gf.parsed, "to_bytes"):
                return gf.parsed.to_bytes()  # type: ignore[no-any-return]
        return gf.raw

    def get_archive(self, path: str | Path) -> RpfArchive | None:
        gf = self.get_file(path)
        if gf is None:
            return None
        return gf.parsed if isinstance(gf.parsed, RpfArchive) else None

