from __future__ import annotations

import dataclasses
import struct
from pathlib import Path
from typing import Any, Iterator

from ..binary import vec3
from ..hashing import jenk_hash
from ..metahash import MetaHash
from .constants import DEFAULT_YED_EXPRESSION_VFT, DEFAULT_YED_VERSION, SPRING_BLOCK_SIZE
from .enums import YedInstructionType, YedTrackFormat


def _coerce_track_format(value: YedTrackFormat | int) -> YedTrackFormat:
    try:
        return YedTrackFormat(int(value))
    except ValueError as exc:
        raise ValueError(f"unsupported YED track format: {value!r}") from exc


@dataclasses.dataclass(slots=True)
class ResourceListInfo:
    pointer: int = 0
    count: int = 0
    capacity: int = 0
    unknown: int = 0

    @classmethod
    def read(cls, data: bytes, offset: int) -> "ResourceListInfo":
        pointer, count, capacity, unknown = struct.unpack_from("<QHHI", data, offset)
        return cls(pointer=pointer, count=count, capacity=capacity, unknown=unknown)


@dataclasses.dataclass(slots=True)
class YedTrack:
    bone_id: int
    track: int
    flags: int

    @property
    def format(self) -> YedTrackFormat:
        return _coerce_track_format(self.flags & 0x7F)

    @format.setter
    def format(self, value: YedTrackFormat | int) -> None:
        self.flags = (_coerce_track_format(value).value & 0x7F) | (self.flags & 0x80)

    @property
    def remap_flag(self) -> bool:
        return bool(self.flags & 0x80)

    @remap_flag.setter
    def remap_flag(self, value: bool) -> None:
        self.flags = (self.flags & 0x7F) | (0x80 if value else 0)

    @classmethod
    def vector3(cls, bone_id: int, track: int = 0, *, remap: bool = False) -> "YedTrack":
        return cls.from_parts(bone_id, track, YedTrackFormat.VECTOR3, remap=remap)

    @classmethod
    def quaternion(cls, bone_id: int, track: int = 0, *, remap: bool = False) -> "YedTrack":
        return cls.from_parts(bone_id, track, YedTrackFormat.QUATERNION, remap=remap)

    @classmethod
    def scalar(cls, bone_id: int, track: int = 0, *, remap: bool = False) -> "YedTrack":
        return cls.from_parts(bone_id, track, YedTrackFormat.FLOAT, remap=remap)

    @classmethod
    def from_parts(
        cls,
        bone_id: int,
        track: int,
        format: YedTrackFormat | int,
        *,
        remap: bool = False,
    ) -> "YedTrack":
        return cls(
            bone_id=int(bone_id) & 0xFFFF,
            track=int(track) & 0xFF,
            flags=(_coerce_track_format(format).value & 0x7F) | (0x80 if remap else 0),
        )


@dataclasses.dataclass(slots=True)
class YedInstruction:
    type: YedInstructionType | int
    index: int = 0
    data1_offset: int = 0
    data2_offset: int = 0
    operands: dict[str, Any] = dataclasses.field(default_factory=dict)
    parsed: bool = True
    parse_error: str = ""

    @property
    def opcode(self) -> int:
        return int(self.type) & 0xFF

    @property
    def name(self) -> str:
        try:
            return YedInstructionType(self.opcode).name
        except ValueError:
            return f"UNKNOWN_{self.opcode:02X}"

    def require_parsed(self) -> None:
        if not self.parsed:
            raise ValueError(f"cannot rebuild unresolved YED instruction {self.name} at index {self.index}: {self.parse_error}")


@dataclasses.dataclass(slots=True)
class YedStream:
    name_hash: MetaHash
    depth: int
    data1: bytes
    data2: bytes
    data3: bytes
    instructions: list[YedInstruction] = dataclasses.field(default_factory=list)
    raw: bytes = b""
    pointer: int = 0
    offset: int = 0

    @property
    def instruction_count(self) -> int:
        return len(self.data3)

    @property
    def has_semantic_instructions(self) -> bool:
        return bool(self.instructions) and all(instruction.parsed for instruction in self.instructions)

    def rebuild_buffers_from_instructions(self) -> None:
        from .instructions import build_instruction_buffers

        self.data1, self.data2, self.data3 = build_instruction_buffers(self.instructions)

    @classmethod
    def raw_stream(
        cls,
        name: str | int | MetaHash,
        *,
        depth: int = 0,
        data1: bytes = b"",
        data2: bytes = b"",
        data3: bytes = b"\x00",
    ) -> "YedStream":
        name_hash = int(name, 16) if isinstance(name, str) and name.lower().startswith("0x") else jenk_hash(name) if isinstance(name, str) else MetaHash(name)
        instructions = [
            YedInstruction(YedInstructionType(opcode) if opcode in YedInstructionType._value2member_map_ else opcode, index)
            for index, opcode in enumerate(data3)
        ]
        return cls(name_hash=MetaHash(name_hash), depth=int(depth), data1=bytes(data1), data2=bytes(data2), data3=bytes(data3), instructions=instructions)


