from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, TypeAlias

from ..common import hash_value
from ..metahash import MetaHash
from .enums import Dat10RelType, Dat16RelType, Dat22RelType, Dat54SoundType, RelDatFileType

RelHashLike: TypeAlias = int | MetaHash | str


def _mask32(value: int) -> int:
    return int(value) & 0xFFFFFFFF


def rel_hash(value: RelHashLike) -> int:
    return _mask32(hash_value(value))


def _rotated_hash(value: int) -> int:
    value = _mask32(value)
    return _mask32((value >> 8) | (value << 24))


_HeaderField: TypeAlias = tuple[int, str, str]
_HeaderGroup: TypeAlias = tuple[int, int, tuple[_HeaderField, ...]]

_SOUND_HEADER_GROUPS: tuple[_HeaderGroup, ...] = (
    (
        0xFF,
        0xAA,
        (
            (0, "flags2", "I"),
            (1, "max_header_size", "H"),
            (2, "volume", "h"),
            (3, "volume_variance", "H"),
            (4, "pitch", "h"),
            (5, "pitch_variance", "H"),
            (6, "pan", "H"),
            (7, "pan_variance", "H"),
        ),
    ),
    (
        0xFF00,
        0xAA00,
        (
            (8, "pre_delay", "h"),
            (9, "pre_delay_variance", "H"),
            (10, "start_offset", "i"),
            (11, "start_offset_variance", "i"),
            (12, "attack_time", "H"),
            (13, "release_time", "H"),
            (14, "doppler_factor", "H"),
            (15, "category", "I"),
        ),
    ),
    (
        0xFF0000,
        0xAA0000,
        (
            (16, "lpf_cutoff", "H"),
            (17, "lpf_cutoff_variance", "H"),
            (18, "hpf_cutoff", "H"),
            (19, "hpf_cutoff_variance", "H"),
            (20, "volume_curve", "I"),
            (21, "volume_curve_scale", "h"),
            (22, "volume_curve_plateau", "B"),
            (23, "speaker_mask", "B"),
        ),
    ),
    (
        0xFF000000,
        0xAA000000,
        (
            (24, "effect_route", "B"),
            (25, "pre_delay_variable", "I"),
            (26, "start_offset_variable", "I"),
            (27, "small_reverb_send", "H"),
            (28, "medium_reverb_send", "H"),
            (29, "large_reverb_send", "H"),
            (30, "unk25", "H"),
            (31, "unk26", "H"),
        ),
    ),
)


def _pack_header_value(fmt: str, value: int) -> bytes:
    if fmt in {"I", "H", "B"}:
        mask = (1 << (struct.calcsize("<" + fmt) * 8)) - 1
        value &= mask
    return struct.pack("<" + fmt, value)


@dataclass(slots=True)
class RelIndexHash:
    name_hash: int
    offset: int
    length: int


@dataclass(slots=True)
class RelIndexString:
    name: str
    offset: int
    length: int


@dataclass(slots=True)
class RelItem:
    name_hash: int = 0
    name: str | None = None
    data_offset: int = 0
    data_length: int = 0
    type_id: int = 0
    raw_data: bytes = b""

    def to_data(self) -> bytes:
        return bytes(self.raw_data)

    def hash_table_offsets(self) -> list[int]:
        return []

    def pack_table_offsets(self) -> list[int]:
        return []


@dataclass(slots=True)
class RelRawItem(RelItem):
    pass


@dataclass(slots=True)
class NamedRelItem(RelItem):
    name_table_offset: int = 0
    flags: int = 0

    def typed_name_header_bytes(self) -> bytes:
        packed = ((self.name_table_offset & 0xFFFFFF) << 8) | (self.type_id & 0xFF)
        return struct.pack("<II", packed, _mask32(self.flags))


@dataclass(slots=True)
class Dat10RelItem(NamedRelItem):
    def dat10_header_bytes(self) -> bytes:
        return self.typed_name_header_bytes()


@dataclass(slots=True)
class Dat10SynthPresetVariable:
    name: RelHashLike
    value1: float = 0.0
    value2: float = 0.0

    def to_bytes(self) -> bytes:
        return struct.pack("<Iff", rel_hash(self.name), float(self.value1), float(self.value2))


@dataclass(slots=True)
class Dat10SynthVariable:
    name: RelHashLike
    value: float = 0.0

    def to_bytes(self) -> bytes:
        return struct.pack("<If", rel_hash(self.name), float(self.value))


