from __future__ import annotations

from pathlib import Path

from ..meta import Meta
from ..meta.defs import meta_name
from ..meta.resource import MetaResource
from ..pso import PsoNode, PsoReader, is_pso
from ..xml import looks_like_xml
from .enums import YmfRelationship
from .model import PackFileMetaData
from .pso import YMF_PSO_ROOT, build_ymf_pso, resolve_ymf_pso_name


class Ymf(MetaResource):
    extension = ".ymf"

    def __init__(
        self,
        meta: Meta | None = None,
        source: str = "",
        *,
        manifest: PackFileMetaData | None = None,
        raw_bytes: bytes | None = None,
        pso_root: PsoNode | None = None,
    ) -> None:
        super().__init__(meta=meta or Meta(), source=source)
        self._manifest = manifest
        self.raw_bytes = raw_bytes
        self.pso_root = pso_root

    @property
    def manifest(self) -> PackFileMetaData | None:
        if self._manifest is not None:
            return self._manifest
        root = self.pso_root if self.pso_root is not None else self.root_value
        if root is None:
            return None
        if isinstance(root, PsoNode):
            if root.type_hash != YMF_PSO_ROOT and root.type_name != "CPackFileMetaData":
                return None
        elif self.root_name_hash != meta_name("CPackFileMetaData"):
            return None
        self._manifest = PackFileMetaData.from_meta_root(root)
        return self._manifest

    def iter_relationships(self) -> list[YmfRelationship]:
        manifest = self.manifest
        return [] if manifest is None else manifest.iter_relationships()

    def to_bytes(self) -> bytes:
        if self.raw_bytes is not None and self._manifest is None:
            return self.raw_bytes
        manifest = self.manifest
        if manifest is not None:
            self.meta = manifest.to_meta(name=self.name)
            return build_ymf_pso(manifest)
        return self.meta.to_rsc7()

    @classmethod
    def from_manifest(cls, manifest: PackFileMetaData, *, name: str = "", source: str = "") -> "Ymf":
        return cls(meta=manifest.to_meta(name=name), source=source, manifest=manifest)

    @classmethod
    def from_meta(cls, meta: Meta, *, source: str = "") -> "Ymf":
        return cls(meta=meta, source=source)

    @classmethod
    def from_bytes(cls, data: bytes, *, source: str = "") -> "Ymf":
        if looks_like_xml(data):
            return cls.from_manifest(PackFileMetaData.from_xml(data), source=source)
        if is_pso(data):
            root = PsoReader(data, name_resolver=resolve_ymf_pso_name).read().root
            return cls(source=source, manifest=PackFileMetaData.from_meta_root(root), raw_bytes=bytes(data), pso_root=root)
        parsed = super().from_bytes(data, source=source)
        return cls(meta=parsed.meta, source=source)

    @classmethod
    def from_path(cls, path: str | Path) -> "Ymf":
        target = Path(path)
        data = target.read_bytes()
        if target.suffix.lower() == ".xml":
            return cls.from_manifest(PackFileMetaData.from_xml(data), source=str(target))
        return cls.from_bytes(data, source=str(target))


def iter_ymf_relationships(value: Ymf | PackFileMetaData) -> list[YmfRelationship]:
    if isinstance(value, PackFileMetaData):
        return value.iter_relationships()
    return value.iter_relationships()


def read_ymf(data: bytes | str | Path) -> Ymf:
    if isinstance(data, (str, Path)):
        return Ymf.from_path(data)
    return Ymf.from_bytes(data)


def save_ymf(ymf: Ymf | PackFileMetaData | Meta, path: str | Path | None = None) -> Path:
    if isinstance(ymf, Ymf):
        resource = ymf
    elif isinstance(ymf, PackFileMetaData):
        resource = Ymf.from_manifest(ymf)
    else:
        resource = Ymf.from_meta(ymf)
    return resource.save(path)


def read_ymf_xml(source: bytes | str | Path) -> PackFileMetaData:
    return PackFileMetaData.from_xml(source)


def build_ymf(manifest: PackFileMetaData, *, name: str = "") -> Ymf:
    return Ymf.from_manifest(manifest, name=name)
