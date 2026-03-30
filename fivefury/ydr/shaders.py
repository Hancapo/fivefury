from __future__ import annotations

import dataclasses
from pathlib import Path
from xml.etree import ElementTree as ET

from ..hashing import jenk_hash


@dataclasses.dataclass(slots=True, frozen=True)
class ShaderParameterDefinition:
    name: str
    type_name: str
    subtype: str | None = None
    uv_index: int | None = None
    count: int = 1
    hidden: bool = False
    defaults: dict[str, str] = dataclasses.field(default_factory=dict)

    @property
    def name_hash(self) -> int:
        return int(jenk_hash(self.name))

    @property
    def is_texture(self) -> bool:
        return self.type_name.lower() == "texture"


@dataclasses.dataclass(slots=True, frozen=True)
class ShaderLayoutDefinition:
    type_name: str
    semantics: tuple[str, ...]

    def has_semantic(self, name: str) -> bool:
        return str(name) in self.semantics


@dataclasses.dataclass(slots=True)
class ShaderDefinition:
    name: str
    file_names_by_bucket: dict[int, tuple[str, ...]] = dataclasses.field(default_factory=dict)
    layouts: tuple[ShaderLayoutDefinition, ...] = ()
    parameters: tuple[ShaderParameterDefinition, ...] = ()
    _parameter_by_name: dict[str, ShaderParameterDefinition] = dataclasses.field(init=False, repr=False)
    _parameter_by_hash: dict[int, ShaderParameterDefinition] = dataclasses.field(init=False, repr=False)
    _file_name_hashes: dict[int, str] = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._parameter_by_name = {parameter.name.lower(): parameter for parameter in self.parameters}
        self._parameter_by_hash = {parameter.name_hash: parameter for parameter in self.parameters}
        self._file_name_hashes = {
            int(jenk_hash(file_name)): file_name
            for files in self.file_names_by_bucket.values()
            for file_name in files
        }

    @property
    def name_hash(self) -> int:
        return int(jenk_hash(self.name))

    @property
    def file_names(self) -> tuple[str, ...]:
        ordered: list[str] = []
        seen: set[str] = set()
        for bucket in sorted(self.file_names_by_bucket):
            for file_name in self.file_names_by_bucket[bucket]:
                lowered = file_name.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                ordered.append(file_name)
        return tuple(ordered)

    @property
    def texture_parameters(self) -> tuple[ShaderParameterDefinition, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.is_texture)

    def get_bucket_file_names(self, bucket: int) -> tuple[str, ...]:
        return self.file_names_by_bucket.get(int(bucket), ())

    def pick_file_name(self, bucket: int | None = None) -> str | None:
        if bucket is not None:
            matches = self.get_bucket_file_names(bucket)
            if matches:
                return matches[0]
        all_files = self.file_names
        return all_files[0] if all_files else None

    def get_parameter(self, value: str | int) -> ShaderParameterDefinition | None:
        if isinstance(value, str):
            return self._parameter_by_name.get(value.lower())
        return self._parameter_by_hash.get(int(value))

    def contains_file_hash(self, value: int) -> bool:
        return int(value) in self._file_name_hashes


@dataclasses.dataclass(slots=True)
class ShaderLibrary:
    shaders: tuple[ShaderDefinition, ...]
    _by_name: dict[str, ShaderDefinition] = dataclasses.field(init=False, repr=False)
    _by_name_hash: dict[int, ShaderDefinition] = dataclasses.field(init=False, repr=False)
    _by_file_name: dict[str, ShaderDefinition] = dataclasses.field(init=False, repr=False)
    _by_file_hash: dict[int, ShaderDefinition] = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._by_name = {}
        self._by_name_hash = {}
        self._by_file_name = {}
        self._by_file_hash = {}
        for shader in self.shaders:
            self._by_name.setdefault(shader.name.lower(), shader)
            self._by_name_hash.setdefault(shader.name_hash, shader)
            for file_name in shader.file_names:
                lowered = file_name.lower()
                self._by_file_name.setdefault(lowered, shader)
                self._by_file_hash.setdefault(int(jenk_hash(file_name)), shader)

    def get_shader(self, value: str | int) -> ShaderDefinition | None:
        if isinstance(value, str):
            lowered = value.lower()
            return self._by_name.get(lowered) or self._by_file_name.get(lowered)
        hash_value = int(value)
        return self._by_name_hash.get(hash_value) or self._by_file_hash.get(hash_value)

    def resolve_shader(
        self,
        *,
        shader_name: str | None = None,
        shader_name_hash: int = 0,
        shader_file_name: str | None = None,
        shader_file_hash: int = 0,
        render_bucket: int | None = None,
    ) -> ShaderDefinition | None:
        if shader_name:
            shader = self.get_shader(shader_name)
            if shader is not None:
                return shader
        if shader_name_hash:
            shader = self.get_shader(int(shader_name_hash))
            if shader is not None:
                return shader
        if shader_file_name:
            shader = self.get_shader(shader_file_name)
            if shader is not None:
                return shader
        if shader_file_hash:
            shader = self.get_shader(int(shader_file_hash))
            if shader is not None:
                return shader
        if render_bucket is not None:
            for shader in self.shaders:
                if shader.get_bucket_file_names(render_bucket):
                    return shader
        return None


