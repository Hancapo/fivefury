from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from ..dlc.enums import DlcDataFileType
from ..gamefile import GameFileType

_METADATA_KINDS = {
    DlcDataFileType.PED_METADATA: GameFileType.PEDS,
    DlcDataFileType.EXPRESSION_SETS: GameFileType.EXPRESSION_SETS,
}


@dataclass(frozen=True, slots=True)
class AssetRegistration:
    """Explicit content registration, relative to a mounted asset root."""

    path: str
    file_type: DlcDataFileType

    def __post_init__(self) -> None:
        path = PurePosixPath(self.path.replace("\\", "/"))
        if (
            path.is_absolute()
            or ".." in path.parts
            or ":" in str(path)
            or str(path) == "."
        ):
            raise ValueError("Registration path must be relative to the asset root")
        object.__setattr__(self, "path", path.as_posix())
        object.__setattr__(self, "file_type", DlcDataFileType(self.file_type))
        if self.file_type not in _METADATA_KINDS:
            raise ValueError(f"Unsupported metadata registration: {self.file_type}")

    @property
    def kind(self) -> GameFileType:
        return _METADATA_KINDS[self.file_type]