@dataclass(slots=True)
class Dat10SynthPreset(Dat10RelItem):
    variables: list[Dat10SynthPresetVariable] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat10RelType.SYNTH_PRESET)

    def to_data(self) -> bytes:
        return self.dat10_header_bytes() + bytes([len(self.variables) & 0xFF]) + b"".join(v.to_bytes() for v in self.variables)


@dataclass(slots=True)
class Dat10Synth(Dat10RelItem):
    MAX_OUTPUTS: ClassVar[int] = 4

    buffers_count: int = 0
    registers_count: int = 0
    outputs_count: int = 0
    output_indices: bytes = b"\x00\x00\x00\x00"
    bytecode: bytes = b""
    state_blocks_count: int = 0
    runtime_cost: int = 0
    constants: list[float] = field(default_factory=list)
    variables: list[Dat10SynthVariable] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat10RelType.SYNTH)

    def to_data(self) -> bytes:
        outputs = bytes(self.output_indices[: self.MAX_OUTPUTS]).ljust(self.MAX_OUTPUTS, b"\x00")
        data = bytearray(self.dat10_header_bytes())
        data += struct.pack(
            "<iii4siii",
            int(self.buffers_count),
            int(self.registers_count),
            int(self.outputs_count),
            outputs,
            len(self.bytecode),
            int(self.state_blocks_count),
            int(self.runtime_cost),
        )
        data += bytes(self.bytecode)
        data += struct.pack("<i", len(self.constants))
        data += struct.pack("<" + "f" * len(self.constants), *[float(v) for v in self.constants]) if self.constants else b""
        data += struct.pack("<i", len(self.variables))
        data += b"".join(v.to_bytes() for v in self.variables)
        return bytes(data)


@dataclass(slots=True)
class Dat16Curve(NamedRelItem):
    curve_type: Dat16RelType | int = Dat16RelType.CONSTANT_CURVE
    min_input: float = 0.0
    max_input: float = 1.0
    value: float = 0.0
    left_hand_pair_x: float = 0.0
    left_hand_pair_y: float = 0.0
    right_hand_pair_x: float = 0.0
    right_hand_pair_y: float = 0.0
    points: list[tuple[float, float]] = field(default_factory=list)
    flip: int = 0
    values: list[float] = field(default_factory=list)
    exponent: float = 1.0
    horizontal_scaling: float = 1.0
    start_phase: float = 0.0
    end_phase: float = 0.0
    frequency: float = 1.0
    vertical_scaling: float = 1.0
    vertical_offset: float = 0.0

    def __post_init__(self) -> None:
        self.type_id = int(self.curve_type)

    def to_data(self) -> bytes:
        data = bytearray(self.typed_name_header_bytes())
        data += struct.pack("<ff", float(self.min_input), float(self.max_input))
        curve_type = int(self.curve_type)
        if curve_type == int(Dat16RelType.CONSTANT_CURVE):
            data += struct.pack("<f", float(self.value))
        elif curve_type in {int(Dat16RelType.LINEAR_CURVE), int(Dat16RelType.LINEAR_DB_CURVE)}:
            data += struct.pack(
                "<ffff",
                float(self.left_hand_pair_x),
                float(self.left_hand_pair_y),
                float(self.right_hand_pair_x),
                float(self.right_hand_pair_y),
            )
        elif curve_type == int(Dat16RelType.PIECEWISE_LINEAR_CURVE):
            data += struct.pack("<I", len(self.points))
            for x, y in self.points:
                data += struct.pack("<ff", float(x), float(y))
        elif curve_type == int(Dat16RelType.EQUAL_POWER_CURVE):
            data += struct.pack("<i", int(self.flip))
        elif curve_type in {int(Dat16RelType.VALUE_TABLE_CURVE), int(Dat16RelType.DISTANCE_ATTENUATION_VALUE_TABLE_CURVE)}:
            data += struct.pack("<i", len(self.values))
            data += struct.pack("<" + "f" * len(self.values), *[float(v) for v in self.values]) if self.values else b""
        elif curve_type == int(Dat16RelType.EXPONENTIAL_CURVE):
            data += struct.pack("<if", int(self.flip), float(self.exponent))
        elif curve_type in {
            int(Dat16RelType.DECAYING_EXPONENTIAL_CURVE),
            int(Dat16RelType.DECAYING_SQUARED_EXPONENTIAL_CURVE),
            int(Dat16RelType.ONE_OVER_X_SQUARED_CURVE),
        }:
            data += struct.pack("<f", float(self.horizontal_scaling))
        elif curve_type == int(Dat16RelType.SINE_CURVE):
            data += struct.pack(
                "<fffff",
                float(self.start_phase),
                float(self.end_phase),
                float(self.frequency),
                float(self.vertical_scaling),
                float(self.vertical_offset),
            )
        elif curve_type == int(Dat16RelType.DEFAULT_DISTANCE_ATTENUATION_CURVE):
            pass
        else:
            return bytes(self.raw_data)
        return bytes(data)


