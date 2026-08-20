from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import ClassVar

from ..binary import align
from ..vector import Vector3
from .enums import Dat151ExplicitSpawnType, Dat151RelType, Dat151ZoneShape
from .limits import checked_count
from .model import RelHashLike, RelItem, rel_hash


def _padding(source: bytes, size: int) -> bytes:
    return source[:size].ljust(size, b"\x00")


@dataclass(slots=True)
class Dat151RelItem(RelItem):
    name_table_offset: int = 0

    def game_header_bytes(self) -> bytes:
        value = ((self.name_table_offset & 0xFFFFFF) << 8) | (self.type_id & 0xFF)
        return struct.pack("<I", value)


@dataclass(slots=True)
class Dat151StaticEmitterList(Dat151RelItem):
    emitters: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat151RelType.STATIC_EMITTER_LIST)

    def to_data(self) -> bytes:
        count = checked_count(self.emitters, 0xFFFFFFFF, "StaticEmitterList emitters")
        return (
            self.game_header_bytes()
            + struct.pack("<I", count)
            + b"".join(struct.pack("<I", rel_hash(value)) for value in self.emitters)
        )


@dataclass(slots=True)
class Dat151AmbientZoneList(Dat151RelItem):
    zones: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat151RelType.AMBIENT_ZONE_LIST)

    def to_data(self) -> bytes:
        count = checked_count(self.zones, 0xFFFFFFFF, "AmbientZoneList zones")
        return (
            self.game_header_bytes()
            + struct.pack("<I", count)
            + b"".join(struct.pack("<I", rel_hash(value)) for value in self.zones)
        )


@dataclass(slots=True)
class Dat151StaticEmitter(Dat151RelItem):
    STRUCT: ClassVar[struct.Struct] = struct.Struct("<III3fffiHHHHIIIfHHII4BHHff")

    flags: int = 0
    child_sound: RelHashLike = 0
    radio_station: RelHashLike = 0
    position: Vector3 = field(default_factory=Vector3)
    min_distance: float = 0.0
    max_distance: float = 0.0
    emitted_volume: int = 0
    lpf_cutoff: int = 0
    hpf_cutoff: int = 0
    rolloff_factor: int = 0
    reserved_00: int = 0
    interior: RelHashLike = 0
    room: RelHashLike = 0
    radio_station_for_score: RelHashLike = 0
    max_leakage: float = 0.0
    min_leakage_distance: int = 0
    max_leakage_distance: int = 0
    alarm: RelHashLike = 0
    on_break_one_shot: RelHashLike = 0
    max_path_depth: int = 0
    small_reverb_send: int = 0
    medium_reverb_send: int = 0
    large_reverb_send: int = 0
    min_time_minutes: int = 0
    max_time_minutes: int = 0
    broken_health: float = 0.0
    undamaged_health: float = 0.0

    def __post_init__(self) -> None:
        self.type_id = int(Dat151RelType.STATIC_EMITTER)
        if not isinstance(self.position, Vector3):
            raise TypeError("Dat151StaticEmitter.position must be a Vector3")

    def to_data(self) -> bytes:
        return self.game_header_bytes() + self.STRUCT.pack(
            self.flags,
            rel_hash(self.child_sound),
            rel_hash(self.radio_station),
            *self.position,
            self.min_distance,
            self.max_distance,
            self.emitted_volume,
            self.lpf_cutoff,
            self.hpf_cutoff,
            self.rolloff_factor,
            self.reserved_00,
            rel_hash(self.interior),
            rel_hash(self.room),
            rel_hash(self.radio_station_for_score),
            self.max_leakage,
            self.min_leakage_distance,
            self.max_leakage_distance,
            rel_hash(self.alarm),
            rel_hash(self.on_break_one_shot),
            self.max_path_depth,
            self.small_reverb_send,
            self.medium_reverb_send,
            self.large_reverb_send,
            self.min_time_minutes,
            self.max_time_minutes,
            self.broken_health,
            self.undamaged_health,
        )