@dataclasses.dataclass(slots=True)
class YedSpring:
    raw: bytes

    def __post_init__(self) -> None:
        if len(self.raw) != SPRING_BLOCK_SIZE:
            raise ValueError(f"YED spring blocks must be {SPRING_BLOCK_SIZE:#x} bytes")

    @property
    def bone_id(self) -> int:
        return struct.unpack_from("<H", self.raw, 0x9C)[0]

    @bone_id.setter
    def bone_id(self, value: int) -> None:
        data = bytearray(self.raw)
        struct.pack_into("<H", data, 0x9C, int(value) & 0xFFFF)
        self.raw = bytes(data)

    @property
    def gravity(self) -> tuple[float, float, float]:
        return vec3(self.raw, 0x90)

    @gravity.setter
    def gravity(self, value: tuple[float, float, float]) -> None:
        data = bytearray(self.raw)
        struct.pack_into("<3f", data, 0x90, *value)
        self.raw = bytes(data)

    @property
    def reserved(self) -> int:
        return struct.unpack_from("<H", self.raw, 0x9E)[0]

    @reserved.setter
    def reserved(self, value: int) -> None:
        data = bytearray(self.raw)
        struct.pack_into("<H", data, 0x9E, int(value) & 0xFFFF)
        self.raw = bytes(data)

    @classmethod
    def default(cls, bone_id: int, *, gravity: tuple[float, float, float] = (0.0, 0.0, -9.81)) -> "YedSpring":
        data = bytearray(SPRING_BLOCK_SIZE)
        struct.pack_into("<3f", data, 0x90, *gravity)
        struct.pack_into("<H", data, 0x9C, int(bone_id) & 0xFFFF)
        return cls(bytes(data))

    def clone(self, *, bone_id: int | None = None) -> "YedSpring":
        spring = YedSpring(self.raw)
        if bone_id is not None:
            spring.bone_id = bone_id
        return spring


@dataclasses.dataclass(slots=True)
class YedExpression:
    name: str
    name_hash: MetaHash
    pointer: int = 0
    offset: int = 0
    vft: int = DEFAULT_YED_EXPRESSION_VFT
    unknown_4h: int = 1
    unknown_70h: int = 1
    signature: int = 0
    max_stream_size: int = 0
    expression_flags: int = 0
    header: bytes = b""
    streams_info: ResourceListInfo = dataclasses.field(default_factory=ResourceListInfo)
    tracks_info: ResourceListInfo = dataclasses.field(default_factory=ResourceListInfo)
    springs_info: ResourceListInfo = dataclasses.field(default_factory=ResourceListInfo)
    variables_info: ResourceListInfo = dataclasses.field(default_factory=ResourceListInfo)
    streams: list[YedStream] = dataclasses.field(default_factory=list)
    tracks: list[YedTrack] = dataclasses.field(default_factory=list)
    springs: list[YedSpring] = dataclasses.field(default_factory=list)
    variables: list[MetaHash] = dataclasses.field(default_factory=list)
    _original_spring_bones: tuple[int, ...] = dataclasses.field(default_factory=tuple, repr=False)
    _dirty_springs: bool = dataclasses.field(default=False, repr=False)

    @property
    def short_name(self) -> str:
        return Path(self.name).stem.lower()

    @property
    def spring_bone_ids(self) -> tuple[int, ...]:
        return tuple(spring.bone_id for spring in self.springs)

    @property
    def has_spring_changes(self) -> bool:
        return self._dirty_springs or self.spring_bone_ids != self._original_spring_bones

    def iter_springs(self) -> Iterator[YedSpring]:
        yield from self.springs

    def find_spring(self, bone_id: int) -> YedSpring | None:
        target = int(bone_id) & 0xFFFF
        for spring in self.springs:
            if spring.bone_id == target:
                return spring
        return None

    def append_spring(self, spring: YedSpring) -> YedSpring:
        self.springs.append(spring.clone())
        self._dirty_springs = True
        return self.springs[-1]

    def clone_spring(self, source_bone_id: int, target_bone_id: int) -> YedSpring:
        source = self.find_spring(source_bone_id)
        if source is None:
            raise KeyError(f"Expression {self.short_name!r} has no spring for bone {source_bone_id:#06x}")
        clone = source.clone(bone_id=target_bone_id)
        self.springs.append(clone)
        self._dirty_springs = True
        return clone

    def clone_springs(self, mapping: dict[int, int]) -> list[YedSpring]:
        return [self.clone_spring(source, target) for source, target in mapping.items()]

    def ensure_spring(self, bone_id: int, *, template: int | None = None) -> YedSpring:
        existing = self.find_spring(bone_id)
        if existing is not None:
            return existing
        if template is not None:
            return self.clone_spring(template, bone_id)
        spring = YedSpring.default(bone_id)
        self.springs.append(spring)
        self._dirty_springs = True
        return spring

    def tracks_for_bone(self, bone_id: int) -> list[YedTrack]:
        target = int(bone_id) & 0xFFFF
        return [track for track in self.tracks if track.bone_id == target]

    def ensure_track(
        self,
        bone_id: int,
        track: int = 0,
        format: YedTrackFormat | int = YedTrackFormat.VECTOR3,
        *,
        remap: bool = False,
    ) -> YedTrack:
        target_format = _coerce_track_format(format)
        for item in self.tracks:
            if item.bone_id == (int(bone_id) & 0xFFFF) and item.track == (int(track) & 0xFF) and item.format == target_format:
                return item
        item = YedTrack.from_parts(bone_id, track, target_format, remap=remap)
        self.tracks.append(item)
        return item

    @classmethod
    def create(cls, name: str, *, springs: list[YedSpring] | None = None, tracks: list[YedTrack] | None = None) -> "YedExpression":
        short = Path(name).stem.lower()
        full_name = name if name.startswith("pack:/") else f"pack:/{short}.expr"
        spring_list = list(springs or [])
        return cls(
            name=full_name,
            name_hash=MetaHash(jenk_hash(short)),
            springs=spring_list,
            tracks=list(tracks or []),
            _original_spring_bones=tuple(spring.bone_id for spring in spring_list),
        )