@dataclass(slots=True)
class Dat22RelItem(NamedRelItem):
    pass


@dataclass(slots=True)
class Dat22Category(Dat22RelItem):
    parent_overrides: int = 0
    volume: int = 0
    pitch: int = 0
    lpf_cutoff: int = 0
    lpf_distance_curve: RelHashLike = 0
    hpf_cutoff: int = 0
    hpf_distance_curve: RelHashLike = 0
    distance_roll_off_scale: int = 0
    plateau_roll_off_scale: int = 0
    occlusion_damping: int = 0
    environmental_filter_damping: int = 0
    source_reverb_damping: int = 0
    distance_reverb_damping: int = 0
    interior_reverb_damping: int = 0
    environmental_loudness: int = 0
    underwater_wet_level: int = 0
    stoned_wet_level: int = 0
    timer: int = 0
    subcategories: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat22RelType.CATEGORY)

    def to_data(self) -> bytes:
        values = [
            int(self.parent_overrides),
            int(self.volume),
            int(self.pitch),
            int(self.lpf_cutoff),
            rel_hash(self.lpf_distance_curve),
            int(self.hpf_cutoff),
            rel_hash(self.hpf_distance_curve),
            int(self.distance_roll_off_scale),
            int(self.plateau_roll_off_scale),
            int(self.occlusion_damping),
            int(self.environmental_filter_damping),
            int(self.source_reverb_damping),
            int(self.distance_reverb_damping),
            int(self.interior_reverb_damping),
            int(self.environmental_loudness),
            int(self.underwater_wet_level),
            int(self.stoned_wet_level),
            int(self.timer) & 0xFF,
            len(self.subcategories) & 0xFF,
        ]
        data = bytearray(self.typed_name_header_bytes())
        data += struct.pack("<hhhhIhIhhhhhhhhhhBB", *values)
        for category in self.subcategories:
            data += struct.pack("<I", rel_hash(category))
        return bytes(data)

    def curve_hashes(self) -> tuple[int, int]:
        return rel_hash(self.lpf_distance_curve), rel_hash(self.hpf_distance_curve)

    def category_hashes(self) -> list[int]:
        return [rel_hash(value) for value in self.subcategories]


@dataclass(slots=True)
class RelSoundHeader:
    flags: int = 0xAAAAAAAA
    flags2: int = 0
    max_header_size: int = 0
    volume: int = 0
    volume_variance: int = 0
    pitch: int = 0
    pitch_variance: int = 0
    pan: int = 0
    pan_variance: int = 0
    pre_delay: int = 0
    pre_delay_variance: int = 0
    start_offset: int = 0
    start_offset_variance: int = 0
    attack_time: int = 0
    release_time: int = 0
    doppler_factor: int = 0
    category: int = 0
    lpf_cutoff: int = 0
    lpf_cutoff_variance: int = 0
    hpf_cutoff: int = 0
    hpf_cutoff_variance: int = 0
    volume_curve: int = 0
    volume_curve_scale: int = 0
    volume_curve_plateau: int = 0
    speaker_mask: int = 0
    effect_route: int = 0
    pre_delay_variable: int = 0
    start_offset_variable: int = 0
    small_reverb_send: int = 0
    medium_reverb_send: int = 0
    large_reverb_send: int = 0
    unk25: int = 0
    unk26: int = 0

    def bit(self, index: int) -> bool:
        return bool(self.flags & (1 << index))

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0) -> tuple["RelSoundHeader", int]:
        pos = offset
        flags = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        header = cls(flags=flags)

        def read(fmt: str) -> int:
            nonlocal offset
            value = struct.unpack_from("<" + fmt, data, offset)[0]
            offset += struct.calcsize("<" + fmt)
            return int(value)

        for mask, skip_value, fields in _SOUND_HEADER_GROUPS:
            if (flags & mask) == skip_value:
                continue
            for bit, attr, fmt in fields:
                if header.bit(bit):
                    setattr(header, attr, read(fmt))
        return header, offset - pos

    def to_bytes(self) -> bytes:
        data = bytearray(struct.pack("<I", _mask32(self.flags)))
        for mask, skip_value, fields in _SOUND_HEADER_GROUPS:
            if (self.flags & mask) == skip_value:
                continue
            for bit, attr, fmt in fields:
                if self.bit(bit):
                    data += _pack_header_value(fmt, getattr(self, attr))
        return bytes(data)

    def byte_length(self) -> int:
        length = 4
        for mask, skip_value, fields in _SOUND_HEADER_GROUPS:
            if (self.flags & mask) == skip_value:
                continue
            length += sum(struct.calcsize("<" + fmt) for bit, _, fmt in fields if self.bit(bit))
        return length