@dataclass(slots=True)
class Dat151AmbientCondition:
    name: RelHashLike = 0
    value: float = 0.0
    condition_type: int = 0
    bank_loading: int = 0
    reserved: int = 0

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<IfBBH",
            rel_hash(self.name),
            self.value,
            self.condition_type,
            self.bank_loading,
            self.reserved,
        )


@dataclass(slots=True)
class Dat151AmbientRule(Dat151RelItem):
    FIXED: ClassVar[struct.Struct] = struct.Struct("<III3fIIIIiIfffHHHH6BH")

    flags: int = 0
    reserved_01: int = 0
    reserved_02: int = 0
    position: Vector3 = field(default_factory=Vector3)
    reserved_03: int = 0
    child_sound: RelHashLike = 0
    category: RelHashLike = 0
    last_play_time: int = 0
    dynamic_bank_id: int = 0
    dynamic_slot_type: int = 0
    weight: float = 0.0
    min_distance: float = 0.0
    max_distance: float = 0.0
    min_time_minutes: int = 0
    max_time_minutes: int = 0
    min_repeat_time: int = 0
    min_repeat_time_variance: int = 0
    spawn_height: int = 0
    explicit_spawn: Dat151ExplicitSpawnType | int = Dat151ExplicitSpawnType.DISABLED
    max_local_instances: int = 0
    max_global_instances: int = 0
    blockability_factor: int = 0
    max_path_depth: int = 0
    conditions: list[Dat151AmbientCondition] = field(default_factory=list)
    trailing_padding: bytes = b""

    def __post_init__(self) -> None:
        self.type_id = int(Dat151RelType.AMBIENT_RULE)
        if not isinstance(self.position, Vector3):
            raise TypeError("Dat151AmbientRule.position must be a Vector3")

    def to_data(self) -> bytes:
        count = checked_count(self.conditions, 0xFFFF, "AmbientRule conditions")
        data = bytearray(self.game_header_bytes())
        data += self.FIXED.pack(
            self.flags,
            self.reserved_01,
            self.reserved_02,
            *self.position,
            self.reserved_03,
            rel_hash(self.child_sound),
            rel_hash(self.category),
            self.last_play_time,
            self.dynamic_bank_id,
            self.dynamic_slot_type,
            self.weight,
            self.min_distance,
            self.max_distance,
            self.min_time_minutes,
            self.max_time_minutes,
            self.min_repeat_time,
            self.min_repeat_time_variance,
            self.spawn_height,
            int(self.explicit_spawn),
            self.max_local_instances,
            self.max_global_instances,
            self.blockability_factor,
            self.max_path_depth,
            count,
        )
        data += b"".join(condition.to_bytes() for condition in self.conditions)
        pad_size = align(len(data), 16) - len(data)
        data += _padding(self.trailing_padding, pad_size)
        return bytes(data)


@dataclass(slots=True)
class Dat151ZoneVolume:
    STRUCT: ClassVar[struct.Struct] = struct.Struct("<3ff3ff3fI3fIHHIII")

    center: Vector3 = field(default_factory=Vector3)
    reserved_center: float = 0.0
    size: Vector3 = field(default_factory=Vector3)
    reserved_size: float = 0.0
    post_rotation_offset: Vector3 = field(default_factory=Vector3)
    reserved_post_rotation: int = 0
    size_scale: Vector3 = field(default_factory=lambda: Vector3(1.0, 1.0, 1.0))
    reserved_scale: int = 0
    rotation_angle: int = 0
    reserved_rotation: int = 0
    reserved_04: int = 0
    reserved_05: int = 0
    reserved_06: int = 0

    def __post_init__(self) -> None:
        for name in ("center", "size", "post_rotation_offset", "size_scale"):
            if not isinstance(getattr(self, name), Vector3):
                raise TypeError(f"Dat151ZoneVolume.{name} must be a Vector3")

    def to_bytes(self) -> bytes:
        return self.STRUCT.pack(
            *self.center,
            self.reserved_center,
            *self.size,
            self.reserved_size,
            *self.post_rotation_offset,
            self.reserved_post_rotation,
            *self.size_scale,
            self.reserved_scale,
            self.rotation_angle,
            self.reserved_rotation,
            self.reserved_04,
            self.reserved_05,
            self.reserved_06,
        )


