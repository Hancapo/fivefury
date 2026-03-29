from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .utils import _resource_flags_from_size, _size_from_resource_flags

if TYPE_CHECKING:  # pragma: no cover
    from .rpf import RpfArchive

@dataclass(slots=True)
class RpfResourcePageFlags:
    value: int = 0

    @property
    def size(self) -> int:
        return _size_from_resource_flags(self.value)

    @property
    def base_shift(self) -> int:
        return self.value & 0xF

    @classmethod
    def from_size(cls, size: int, version: int = 0) -> "RpfResourcePageFlags":
        return cls(_resource_flags_from_size(size, version))


@dataclass(slots=True)
class RpfEntry:
    name: str = ""
    path: str = ""
    parent: Optional["RpfDirectoryEntry"] = None
    name_offset: int = 0
    _archive: Optional["RpfArchive"] = field(default=None, repr=False, compare=False)

    @property
    def name_lower(self) -> str:
        return self.name.lower()

    @property
    def full_path(self) -> str:
        if self._archive is not None and self._archive.prefix:
            return f"{self._archive.prefix}/{self.path}" if self.path else self._archive.prefix
        return self.path

    @property
    def is_directory(self) -> bool:
        return False

    @property
    def is_file(self) -> bool:
        return False

    def get_short_name(self) -> str:
        dot = self.name.rfind(".")
        return self.name[:dot] if dot > 0 else self.name


@dataclass(slots=True)
class RpfDirectoryEntry(RpfEntry):
    entries_index: int = 0
    entries_count: int = 0
    directories: list["RpfDirectoryEntry"] = field(default_factory=list)
    files: list["RpfFileEntry"] = field(default_factory=list)

    @property
    def is_directory(self) -> bool:
        return True


@dataclass(slots=True)
class RpfFileEntry(RpfEntry):
    file_offset: int = 0
    file_size: int = 0
    is_encrypted: bool = False

    @property
    def is_file(self) -> bool:
        return True

    def get_file_size(self) -> int:
        raise NotImplementedError

    def set_file_size(self, size: int) -> None:
        raise NotImplementedError

    def read_raw(self) -> bytes:
        if self._archive is None:
            raise ValueError("Detached RPF entry")
        return self._archive.read_entry_raw(self)

    def read(self, logical: bool = True) -> bytes:
        if self._archive is None:
            raise ValueError("Detached RPF entry")
        return self._archive.read_entry_bytes(self, logical=logical)


@dataclass(slots=True)
class RpfBinaryFileEntry(RpfFileEntry):
    file_uncompressed_size: int = 0
    encryption_type: int = 0
    child_archive: Optional["RpfArchive"] = field(default=None, repr=False, compare=False)
    _data: bytes | None = field(default=None, repr=False, compare=False)

    def get_file_size(self) -> int:
        return self.file_size if self.file_size else self.file_uncompressed_size

    def set_file_size(self, size: int) -> None:
        self.file_size = int(size)


@dataclass(slots=True)
class RpfResourceFileEntry(RpfFileEntry):
    system_flags: RpfResourcePageFlags = field(default_factory=RpfResourcePageFlags)
    graphics_flags: RpfResourcePageFlags = field(default_factory=RpfResourcePageFlags)
    child_archive: Optional["RpfArchive"] = field(default=None, repr=False, compare=False)
    _data: bytes | None = field(default=None, repr=False, compare=False)

    def get_file_size(self) -> int:
        return self.file_size if self.file_size else self.system_flags.size + self.graphics_flags.size

    def set_file_size(self, size: int) -> None:
        self.file_size = int(size)

    @property
    def system_size(self) -> int:
        return self.system_flags.size

    @property
    def graphics_size(self) -> int:
        return self.graphics_flags.size