@dataclass(slots=True)
class Dat54Sound(RelItem):
    header: RelSoundHeader = field(default_factory=RelSoundHeader)

    def sound_payload_bytes(self) -> bytes:
        return b""

    def to_data(self) -> bytes:
        return bytes([self.type_id & 0xFF]) + self.header.to_bytes() + self.sound_payload_bytes()

    def hash_base_adjustment(self) -> int:
        return 1 + self.header.byte_length()


@dataclass(slots=True)
class Dat54LoopingSound(Dat54Sound):
    loop_count: int = 0
    loop_count_variance: int = 0
    loop_point: int = 0
    child_sound: RelHashLike = 0
    loop_count_variable: RelHashLike = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.LOOPING_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<hhhII",
            int(self.loop_count),
            int(self.loop_count_variance),
            int(self.loop_point),
            rel_hash(self.child_sound),
            rel_hash(self.loop_count_variable),
        )

    def hash_table_offsets(self) -> list[int]:
        return [6]


@dataclass(slots=True)
class Dat54SimpleSound(Dat54Sound):
    container_name: RelHashLike = 0
    file_name: RelHashLike = 0
    wave_slot_index: int = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.SIMPLE_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack("<IIB", rel_hash(self.container_name), rel_hash(self.file_name), int(self.wave_slot_index) & 0xFF)

    def pack_table_offsets(self) -> list[int]:
        return [0]

    def audio_container_hashes(self) -> list[int]:
        return [rel_hash(self.container_name)]


@dataclass(slots=True)
class Dat54ChildListSound(Dat54Sound):
    child_sounds: list[RelHashLike] = field(default_factory=list)
    child_offset: int = 0

    def sound_payload_bytes(self) -> bytes:
        data = bytearray(bytes([len(self.child_sounds) & 0xFF]))
        data += b"".join(struct.pack("<I", rel_hash(sound)) for sound in self.child_sounds)
        return bytes(data)

    def hash_table_offsets(self) -> list[int]:
        return [int(self.child_offset) + 1 + i * 4 for i in range(len(self.child_sounds))]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(sound) for sound in self.child_sounds]


@dataclass(slots=True)
class Dat54SequentialSound(Dat54ChildListSound):
    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.SEQUENTIAL_SOUND)
        self.child_offset = 0


@dataclass(slots=True)
class Dat54MultitrackSound(Dat54ChildListSound):
    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.MULTITRACK_SOUND)
        self.child_offset = 0


@dataclass(slots=True)
class Dat54StreamingSound(Dat54ChildListSound):
    duration: int = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.STREAMING_SOUND)
        self.child_offset = 4

    def sound_payload_bytes(self) -> bytes:
        return struct.pack("<i", int(self.duration)) + super().sound_payload_bytes()


@dataclass(slots=True)
class Dat54WrapperVariable:
    name: RelHashLike
    value: int = 0

    def to_bytes(self) -> bytes:
        return struct.pack("<IB", rel_hash(self.name), int(self.value) & 0xFF)


@dataclass(slots=True)
class Dat54WrapperSound(Dat54Sound):
    child_sound: RelHashLike = 0
    last_play_time: int = 0
    fallback_sound: RelHashLike = 0
    min_repeat_time: int = 0
    variables: list[Dat54WrapperVariable] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.WRAPPER_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return (
            struct.pack(
                "<IiIhB",
                rel_hash(self.child_sound),
                int(self.last_play_time),
                rel_hash(self.fallback_sound),
                int(self.min_repeat_time),
                len(self.variables) & 0xFF,
            )
            + b"".join(variable.to_bytes() for variable in self.variables)
        )

    def hash_table_offsets(self) -> list[int]:
        return [0, 8]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.child_sound), rel_hash(self.fallback_sound)]


@dataclass(slots=True)
class Dat54RandomizedVariation:
    sound: RelHashLike
    weight: float = 1.0

    def to_bytes(self) -> bytes:
        return struct.pack("<If", rel_hash(self.sound), float(self.weight))