@dataclass(slots=True)
class Dat151DirectionalAmbienceRef:
    name: RelHashLike = 0
    volume: float = 0.0

    def to_bytes(self) -> bytes:
        return struct.pack("<If", rel_hash(self.name), self.volume)


@dataclass(slots=True)
class Dat151AmbientZone(Dat151RelItem):
    TAIL: ClassVar[struct.Struct] = struct.Struct("<fffIfffIIIfIIBBBB")

    flags: int = 0
    shape: Dat151ZoneShape | int = Dat151ZoneShape.BOX
    shape_reserved: bytes = b"\x00\x00\x00"
    reserved_00: int = 0
    activation: Dat151ZoneVolume = field(default_factory=Dat151ZoneVolume)
    positioning: Dat151ZoneVolume = field(default_factory=Dat151ZoneVolume)
    built_up_factor: float = 0.0
    min_ped_density: float = 0.0
    max_ped_density: float = 0.0
    ped_density_tod: RelHashLike = 0
    ped_density_scalar: float = 0.0
    max_wind_influence: float = 0.0
    min_wind_influence: float = 0.0
    wind_elevation_sounds: RelHashLike = 0
    environment_rule: RelHashLike = 0
    audio_scene: RelHashLike = 0
    underwater_creak_factor: float = 0.0
    ped_walla_settings: RelHashLike = 0
    randomised_radio_settings: RelHashLike = 0
    rules_to_play: int = 0
    water_calculation: int = 0
    rules_reserved: int = 0
    rules: list[RelHashLike] = field(default_factory=list)
    directional_reserved: bytes = b"\x00\x00\x00"
    directional_ambiences: list[Dat151DirectionalAmbienceRef] = field(default_factory=list)
    trailing_padding: bytes = b""

    def __post_init__(self) -> None:
        self.type_id = int(Dat151RelType.AMBIENT_ZONE)

    def to_data(self) -> bytes:
        rule_count = checked_count(self.rules, 0xFF, "AmbientZone rules")
        directional_count = checked_count(
            self.directional_ambiences,
            0xFF,
            "AmbientZone directional ambiences",
        )
        data = bytearray(self.game_header_bytes())
        data += struct.pack(
            "<IB3sI",
            self.flags,
            int(self.shape),
            _padding(self.shape_reserved, 3),
            self.reserved_00,
        )
        data += self.activation.to_bytes()
        data += self.positioning.to_bytes()
        data += self.TAIL.pack(
            self.built_up_factor,
            self.min_ped_density,
            self.max_ped_density,
            rel_hash(self.ped_density_tod),
            self.ped_density_scalar,
            self.max_wind_influence,
            self.min_wind_influence,
            rel_hash(self.wind_elevation_sounds),
            rel_hash(self.environment_rule),
            rel_hash(self.audio_scene),
            self.underwater_creak_factor,
            rel_hash(self.ped_walla_settings),
            rel_hash(self.randomised_radio_settings),
            self.rules_to_play,
            self.water_calculation,
            rule_count,
            self.rules_reserved,
        )
        data += b"".join(struct.pack("<I", rel_hash(value)) for value in self.rules)
        data += struct.pack(
            "<B3s", directional_count, _padding(self.directional_reserved, 3)
        )
        data += b"".join(value.to_bytes() for value in self.directional_ambiences)
        pad_size = align(len(data), 16) - len(data)
        data += _padding(self.trailing_padding, pad_size)
        return bytes(data)


