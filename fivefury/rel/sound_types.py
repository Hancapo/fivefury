from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .enums import Dat54SoundType
from .limits import checked_count
from .model import Dat54Sound, RelHashLike, rel_hash


def _text_u8(value: str, label: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 255:
        raise ValueError(f"{label} is longer than 255 encoded bytes")
    return bytes([len(encoded)]) + encoded


@dataclass(slots=True)
class Dat54EnvelopeSound(Dat54Sound):
    attack: int = 0
    attack_variance: int = 0
    decay: int = 0
    decay_variance: int = 0
    sustain: int = 0
    sustain_variance: int = 0
    hold: int = 0
    hold_variance: int = 0
    release: int = 0
    release_variance: int = 0
    attack_curve: RelHashLike = 0
    decay_curve: RelHashLike = 0
    release_curve: RelHashLike = 0
    attack_variable: RelHashLike = 0
    decay_variable: RelHashLike = 0
    sustain_variable: RelHashLike = 0
    hold_variable: RelHashLike = 0
    release_variable: RelHashLike = 0
    child_sound: RelHashLike = 0
    mode: int = 0
    output_variable: RelHashLike = 0
    output_range_min: float = 0.0
    output_range_max: float = 0.0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.ENVELOPE_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<HHHHBBiHiI3I5IIB3xIff",
            self.attack,
            self.attack_variance,
            self.decay,
            self.decay_variance,
            self.sustain,
            self.sustain_variance,
            self.hold,
            self.hold_variance,
            self.release,
            self.release_variance,
            rel_hash(self.attack_curve),
            rel_hash(self.decay_curve),
            rel_hash(self.release_curve),
            rel_hash(self.attack_variable),
            rel_hash(self.decay_variable),
            rel_hash(self.sustain_variable),
            rel_hash(self.hold_variable),
            rel_hash(self.release_variable),
            rel_hash(self.child_sound),
            self.mode,
            rel_hash(self.output_variable),
            self.output_range_min,
            self.output_range_max,
        )

    def hash_table_offsets(self) -> list[int]:
        return [56]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.child_sound)]


@dataclass(slots=True)
class Dat54TwinLoopSound(Dat54Sound):
    min_swap_time: int = 0
    max_swap_time: int = 0
    min_crossfade_time: int = 0
    max_crossfade_time: int = 0
    crossfade_curve: RelHashLike = 0
    min_swap_time_variable: RelHashLike = 0
    max_swap_time_variable: RelHashLike = 0
    min_crossfade_time_variable: RelHashLike = 0
    max_crossfade_time_variable: RelHashLike = 0
    child_sounds: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.TWIN_LOOP_SOUND)

    def sound_payload_bytes(self) -> bytes:
        count = checked_count(self.child_sounds, 2, "TwinLoopSound child_sounds")
        return struct.pack(
            "<HHHH5IB",
            self.min_swap_time,
            self.max_swap_time,
            self.min_crossfade_time,
            self.max_crossfade_time,
            rel_hash(self.crossfade_curve),
            rel_hash(self.min_swap_time_variable),
            rel_hash(self.max_swap_time_variable),
            rel_hash(self.min_crossfade_time_variable),
            rel_hash(self.max_crossfade_time_variable),
            count,
        ) + b"".join(struct.pack("<I", rel_hash(sound)) for sound in self.child_sounds)

    def hash_table_offsets(self) -> list[int]:
        return [29 + index * 4 for index in range(len(self.child_sounds))]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(sound) for sound in self.child_sounds]


@dataclass(slots=True)
class Dat54SpeechSound(Dat54Sound):
    last_variation: int = 1
    dynamic_field_name: RelHashLike = 0
    voice_name: RelHashLike = 0
    context_name: str = ""

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.SPEECH_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<III",
            self.last_variation,
            rel_hash(self.dynamic_field_name),
            rel_hash(self.voice_name),
        ) + _text_u8(self.context_name, "SpeechSound context_name")


@dataclass(slots=True)
class Dat54OnStopSound(Dat54Sound):
    child_sound: RelHashLike = 0
    stop_sound: RelHashLike = 0
    finished_sound: RelHashLike = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.ON_STOP_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<III",
            rel_hash(self.child_sound),
            rel_hash(self.stop_sound),
            rel_hash(self.finished_sound),
        )

    def hash_table_offsets(self) -> list[int]:
        return [0, 4, 8]

    def sound_hashes(self) -> list[int]:
        return [
            rel_hash(self.child_sound),
            rel_hash(self.stop_sound),
            rel_hash(self.finished_sound),
        ]