@dataclass(slots=True)
class Dat54RandomizedSound(Dat54Sound):
    history_index: int = 0
    history_space: bytes = b""
    variations: list[Dat54RandomizedVariation] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.RANDOMIZED_SOUND)

    def sound_payload_bytes(self) -> bytes:
        data = bytearray(
            struct.pack(
                "<BB",
                int(self.history_index) & 0xFF,
                len(self.history_space) & 0xFF,
            )
        )
        data += bytes(self.history_space)
        data += bytes([len(self.variations) & 0xFF])
        data += b"".join(variation.to_bytes() for variation in self.variations)
        return bytes(data)

    def hash_table_offsets(self) -> list[int]:
        offset = 3 + len(self.history_space)
        return [offset + i * 8 for i in range(len(self.variations))]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(variation.sound) for variation in self.variations]


@dataclass(slots=True)
class Dat54ModularSynthSoundVariable:
    variable_name: RelHashLike
    parameter_name: RelHashLike
    value: float = 0.0

    def to_bytes(self) -> bytes:
        return struct.pack("<IIf", rel_hash(self.variable_name), rel_hash(self.parameter_name), float(self.value))


@dataclass(slots=True)
class Dat54ModularSynthSound(Dat54Sound):
    synth_sound: RelHashLike = 0
    synth_preset: RelHashLike = 0
    playback_time_limit: float = 0.0
    virtualisation_mode: int = 0
    track_count: int = 0
    environment_sounds: list[RelHashLike] = field(default_factory=lambda: [0, 0, 0, 0])
    exposed_variables: list[Dat54ModularSynthSoundVariable] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.MODULAR_SYNTH_SOUND)

    def sound_payload_bytes(self) -> bytes:
        env = [rel_hash(value) for value in self.environment_sounds[:4]]
        env.extend([0] * (4 - len(env)))
        data = bytearray(
            struct.pack(
                "<IIfii4I",
                rel_hash(self.synth_sound),
                rel_hash(self.synth_preset),
                float(self.playback_time_limit),
                int(self.virtualisation_mode),
                int(self.track_count),
                *env,
            )
        )
        data += struct.pack("<i", len(self.exposed_variables))
        data += b"".join(v.to_bytes() for v in self.exposed_variables)
        return bytes(data)

    def hash_table_offsets(self) -> list[int]:
        return [20, 24, 28, 32]

    def synth_hashes(self) -> tuple[int, int]:
        return rel_hash(self.synth_sound), rel_hash(self.synth_preset)


@dataclass(slots=True)
class Dat54SoundSetItem:
    script_name: RelHashLike
    child_sound: RelHashLike

    def to_bytes(self) -> bytes:
        return struct.pack("<II", rel_hash(self.script_name), rel_hash(self.child_sound))


@dataclass(slots=True)
class Dat54SoundSet(Dat54Sound):
    sound_sets: list[Dat54SoundSetItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.SOUND_SET)

    def sound_payload_bytes(self) -> bytes:
        ordered = sorted(self.sound_sets, key=lambda item: rel_hash(item.script_name))
        return struct.pack("<i", len(ordered)) + b"".join(item.to_bytes() for item in ordered)

    def hash_table_offsets(self) -> list[int]:
        return [8 + i * 8 for i in range(len(self.sound_sets))]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(item.child_sound) for item in self.sound_sets]


@dataclass(slots=True)
class Dat54SoundSetList(Dat54Sound):
    sound_sets: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.SOUND_SET_LIST)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack("<I", len(self.sound_sets)) + b"".join(struct.pack("<I", rel_hash(sound)) for sound in self.sound_sets)

    def hash_table_offsets(self) -> list[int]:
        return [4 + i * 4 for i in range(len(self.sound_sets))]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(sound) for sound in self.sound_sets]


@dataclass(slots=True)
class Dat54SoundHashList(Dat54Sound):
    unk_short: int = 0
    sound_hashes_list: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.SOUND_HASH_LIST)

    def sound_payload_bytes(self) -> bytes:
        return (
            struct.pack("<HI", int(self.unk_short) & 0xFFFF, len(self.sound_hashes_list))
            + b"".join(struct.pack("<I", rel_hash(sound)) for sound in self.sound_hashes_list)
        )

    def sound_hashes(self) -> list[int]:
        return [rel_hash(sound) for sound in self.sound_hashes_list]


@dataclass(slots=True)
class Dat54AutomationSoundVariableOutput:
    channel: int = 0
    variable: RelHashLike = 0

    def to_bytes(self) -> bytes:
        return struct.pack("<iI", int(self.channel), rel_hash(self.variable))