@dataclass(slots=True)
class Dat151EnvironmentRule(Dat151RelItem):
    STRUCT: ClassVar[struct.Struct] = struct.Struct("<I7fiIf")

    flags: int = 0
    reverb_small: float = 0.0
    reverb_medium: float = 0.0
    reverb_large: float = 0.0
    reverb_damp: float = 0.0
    echo_delay: float = 0.0
    echo_delay_variance: float = 0.0
    echo_attenuation: float = 0.0
    echo_number: int = 0
    echo_sound_list: RelHashLike = 0
    base_echo_volume_modifier: float = 0.0

    def __post_init__(self) -> None:
        self.type_id = int(Dat151RelType.ENVIRONMENT_RULE)

    def to_data(self) -> bytes:
        return self.game_header_bytes() + self.STRUCT.pack(
            self.flags,
            self.reverb_small,
            self.reverb_medium,
            self.reverb_large,
            self.reverb_damp,
            self.echo_delay,
            self.echo_delay_variance,
            self.echo_attenuation,
            self.echo_number,
            rel_hash(self.echo_sound_list),
            self.base_echo_volume_modifier,
        )


@dataclass(slots=True)
class Dat151DirectionalAmbience(Dat151RelItem):
    STRUCT: ClassVar[struct.Struct] = struct.Struct("<5If8If3If")

    flags: int = 0
    sound_north: RelHashLike = 0
    sound_east: RelHashLike = 0
    sound_south: RelHashLike = 0
    sound_west: RelHashLike = 0
    volume_smoothing: float = 0.0
    time_to_volume: RelHashLike = 0
    occlusion_to_volume: RelHashLike = 0
    height_to_cutoff: RelHashLike = 0
    occlusion_to_cutoff: RelHashLike = 0
    built_up_factor_to_volume: RelHashLike = 0
    building_density_to_volume: RelHashLike = 0
    tree_density_to_volume: RelHashLike = 0
    water_factor_to_volume: RelHashLike = 0
    instance_volume_scale: float = 0.0
    height_above_blanket_to_volume: RelHashLike = 0
    highway_factor_to_volume: RelHashLike = 0
    vehicle_count_to_volume: RelHashLike = 0
    max_distance_out_to_sea: float = 0.0

    def __post_init__(self) -> None:
        self.type_id = int(Dat151RelType.DIRECTIONAL_AMBIENCE)

    def to_data(self) -> bytes:
        return self.game_header_bytes() + self.STRUCT.pack(
            self.flags,
            rel_hash(self.sound_north),
            rel_hash(self.sound_east),
            rel_hash(self.sound_south),
            rel_hash(self.sound_west),
            self.volume_smoothing,
            rel_hash(self.time_to_volume),
            rel_hash(self.occlusion_to_volume),
            rel_hash(self.height_to_cutoff),
            rel_hash(self.occlusion_to_cutoff),
            rel_hash(self.built_up_factor_to_volume),
            rel_hash(self.building_density_to_volume),
            rel_hash(self.tree_density_to_volume),
            rel_hash(self.water_factor_to_volume),
            self.instance_volume_scale,
            rel_hash(self.height_above_blanket_to_volume),
            rel_hash(self.highway_factor_to_volume),
            rel_hash(self.vehicle_count_to_volume),
            self.max_distance_out_to_sea,
        )


__all__ = [
    "Dat151AmbientCondition",
    "Dat151AmbientRule",
    "Dat151AmbientZone",
    "Dat151AmbientZoneList",
    "Dat151DirectionalAmbience",
    "Dat151DirectionalAmbienceRef",
    "Dat151EnvironmentRule",
    "Dat151RelItem",
    "Dat151StaticEmitter",
    "Dat151StaticEmitterList",
    "Dat151ZoneVolume",
]