@dataclass(slots=True)
class Dat54RetriggeredOverlappedSound(Dat54Sound):
    loop_count: int = -1
    loop_count_variance: int = 0
    delay_time: int = 0
    delay_time_variance: int = 0
    loop_count_variable: RelHashLike = 0
    delay_time_variable: RelHashLike = 0
    start_sound: RelHashLike = 0
    retrigger_sound: RelHashLike = 0
    stop_sound: RelHashLike = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.RETRIGGERED_OVERLAPPED_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<hHHH5I",
            self.loop_count,
            self.loop_count_variance,
            self.delay_time,
            self.delay_time_variance,
            rel_hash(self.loop_count_variable),
            rel_hash(self.delay_time_variable),
            rel_hash(self.start_sound),
            rel_hash(self.retrigger_sound),
            rel_hash(self.stop_sound),
        )

    def hash_table_offsets(self) -> list[int]:
        return [16, 20, 24]

    def sound_hashes(self) -> list[int]:
        return [
            rel_hash(self.start_sound),
            rel_hash(self.retrigger_sound),
            rel_hash(self.stop_sound),
        ]


@dataclass(slots=True)
class Dat54CrossfadeSound(Dat54Sound):
    near_sound: RelHashLike = 0
    far_sound: RelHashLike = 0
    mode: int = 0
    min_distance: float = -1.0
    max_distance: float = -1.0
    hysteresis: float = 0.0
    crossfade_curve: RelHashLike = 0
    distance_variable: RelHashLike = 0
    min_distance_variable: RelHashLike = 0
    max_distance_variable: RelHashLike = 0
    hysteresis_variable: RelHashLike = 0
    crossfade_variable: RelHashLike = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.CROSSFADE_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<IIBfff6I",
            rel_hash(self.near_sound),
            rel_hash(self.far_sound),
            self.mode,
            self.min_distance,
            self.max_distance,
            self.hysteresis,
            rel_hash(self.crossfade_curve),
            rel_hash(self.distance_variable),
            rel_hash(self.min_distance_variable),
            rel_hash(self.max_distance_variable),
            rel_hash(self.hysteresis_variable),
            rel_hash(self.crossfade_variable),
        )

    def hash_table_offsets(self) -> list[int]:
        return [0, 4]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.near_sound), rel_hash(self.far_sound)]


@dataclass(slots=True)
class Dat54CollapsingStereoSound(Dat54Sound):
    left_sound: RelHashLike = 0
    right_sound: RelHashLike = 0
    min_distance: float = -1.0
    max_distance: float = -1.0
    min_distance_variable: RelHashLike = 0
    max_distance_variable: RelHashLike = 0
    crossfade_override_variable: RelHashLike = 0
    frontend_left_pan_variable: RelHashLike = 0
    frontend_right_pan_variable: RelHashLike = 0
    position_relative_pan_damping: float = 1.0
    position_relative_pan_damping_variable: RelHashLike = 0
    mode: int = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.COLLAPSING_STEREO_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack(
            "<IIff5IfIB",
            rel_hash(self.left_sound),
            rel_hash(self.right_sound),
            self.min_distance,
            self.max_distance,
            rel_hash(self.min_distance_variable),
            rel_hash(self.max_distance_variable),
            rel_hash(self.crossfade_override_variable),
            rel_hash(self.frontend_left_pan_variable),
            rel_hash(self.frontend_right_pan_variable),
            self.position_relative_pan_damping,
            rel_hash(self.position_relative_pan_damping_variable),
            self.mode,
        )

    def hash_table_offsets(self) -> list[int]:
        return [0, 4]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.left_sound), rel_hash(self.right_sound)]


@dataclass(slots=True)
class Dat54EnvironmentSound(Dat54Sound):
    channel_id: int = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.ENVIRONMENT_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack("<B", self.channel_id)


@dataclass(slots=True)
class Dat54DynamicEntitySound(Dat54Sound):
    entities: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.DYNAMIC_ENTITY_SOUND)

    def sound_payload_bytes(self) -> bytes:
        count = checked_count(self.entities, 8, "DynamicEntitySound entities")
        return bytes([count]) + b"".join(
            struct.pack("<I", rel_hash(entity)) for entity in self.entities
        )


@dataclass(slots=True)
class Dat54SequentialOverlapSound(Dat54Sound):
    delay_time: int = 0
    delay_time_variable: RelHashLike = 0
    sequence_direction: RelHashLike = 0
    child_sounds: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.SEQUENTIAL_OVERLAP_SOUND)

    def sound_payload_bytes(self) -> bytes:
        count = checked_count(
            self.child_sounds,
            254,
            "SequentialOverlapSound child_sounds",
        )
        return struct.pack(
            "<HIIB",
            self.delay_time,
            rel_hash(self.delay_time_variable),
            rel_hash(self.sequence_direction),
            count,
        ) + b"".join(struct.pack("<I", rel_hash(sound)) for sound in self.child_sounds)

    def hash_table_offsets(self) -> list[int]:
        return [11 + index * 4 for index in range(len(self.child_sounds))]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(sound) for sound in self.child_sounds]


@dataclass(slots=True)
class Dat54GranularChannel:
    container_name: RelHashLike = 0
    file_name: RelHashLike = 0

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<II",
            rel_hash(self.container_name),
            rel_hash(self.file_name),
        )