@dataclass(slots=True)
class Dat54AutomationSound(Dat54Sound):
    fallback_sound: RelHashLike = 0
    playback_rate: float = 1.0
    playback_rate_variance: float = 0.0
    playback_rate_variable: RelHashLike = 0
    note_map: RelHashLike = 0
    container_name: RelHashLike = 0
    file_name: RelHashLike = 0
    variable_outputs: list[Dat54AutomationSoundVariableOutput] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.AUTOMATION_SOUND)

    def sound_payload_bytes(self) -> bytes:
        data = bytearray(
            struct.pack(
                "<IffIIIIi",
                rel_hash(self.fallback_sound),
                float(self.playback_rate),
                float(self.playback_rate_variance),
                rel_hash(self.playback_rate_variable),
                rel_hash(self.note_map),
                rel_hash(self.container_name),
                rel_hash(self.file_name),
                len(self.variable_outputs),
            )
        )
        data += b"".join(output.to_bytes() for output in self.variable_outputs)
        return bytes(data)

    def hash_table_offsets(self) -> list[int]:
        return [0, 16]

    def pack_table_offsets(self) -> list[int]:
        return [20]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.fallback_sound), rel_hash(self.note_map)]

    def audio_container_hashes(self) -> list[int]:
        return [rel_hash(self.container_name)]


@dataclass(slots=True)
class Dat54AutomationNoteMapRange:
    first_note_id: int = 0
    last_note_id: int = 0
    mode: int = 0
    child_sound: RelHashLike = 0

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<BBBI",
            int(self.first_note_id) & 0xFF,
            int(self.last_note_id) & 0xFF,
            int(self.mode) & 0xFF,
            rel_hash(self.child_sound),
        )


@dataclass(slots=True)
class Dat54AutomationNoteMapSound(Dat54Sound):
    ranges: list[Dat54AutomationNoteMapRange] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.AUTOMATION_NOTE_MAP_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return bytes([len(self.ranges) & 0xFF]) + b"".join(item.to_bytes() for item in self.ranges)

    def hash_table_offsets(self) -> list[int]:
        return [4 + i * 7 for i in range(len(self.ranges))]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(item.child_sound) for item in self.ranges]


@dataclass(slots=True)
class Dat54VariableCurveSound(Dat54Sound):
    child_sound: RelHashLike = 0
    input_variable: RelHashLike = 0
    output_variable: RelHashLike = 0
    curve: RelHashLike = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.VARIABLE_CURVE_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<IIII",
            rel_hash(self.child_sound),
            rel_hash(self.input_variable),
            rel_hash(self.output_variable),
            rel_hash(self.curve),
        )

    def hash_table_offsets(self) -> list[int]:
        return [0]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.child_sound)]

    def curve_hashes(self) -> list[int]:
        return [rel_hash(self.curve)]


@dataclass(slots=True)
class Dat54IfSound(Dat54Sound):
    true_sound: RelHashLike = 0
    false_sound: RelHashLike = 0
    condition_variable: RelHashLike = 0
    condition_type: int = 0
    condition_value: float = 0.0
    rhs: RelHashLike = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.IF_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<IIIBfI",
            rel_hash(self.true_sound),
            rel_hash(self.false_sound),
            rel_hash(self.condition_variable),
            int(self.condition_type) & 0xFF,
            float(self.condition_value),
            rel_hash(self.rhs),
        )

    def hash_table_offsets(self) -> list[int]:
        return [0, 4]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.true_sound), rel_hash(self.false_sound)]


@dataclass(slots=True)
class Dat54DirectionalSound(Dat54Sound):
    child_sound: RelHashLike = 0
    inner_angle: float = 0.0
    outer_angle: float = 0.0
    rear_attenuation: float = 0.0
    yaw_angle: float = 0.0
    pitch_angle: float = 0.0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.DIRECTIONAL_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<Ifffff",
            rel_hash(self.child_sound),
            float(self.inner_angle),
            float(self.outer_angle),
            float(self.rear_attenuation),
            float(self.yaw_angle),
            float(self.pitch_angle),
        )

    def hash_table_offsets(self) -> list[int]:
        return [0]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.child_sound)]


@dataclass(slots=True)
class Dat54KineticSound(Dat54Sound):
    child_sound: RelHashLike = 0
    mass: float = 0.0
    yaw_angle: float = 0.0
    pitch_angle: float = 0.0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.KINETIC_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<Ifff",
            rel_hash(self.child_sound),
            float(self.mass),
            float(self.yaw_angle),
            float(self.pitch_angle),
        )

    def hash_table_offsets(self) -> list[int]:
        return [0]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.child_sound)]