def _coerce_bool(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def _parse_parameter(item: ET.Element) -> ShaderParameterDefinition:
    defaults = {
        key: value
        for key, value in item.attrib.items()
        if key not in {"name", "type", "subtype", "uv", "count", "hidden"}
    }
    uv_value = item.get("uv")
    count_value = item.get("count")
    return ShaderParameterDefinition(
        name=item.get("name", ""),
        type_name=item.get("type", ""),
        subtype=item.get("subtype"),
        uv_index=int(uv_value) if uv_value not in (None, "") else None,
        count=max(1, int(count_value)) if count_value not in (None, "") else 1,
        hidden=_coerce_bool(item.get("hidden")),
        defaults=defaults,
    )


def _parse_layout(item: ET.Element) -> ShaderLayoutDefinition:
    semantics = tuple(child.tag for child in item if child.tag)
    return ShaderLayoutDefinition(type_name=item.get("type", ""), semantics=semantics)


def _parse_shader(item: ET.Element) -> ShaderDefinition:
    name = (item.findtext("Name") or "").strip()

    file_names_by_bucket: dict[int, list[str]] = {}
    file_name_container = item.find("FileName")
    if file_name_container is not None:
        for file_item in file_name_container.findall("Item"):
            bucket = int(file_item.get("bucket", "0"))
            value = (file_item.text or "").strip()
            if value:
                file_names_by_bucket.setdefault(bucket, []).append(value)

    layouts: list[ShaderLayoutDefinition] = []
    layout_container = item.find("Layout")
    if layout_container is not None:
        layouts = [_parse_layout(layout_item) for layout_item in layout_container.findall("Item")]

    parameters: list[ShaderParameterDefinition] = []
    parameters_container = item.find("Parameters")
    if parameters_container is not None:
        parameters = [_parse_parameter(parameter_item) for parameter_item in parameters_container.findall("Item")]

    return ShaderDefinition(
        name=name,
        file_names_by_bucket={bucket: tuple(values) for bucket, values in file_names_by_bucket.items()},
        layouts=tuple(layouts),
        parameters=tuple(parameters),
    )


def _default_shader_library_path() -> Path:
    return Path(__file__).with_name("Shaders.xml")


def read_shader_library(path: str | Path | None = None) -> ShaderLibrary:
    source = Path(path) if path is not None else _default_shader_library_path()
    root = ET.fromstring(source.read_text(encoding="utf-8"))
    shaders = tuple(_parse_shader(item) for item in root.findall("Item"))
    return ShaderLibrary(shaders=shaders)


_DEFAULT_SHADER_LIBRARY: ShaderLibrary | None = None


def load_shader_library(path: str | Path | None = None, *, reload: bool = False) -> ShaderLibrary:
    global _DEFAULT_SHADER_LIBRARY
    if path is not None:
        return read_shader_library(path)
    if reload or _DEFAULT_SHADER_LIBRARY is None:
        _DEFAULT_SHADER_LIBRARY = read_shader_library()
    return _DEFAULT_SHADER_LIBRARY


__all__ = [
    "ShaderDefinition",
    "ShaderLayoutDefinition",
    "ShaderLibrary",
    "ShaderParameterDefinition",
    "load_shader_library",
    "read_shader_library",
]