@dataclasses.dataclass(slots=True)
class YedDictionary:
    file_vft: int = 0
    file_unknown: int = 1
    pages_info_pointer: int = 0
    unknown_10h: int = 0
    unknown_14h: int = 0
    unknown_18h: int = 1
    unknown_1ch: int = 0
    expression_name_hashes: ResourceListInfo = dataclasses.field(default_factory=ResourceListInfo)
    expressions_info: ResourceListInfo = dataclasses.field(default_factory=ResourceListInfo)
    expressions: list[YedExpression] = dataclasses.field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.expressions)

    def iter_expressions(self) -> Iterator[YedExpression]:
        yield from self.expressions


@dataclasses.dataclass(slots=True)
class Yed:
    dictionary: YedDictionary = dataclasses.field(default_factory=YedDictionary)
    version: int = DEFAULT_YED_VERSION
    path: str = ""
    system_flags: int = 0
    graphics_flags: int = 0
    system_data: bytes = b""
    graphics_data: bytes = b""
    _standalone_data: bytes | None = dataclasses.field(default=None, repr=False)

    @property
    def name(self) -> str:
        return Path(self.path).name if self.path else ""

    @property
    def expressions(self) -> list[YedExpression]:
        return self.dictionary.expressions

    @property
    def dirty(self) -> bool:
        return self._standalone_data is None or any(expression.has_spring_changes for expression in self.expressions)

    def expression_names(self) -> list[str]:
        return [expression.short_name for expression in self.expressions]

    def iter_expressions(self) -> Iterator[YedExpression]:
        yield from self.expressions

    def get_expression(self, name: str | int | MetaHash) -> YedExpression | None:
        if isinstance(name, str):
            normalized = name.lower()
            short = Path(normalized).stem
            target_hash = jenk_hash(short)
            for expression in self.expressions:
                if expression.name.lower() == normalized or expression.short_name == short:
                    return expression
                if int(expression.name_hash) == target_hash:
                    return expression
            return None
        target = int(MetaHash(name))
        for expression in self.expressions:
            if int(expression.name_hash) == target:
                return expression
        return None

    def require_expression(self, name: str | int | MetaHash) -> YedExpression:
        expression = self.get_expression(name)
        if expression is None:
            raise KeyError(f"YED expression not found: {name!r}")
        return expression

    def clone_expression_springs(self, expression: str | int | MetaHash, mapping: dict[int, int]) -> list[YedSpring]:
        springs = self.require_expression(expression).clone_springs(mapping)
        self._standalone_data = None
        return springs

    def clone_breast_springs_to_glutes(
        self,
        *,
        expression: str = "breasts",
        left_breast: int = 0xFC8E,
        right_breast: int = 0x885F,
        left_glute: int = 0x40B2,
        right_glute: int = 0xC141,
    ) -> list[YedSpring]:
        return self.clone_expression_springs(
            expression,
            {
                left_breast: left_glute,
                right_breast: right_glute,
            },
        )

    def ensure_expression(self, name: str) -> YedExpression:
        existing = self.get_expression(name)
        if existing is not None:
            return existing
        expression = YedExpression.create(name)
        self.expressions.append(expression)
        self._standalone_data = None
        return expression

    def rename_expression(self, old: str | int | MetaHash, new: str) -> YedExpression:
        expression = self.require_expression(old)
        short = Path(new).stem.lower()
        expression.name = new if new.startswith("pack:/") else f"pack:/{short}.expr"
        expression.name_hash = MetaHash(jenk_hash(short))
        self._standalone_data = None
        return expression

    def clone_expression(self, source: str | int | MetaHash, target: str) -> YedExpression:
        original = self.require_expression(source)
        clone = dataclasses.replace(
            original,
            name=target if target.startswith("pack:/") else f"pack:/{Path(target).stem.lower()}.expr",
            name_hash=MetaHash(jenk_hash(Path(target).stem.lower())),
            streams=[
                dataclasses.replace(stream, instructions=[dataclasses.replace(instruction, operands=dict(instruction.operands)) for instruction in stream.instructions])
                for stream in original.streams
            ],
            tracks=[dataclasses.replace(track) for track in original.tracks],
            springs=[spring.clone() for spring in original.springs],
            variables=list(original.variables),
            _original_spring_bones=tuple(spring.bone_id for spring in original.springs),
            _dirty_springs=True,
        )
        self.expressions.append(clone)
        self._standalone_data = None
        return clone

    def copy_springs_from(
        self,
        source_expression: str | int | MetaHash,
        target_expression: str | int | MetaHash,
        *,
        mapping: dict[int, int] | None = None,
        replace: bool = False,
    ) -> list[YedSpring]:
        source = self.require_expression(source_expression)
        target = self.require_expression(target_expression)
        if replace:
            target.springs.clear()
        copied: list[YedSpring] = []
        for spring in source.springs:
            target_bone_id = int(mapping.get(spring.bone_id, spring.bone_id)) if mapping else spring.bone_id
            existing = target.find_spring(target_bone_id)
            if existing is not None:
                continue
            copied.append(target.append_spring(spring.clone(bone_id=target_bone_id)))
        self._standalone_data = None
        return copied

    def retarget_bone_ids(self, mapping: dict[int, int], *, expressions: list[str | int | MetaHash] | None = None) -> "Yed":
        selected = [self.require_expression(expression) for expression in expressions] if expressions else list(self.expressions)
        normalized = {int(source) & 0xFFFF: int(target) & 0xFFFF for source, target in mapping.items()}
        for expression in selected:
            for spring in expression.springs:
                if spring.bone_id in normalized:
                    spring.bone_id = normalized[spring.bone_id]
                    expression._dirty_springs = True
            for track in expression.tracks:
                if int(track.bone_id) in normalized:
                    track.bone_id = normalized[int(track.bone_id)]
            for stream in expression.streams:
                for instruction in stream.instructions:
                    bone_id = instruction.operands.get("bone_id")
                    if bone_id is not None and int(bone_id) in normalized:
                        instruction.operands["bone_id"] = normalized[int(bone_id)]
                    spring_raw = instruction.operands.get("spring_raw")
                    if isinstance(spring_raw, (bytes, bytearray)) and len(spring_raw) == SPRING_BLOCK_SIZE:
                        spring = YedSpring(bytes(spring_raw))
                        if spring.bone_id in normalized:
                            spring.bone_id = normalized[spring.bone_id]
                            instruction.operands["spring_raw"] = spring.raw
        self._standalone_data = None
        return self

    def refresh_metadata(self) -> "Yed":
        self.dictionary.expressions.sort(key=lambda expression: int(expression.name_hash))
        for expression in self.expressions:
            expression.max_stream_size = max((0x10 + len(stream.data1) + len(stream.data2) + len(stream.data3) for stream in expression.streams), default=0)
        self._standalone_data = None
        return self

    def validate(self, *, skeleton: object | None = None, raise_on_error: bool = True) -> list["YedValidationIssue"]:
        issues = validate_yed(self, skeleton=skeleton)
        if issues and raise_on_error:
            details = "; ".join(issue.message for issue in issues[:4])
            raise ValueError(f"invalid YED: {details}")
        return issues

    def to_bytes(self) -> bytes:
        if self._standalone_data is not None and not self.dirty:
            return self._standalone_data
        from .writer import build_yed_bytes

        return build_yed_bytes(self)

    def save(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.write_bytes(self.to_bytes())
        self.path = str(target)
        return target


@dataclasses.dataclass(slots=True)
class YedValidationIssue:
    code: str
    message: str
    expression: str = ""


def create_yed(*expressions: str | YedExpression, version: int = DEFAULT_YED_VERSION) -> Yed:
    yed = Yed(version=version)
    for expression in expressions:
        yed.expressions.append(expression if isinstance(expression, YedExpression) else YedExpression.create(expression))
    return yed


def _collect_skeleton_bone_tags(skeleton: object | None) -> set[int]:
    if skeleton is None:
        return set()
    if hasattr(skeleton, "skeleton") and getattr(skeleton, "skeleton") is not None:
        return _collect_skeleton_bone_tags(getattr(skeleton, "skeleton"))
    if hasattr(skeleton, "drawable"):
        return _collect_skeleton_bone_tags(getattr(skeleton, "drawable"))
    if hasattr(skeleton, "drawables"):
        tags: set[int] = set()
        for entry in getattr(skeleton, "drawables"):
            tags.update(_collect_skeleton_bone_tags(entry))
        return tags
    bones = getattr(skeleton, "bones", None)
    if bones is None:
        return set()
    return {int(getattr(bone, "tag")) & 0xFFFF for bone in bones if hasattr(bone, "tag")}


def validate_yed(yed: Yed, *, skeleton: object | None = None) -> list[YedValidationIssue]:
    issues: list[YedValidationIssue] = []
    seen_hashes: set[int] = set()
    skeleton_tags = _collect_skeleton_bone_tags(skeleton)
    for expression in yed.expressions:
        short = expression.short_name
        expression_name = short or expression.name
        if not expression.name:
            issues.append(YedValidationIssue("expression-name-empty", "YED expression names cannot be empty", expression_name))
        if int(expression.name_hash) in seen_hashes:
            issues.append(YedValidationIssue("expression-hash-duplicate", f"duplicate YED expression hash {int(expression.name_hash):#010x}", expression_name))
        seen_hashes.add(int(expression.name_hash))
        if short and int(expression.name_hash) != jenk_hash(short):
            issues.append(
                YedValidationIssue(
                    "expression-hash-mismatch",
                    f"expression {expression.name!r} hash does not match short name {short!r}",
                    expression_name,
                )
            )
        for track in expression.tracks:
            try:
                _ = track.format
            except ValueError as exc:
                issues.append(YedValidationIssue("track-format-invalid", str(exc), expression_name))
            if skeleton_tags and (int(track.bone_id) & 0xFFFF) not in skeleton_tags:
                issues.append(YedValidationIssue("track-bone-missing", f"track bone id {track.bone_id:#06x} is not present in the skeleton", expression_name))
        seen_springs: set[int] = set()
        for spring in expression.springs:
            if len(spring.raw) != SPRING_BLOCK_SIZE:
                issues.append(YedValidationIssue("spring-size-invalid", "YED spring raw block has invalid size", expression_name))
            if spring.bone_id in seen_springs:
                issues.append(YedValidationIssue("spring-bone-duplicate", f"duplicate spring bone id {spring.bone_id:#06x}", expression_name))
            seen_springs.add(spring.bone_id)
            if skeleton_tags and (int(spring.bone_id) & 0xFFFF) not in skeleton_tags:
                issues.append(YedValidationIssue("spring-bone-missing", f"spring bone id {spring.bone_id:#06x} is not present in the skeleton", expression_name))
        for stream in expression.streams:
            if len(stream.data3) > 0xFFFF:
                issues.append(YedValidationIssue("stream-opcode-list-too-large", "YED stream instruction list cannot exceed 65535 bytes", expression_name))
            for instruction in stream.instructions:
                if not instruction.parsed:
                    issues.append(
                        YedValidationIssue(
                            "stream-instruction-unresolved",
                            f"stream {int(stream.name_hash):#010x} has unresolved instruction {instruction.name}: {instruction.parse_error}",
                            expression_name,
                        )
                    )
    return issues


__all__ = [
    "YedInstruction",
    "YedInstructionType",
    "ResourceListInfo",
    "Yed",
    "YedDictionary",
    "YedExpression",
    "YedSpring",
    "YedStream",
    "YedTrack",
    "YedTrackFormat",
    "YedValidationIssue",
    "create_yed",
    "validate_yed",
]