@dataclass(slots=True)
class Dat54VariableData:
    name: RelHashLike = 0
    value: float = 0.0
    value_variance: float = 0.0
    variable_type: int = 0

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<IffB",
            rel_hash(self.name),
            float(self.value),
            float(self.value_variance),
            int(self.variable_type) & 0xFF,
        )


@dataclass(slots=True)
class Dat54VariableBlockSound(Dat54Sound):
    child_sound: RelHashLike = 0
    variables: list[Dat54VariableData] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.VARIABLE_BLOCK_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return (
            struct.pack("<IB", rel_hash(self.child_sound), len(self.variables) & 0xFF)
            + b"".join(variable.to_bytes() for variable in self.variables)
        )

    def hash_table_offsets(self) -> list[int]:
        return [0]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.child_sound)]


@dataclass(slots=True)
class Dat54MathOperation:
    operation_type: int = 0
    input_immediate_1: float = 0.0
    input_parameter_1: RelHashLike = 0
    input_immediate_2: float = 0.0
    input_parameter_2: RelHashLike = 0
    input_immediate_3: float = 0.0
    input_parameter_3: RelHashLike = 0
    output_parameter: RelHashLike = 0

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<BfIfIfII",
            int(self.operation_type) & 0xFF,
            float(self.input_immediate_1),
            rel_hash(self.input_parameter_1),
            float(self.input_immediate_2),
            rel_hash(self.input_parameter_2),
            float(self.input_immediate_3),
            rel_hash(self.input_parameter_3),
            rel_hash(self.output_parameter),
        )


@dataclass(slots=True)
class Dat54MathOperationSound(Dat54Sound):
    child_sound: RelHashLike = 0
    operations: list[Dat54MathOperation] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.MATH_OPERATION_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return (
            struct.pack("<Ii", rel_hash(self.child_sound), len(self.operations))
            + b"".join(operation.to_bytes() for operation in self.operations)
        )

    def hash_table_offsets(self) -> list[int]:
        return [0]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.child_sound)]


@dataclass(slots=True)
class Dat54ParameterTransform:
    smooth_rate: float = 0.0
    transform_type: int = 0
    transform_type_parameter: RelHashLike = 0
    output_range_min: float = 0.0
    output_range_max: float = 0.0
    vectors: list[tuple[float, float]] = field(default_factory=list)

    def to_bytes(self) -> bytes:
        data = bytearray(
            struct.pack(
                "<fiIffi",
                float(self.smooth_rate),
                int(self.transform_type),
                rel_hash(self.transform_type_parameter),
                float(self.output_range_min),
                float(self.output_range_max),
                len(self.vectors),
            )
        )
        for x, y in self.vectors:
            data += struct.pack("<ff", float(x), float(y))
        return bytes(data)


@dataclass(slots=True)
class Dat54ParameterTransformBlock:
    input_parameter: RelHashLike = 0
    input_range_min: float = 0.0
    input_range_max: float = 0.0
    transforms: list[Dat54ParameterTransform] = field(default_factory=list)

    def to_bytes(self) -> bytes:
        return (
            struct.pack(
                "<Iffi",
                rel_hash(self.input_parameter),
                float(self.input_range_min),
                float(self.input_range_max),
                len(self.transforms),
            )
            + b"".join(transform.to_bytes() for transform in self.transforms)
        )


@dataclass(slots=True)
class Dat54ParameterTransformSound(Dat54Sound):
    child_sound: RelHashLike = 0
    parameter_transforms: list[Dat54ParameterTransformBlock] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.PARAMETER_TRANSFORM_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return (
            struct.pack("<Ii", rel_hash(self.child_sound), len(self.parameter_transforms))
            + b"".join(transform.to_bytes() for transform in self.parameter_transforms)
        )

    def hash_table_offsets(self) -> list[int]:
        return [0]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.child_sound)]


