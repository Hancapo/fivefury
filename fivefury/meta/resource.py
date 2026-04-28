from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from . import Meta, MetaEnumInfo, MetaStructInfo, ParsedMeta


@dataclass(slots=True)
class MetaResource:
    meta: Meta = field(default_factory=Meta)
    source: str = ""

    extension: ClassVar[str] = ""

    @property
    def name(self) -> str:
        return self.meta.Name

    @name.setter
    def name(self, value: str) -> None:
        self.meta.Name = str(value or "")

    @property
    def root_name_hash(self) -> int:
        return self.meta.root_name_hash

    @root_name_hash.setter
    def root_name_hash(self, value: int) -> None:
        self.meta.root_name_hash = int(value)

    @property
    def root_value(self) -> Any:
        return self.meta.root_value

    @root_value.setter
    def root_value(self, value: Any) -> None:
        self.meta.root_value = value

    @property
    def decoded_root(self) -> Any:
        return self.meta.root_value

    @property
    def struct_infos(self) -> list[MetaStructInfo]:
        return self.meta.struct_infos

    @property
    def enum_infos(self) -> list[MetaEnumInfo]:
        return self.meta.enum_infos

    @property
    def resource_version(self) -> int:
        return self.meta.resource_version

    @resource_version.setter
    def resource_version(self, value: int) -> None:
        self.meta.resource_version = int(value)

    def to_meta(self) -> Meta:
        return self.meta

    def to_bytes(self) -> bytes:
        return self.meta.to_rsc7()

    def save(self, path: str | Path | None = None) -> Path:
        destination = Path(path) if path is not None else Path(self.suggested_path())
        destination.write_bytes(self.to_bytes())
        return destination

    def suggested_path(self) -> str:
        stem = self.name or "unnamed"
        extension = self.extension or ".ymt"
        return stem if stem.lower().endswith(extension) else f"{stem}{extension}"

    @classmethod
    def from_meta(cls, meta: Meta, *, source: str = "") -> "MetaResource":
        return cls(meta=meta, source=source)

    @classmethod
    def from_parsed_meta(cls, parsed: ParsedMeta, *, source: str = "") -> "MetaResource":
        return cls(
            meta=Meta(
                Name=parsed.name,
                root_name_hash=parsed.data_blocks[parsed.root_block_index - 1].struct_name_hash
                if parsed.root_block_index > 0 and parsed.data_blocks
                else 0,
                root_value=parsed.decoded_root,
                struct_infos=list(parsed.struct_infos.values()),
                enum_infos=list(parsed.enum_infos.values()),
                resource_version=parsed.resource_version or 2,
            ),
            source=source,
        )

    @classmethod
    def from_bytes(cls, data: bytes, *, source: str = "") -> "MetaResource":
        return cls.from_parsed_meta(ParsedMeta.from_bytes(data), source=source)

    @classmethod
    def from_path(cls, path: str | Path) -> "MetaResource":
        target = Path(path)
        return cls.from_bytes(target.read_bytes(), source=str(target))


__all__ = ["MetaResource"]