@dataclass(slots=True)
class Dat54GranularChannelSettings:
    output_buffer: int = 0
    clock_index: int = 0
    stretch_to_min_pitch: int = 0
    stretch_to_max_pitch: int = 0
    max_loop_proportion: float = 0.0

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<BBBBf",
            self.output_buffer,
            self.clock_index,
            self.stretch_to_min_pitch,
            self.stretch_to_max_pitch,
            self.max_loop_proportion,
        )


@dataclass(slots=True)
class Dat54GranularSound(Dat54Sound):
    wave_slot_index: int = 0
    channels: list[Dat54GranularChannel] = field(default_factory=list)
    channel_settings: list[Dat54GranularChannelSettings] = field(default_factory=list)
    loop_randomisation_change_rate: float = 0.01
    loop_randomisation_pitch_fraction: float = 0.05
    channel_volumes: list[int] = field(default_factory=list)
    parent_sound: RelHashLike = 0
    granular_clocks: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.GRANULAR_SOUND)

    @staticmethod
    def _six(values: list[object], factory: type[object], label: str) -> list[object]:
        if len(values) > 6:
            raise ValueError(f"{label} supports exactly six slots")
        return list(values) + [factory() for _ in range(6 - len(values))]

    def sound_payload_bytes(self) -> bytes:
        channels = self._six(
            self.channels, Dat54GranularChannel, "GranularSound channels"
        )
        settings = self._six(
            self.channel_settings,
            Dat54GranularChannelSettings,
            "GranularSound channel_settings",
        )
        volumes = list(self.channel_volumes)
        if len(volumes) > 6:
            raise ValueError("GranularSound channel_volumes supports exactly six slots")
        volumes.extend([0] * (6 - len(volumes)))
        clock_count = checked_count(
            self.granular_clocks,
            2,
            "GranularSound granular_clocks",
        )
        return (
            struct.pack("<I", self.wave_slot_index)
            + b"".join(channel.to_bytes() for channel in channels)
            + b"".join(setting.to_bytes() for setting in settings)
            + struct.pack(
                "<ff6hIB",
                self.loop_randomisation_change_rate,
                self.loop_randomisation_pitch_fraction,
                *volumes,
                rel_hash(self.parent_sound),
                clock_count,
            )
            + b"".join(
                struct.pack("<ff", minimum, maximum)
                for minimum, maximum in self.granular_clocks
            )
        )

    def hash_table_offsets(self) -> list[int]:
        return [120]

    def pack_table_offsets(self) -> list[int]:
        return [4, 12, 20, 28, 36, 44]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(self.parent_sound)]

    def audio_container_hashes(self) -> list[int]:
        channels = self._six(
            self.channels, Dat54GranularChannel, "GranularSound channels"
        )
        return [rel_hash(channel.container_name) for channel in channels]

    def audio_stream_hashes(self) -> list[int]:
        channels = self._six(
            self.channels, Dat54GranularChannel, "GranularSound channels"
        )
        return [rel_hash(channel.file_name) for channel in channels]


@dataclass(slots=True)
class Dat54SwitchSound(Dat54Sound):
    variable: RelHashLike = 0
    child_sounds: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.SWITCH_SOUND)

    def sound_payload_bytes(self) -> bytes:
        count = checked_count(self.child_sounds, 32, "SwitchSound child_sounds")
        return struct.pack("<IB", rel_hash(self.variable), count) + b"".join(
            struct.pack("<I", rel_hash(sound)) for sound in self.child_sounds
        )

    def hash_table_offsets(self) -> list[int]:
        return [5 + index * 4 for index in range(len(self.child_sounds))]

    def sound_hashes(self) -> list[int]:
        return [rel_hash(sound) for sound in self.child_sounds]


@dataclass(slots=True)
class Dat54VariablePrintValueSound(Dat54Sound):
    variable: RelHashLike = 0
    message: str = ""

    def __post_init__(self) -> None:
        self.type_id = int(Dat54SoundType.VARIABLE_PRINT_VALUE_SOUND)

    def sound_payload_bytes(self) -> bytes:
        return struct.pack("<I", rel_hash(self.variable)) + _text_u8(
            self.message,
            "VariablePrintValueSound message",
        )


__all__ = [
    "Dat54CollapsingStereoSound",
    "Dat54CrossfadeSound",
    "Dat54DynamicEntitySound",
    "Dat54EnvelopeSound",
    "Dat54EnvironmentSound",
    "Dat54GranularChannel",
    "Dat54GranularChannelSettings",
    "Dat54GranularSound",
    "Dat54OnStopSound",
    "Dat54RetriggeredOverlappedSound",
    "Dat54SequentialOverlapSound",
    "Dat54SpeechSound",
    "Dat54SwitchSound",
    "Dat54TwinLoopSound",
    "Dat54VariablePrintValueSound",
]