@dataclass(slots=True)
class Dat54Fluctuator:
    mode: int = 0
    destination: int = 0
    output_variable: RelHashLike = 0
    increase_rate: float = 0.0
    decrease_rate: float = 0.0
    band_one_minimum: float = 0.0
    band_one_maximum: float = 0.0
    band_two_minimum: float = 0.0
    band_two_maximum: float = 0.0
    intra_band_flip_probability: float = 0.0
    inter_band_flip_probability: float = 0.0
    min_switch_time: float = 0.0
    max_switch_time: float = 0.0
    initial_value: float = 0.0

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<BBI" + "f" * 11,
            int(self.mode) & 0xFF,
            int(self.destination) & 0xFF,
            rel_hash(self.output_variable),
            float(self.increase_rate),
            float(self.decrease_rate),
            float(self.band_one_minimum),
            float(self.band_one_maximum),
            float(self.band_two_minimum),
            float(self.band_two_maximum),
            float(self.intra_band_flip_probability),
            float(self.inter_band_flip_probability),
            float(self.min_switch_time),
            float(self.max_switch_time),
            float(self.initial_value),
        )


@dataclass(slots=True)
class Dat54FluctuatorSound(Dat54Sound):
    child_sound: RelHashLike = 0
    fluctuators: list[Dat54Fluctuator] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.FLUCTUATOR_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return (
            struct.pack("<Ii", rel_hash(self.child_sound), len(self.fluctuators))
            + b"".join(fluctuator.to_bytes() for fluctuator in self.fluctuators)
        )

    def hash_table_offsets(self) -> list[int]:
        return [0]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.child_sound)]


@dataclass(slots=True)
class Dat54ExternalStreamSound(Dat54ChildListSound):
    environment_sound_1: RelHashLike = 0
    environment_sound_2: RelHashLike = 0
    environment_sound_3: RelHashLike = 0
    environment_sound_4: RelHashLike = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.EXTERNAL_STREAM_SOUND)
        self.child_offset = 0

    def sound_payload_bytes(self) -> bytes:
        data = bytearray(super().sound_payload_bytes())
        data += struct.pack("<II", rel_hash(self.environment_sound_1), rel_hash(self.environment_sound_2))
        if not self.child_sounds:
            data += struct.pack("<II", rel_hash(self.environment_sound_3), rel_hash(self.environment_sound_4))
        return bytes(data)

    def hash_table_offsets(self) -> list[int]:
        offsets = super().hash_table_offsets()
        env_offset = 1 + len(self.child_sounds) * 4
        offsets.extend([env_offset, env_offset + 4])
        if not self.child_sounds:
            offsets.extend([env_offset + 8, env_offset + 12])
        return offsets

    def sound_hashes(self) -> list[int]:
        hashes = super().sound_hashes()
        hashes.extend([rel_hash(self.environment_sound_1), rel_hash(self.environment_sound_2)])
        if not self.child_sounds:
            hashes.extend([rel_hash(self.environment_sound_3), rel_hash(self.environment_sound_4)])
        return hashes


@dataclass(slots=True)
class RelFile:
    rel_type: RelDatFileType | int
    version: int = 0
    items: list[RelItem] = field(default_factory=list)
    name_table: list[str] = field(default_factory=list)
    index_hashes: list[RelIndexHash] = field(default_factory=list)
    index_strings: list[RelIndexString] = field(default_factory=list)
    hash_table_offsets: list[int] = field(default_factory=list)
    pack_table_offsets: list[int] = field(default_factory=list)
    is_audio_config: bool = False
    index_string_flags: int = 2524
    path: str | None = None

    def find_item(self, name_or_hash: RelHashLike) -> RelItem | None:
        wanted = rel_hash(name_or_hash)
        for item in self.items:
            if item.name_hash == wanted or item.name == name_or_hash:
                return item
        return None

    def iter_items(self, cls: type[RelItem] | None = None) -> Iterable[RelItem]:
        for item in self.items:
            if cls is None or isinstance(item, cls):
                yield item

    def to_bytes(self) -> bytes:
        from .io import build_rel_bytes

        return build_rel_bytes(self)

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path or self.path or "")
        if not str(target):
            raise ValueError("REL save path is required")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_bytes())
        self.path = str(target)
        return target

    def sorted_index_items(self) -> list[RelItem]:
        sortable = {
            int(RelDatFileType.DAT10_MODULAR_SYNTH),
            int(RelDatFileType.DAT15_DYNAMIC_MIXER),
            int(RelDatFileType.DAT16_CURVES),
            int(RelDatFileType.DAT22_CATEGORIES),
            int(RelDatFileType.DAT54_DATA_ENTRIES),
            int(RelDatFileType.DAT149),
            int(RelDatFileType.DAT150),
            int(RelDatFileType.DAT151),
        }
        if int(self.rel_type) in sortable:
            return sorted(self.items, key=lambda item: _rotated_hash(item.name_hash))
        if self.is_audio_config:
            return list(self.items)
        return sorted(self.items, key=lambda item: item.name_hash & 0xFFFFFFFF)
