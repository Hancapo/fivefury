from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .rpf import RpfArchive, RpfFileEntry


class GameFileType(IntEnum):
    UNKNOWN = -1
    YDD = 0
    YDR = 1
    YFT = 2
    YMAP = 3
    YMF = 4
    YMT = 5
    YTD = 6
    YTYP = 7
    YBN = 8
    YCD = 9
    YPT = 10
    YND = 11
    YNV = 12
    REL = 13
    YWR = 14
    YVR = 15
    GTXD = 16
    VEHICLES = 17
    CAR_COLS = 18
    CAR_MOD_COLS = 19
    CAR_VARIATIONS = 20
    VEHICLE_LAYOUTS = 21
    PEDS = 22
    PED = 23
    YED = 24
    YLD = 25
    YFD = 26
    HEIGHTMAP = 27
    WATERMAP = 28
    MRF = 29
    DISTANT_LIGHTS = 30
    YPDB = 31
    CUT = 32
    RPF = 100
    BINARY = 101


_FILE_TYPE_MAP: dict[str, GameFileType] = {
    ".ymap": GameFileType.YMAP,
    ".ytyp": GameFileType.YTYP,
    ".ytd": GameFileType.YTD,
    ".ydr": GameFileType.YDR,
    ".ydd": GameFileType.YDD,
    ".yft": GameFileType.YFT,
    ".ybn": GameFileType.YBN,
    ".ycd": GameFileType.YCD,
    ".ypt": GameFileType.YPT,
    ".ynd": GameFileType.YND,
    ".ynv": GameFileType.YNV,
    ".rel": GameFileType.REL,
    ".ywr": GameFileType.YWR,
    ".yvr": GameFileType.YVR,
    ".gxt2": GameFileType.GTXD,
    ".cut": GameFileType.CUT,
    ".cutxml": GameFileType.CUT,
    ".rpf": GameFileType.RPF,
}


def guess_game_file_type(path: str | Path, default: GameFileType = GameFileType.UNKNOWN) -> GameFileType:
    ext = Path(str(path)).suffix.lower()
    return _FILE_TYPE_MAP.get(ext, default)


@dataclass(slots=True)
class GameFile:
    path: str
    kind: GameFileType = GameFileType.UNKNOWN
    entry: Optional["RpfFileEntry"] = None
    archive: Optional["RpfArchive"] = None
    raw: bytes | None = None
    parsed: Any = None
    loaded: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def extension(self) -> str:
        return Path(self.path).suffix.lower()

    @property
    def stem(self) -> str:
        return Path(self.path).stem

    def read_bytes(self, *, logical: bool = True) -> bytes:
        if logical:
            if self.entry is not None and self.archive is not None:
                return self.archive.read_entry_bytes(self.entry, logical=True)
            if isinstance(self.parsed, (bytes, bytearray)):
                return bytes(self.parsed)
            if hasattr(self.parsed, "to_bytes"):
                return self.parsed.to_bytes()
        if self.raw is None and self.entry is not None and self.archive is not None:
            self.raw = self.archive.read_entry_bytes(self.entry, logical=False)
        if self.raw is None:
            return b""
        return self.raw

    def ensure_loaded(self, loader: Callable[[bytes], Any] | None = None) -> Any:
        if self.loaded:
            return self.parsed
        data = self.read_bytes(logical=True)
        self.parsed = loader(data) if loader is not None else data
        self.loaded = True
        return self.parsed
