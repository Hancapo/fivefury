from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .enums import (
    Dat15MixModuleInput,
    Dat15RelType,
    Dat15VolumeInvert,
    RelTriState,
)
from .limits import checked_count
from .model import NamedRelItem, RelHashLike, rel_hash


def rel_tristate(flags: int, field_id: int) -> RelTriState:
    field = int(field_id)
    if not 0 <= field < 16:
        raise ValueError(
            f"REL tri-state field ID must be between 0 and 15, got {field}"
        )
    return RelTriState((int(flags) >> (field * 2)) & 0x03)


def replace_rel_tristate(
    flags: int,
    field_id: int,
    state: RelTriState | int,
) -> int:
    field = int(field_id)
    value = int(state)
    if not 0 <= field < 16:
        raise ValueError(
            f"REL tri-state field ID must be between 0 and 15, got {field}"
        )
    if not 0 <= value <= 3:
        raise ValueError(f"REL tri-state value must fit in 2 bits, got {value}")
    shift = field * 2
    return ((int(flags) & ~(0x03 << shift)) | (value << shift)) & 0xFFFFFFFF


@dataclass(slots=True)
class Dat15RelItem(NamedRelItem):
    flags: int = 0xAAAAAAAA


@dataclass(slots=True)
class Dat15MixCategory:
    name: RelHashLike = 0
    volume: int = 0
    volume_invert: Dat15VolumeInvert | int = Dat15VolumeInvert.INVERT
    lpf_cutoff: int = 0
    hpf_cutoff: int = 0
    pitch: int = 0
    frequency: float = 0.0
    pitch_invert: Dat15VolumeInvert | int = Dat15VolumeInvert.INVERT
    rolloff: float = 0.0

    STRUCT = struct.Struct("<IhBHHhfBf")

    def to_bytes(self) -> bytes:
        return self.STRUCT.pack(
            rel_hash(self.name),
            self.volume,
            int(self.volume_invert),
            self.lpf_cutoff,
            self.hpf_cutoff,
            self.pitch,
            self.frequency,
            int(self.pitch_invert),
            self.rolloff,
        )


@dataclass(slots=True)
class Dat15MixerPatch(Dat15RelItem):
    fade_in: int = 0
    fade_out: int = 0
    pre_delay: float = 0.0
    duration: float = 0.0
    apply_factor_curve: RelHashLike = 219049753
    apply_variable: RelHashLike = 3898985960
    apply_smooth_rate: float = 0.0
    mix_categories: list[Dat15MixCategory] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.MIXER_PATCH)

    def to_data(self) -> bytes:
        count = checked_count(self.mix_categories, 32, "DAT15 mixer patch categories")
        return (
            self.typed_name_header_bytes()
            + struct.pack(
                "<HHffIIfB",
                self.fade_in,
                self.fade_out,
                self.pre_delay,
                self.duration,
                rel_hash(self.apply_factor_curve),
                rel_hash(self.apply_variable),
                self.apply_smooth_rate,
                count,
            )
            + b"".join(category.to_bytes() for category in self.mix_categories)
        )


@dataclass(slots=True)
class Dat15SceneStateEntry:
    name: RelHashLike = 0
    scene: RelHashLike = 0

    def to_bytes(self) -> bytes:
        return struct.pack("<II", rel_hash(self.name), rel_hash(self.scene))


@dataclass(slots=True)
class Dat15SceneState(Dat15RelItem):
    states: list[Dat15SceneStateEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.SCENE_STATE)

    def to_data(self) -> bytes:
        count = checked_count(self.states, 8, "DAT15 scene states")
        return (
            self.typed_name_header_bytes()
            + bytes([count])
            + b"".join(state.to_bytes() for state in self.states)
        )


@dataclass(slots=True)
class Dat15PatchGroup:
    patch: RelHashLike = 0
    mix_group: RelHashLike = 0

    def to_bytes(self) -> bytes:
        return struct.pack("<II", rel_hash(self.patch), rel_hash(self.mix_group))


@dataclass(slots=True)
class Dat15MixerScene(Dat15RelItem):
    reference_count: int = 0
    patch_groups: list[Dat15PatchGroup] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.MIXER_SCENE)

    def to_data(self) -> bytes:
        count = checked_count(self.patch_groups, 16, "DAT15 scene patch groups")
        return (
            self.typed_name_header_bytes()
            + struct.pack("<iB", self.reference_count, count)
            + b"".join(group.to_bytes() for group in self.patch_groups)
        )


@dataclass(slots=True)
class Dat15MixGroup(Dat15RelItem):
    reference_count: int = 0
    fade_time: float = 0.0
    category_map: RelHashLike = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.MIX_GROUP)

    def to_data(self) -> bytes:
        return self.typed_name_header_bytes() + struct.pack(
            "<ifI",
            self.reference_count,
            self.fade_time,
            rel_hash(self.category_map),
        )


@dataclass(slots=True)
class Dat15MixGroupList(Dat15RelItem):
    mix_groups: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.MIX_GROUP_LIST)

    def to_data(self) -> bytes:
        count = checked_count(self.mix_groups, 255, "DAT15 mix groups")
        return (
            self.typed_name_header_bytes()
            + bytes([count])
            + b"".join(struct.pack("<I", rel_hash(group)) for group in self.mix_groups)
        )


@dataclass(slots=True)
class Dat15DynamicMixModuleSettings(Dat15RelItem):
    fade_in: int = 0
    fade_out: int = 0
    apply_variable: RelHashLike = 3898985960
    duration: float = 0.0
    module_type_settings: RelHashLike = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.DYNAMIC_MIX_MODULE_SETTINGS)

    def to_data(self) -> bytes:
        return self.typed_name_header_bytes() + struct.pack(
            "<HHIfI",
            self.fade_in,
            self.fade_out,
            rel_hash(self.apply_variable),
            self.duration,
            rel_hash(self.module_type_settings),
        )


@dataclass(slots=True)
class Dat15SceneVariableModuleSettings(Dat15RelItem):
    scene_variable: RelHashLike = 3898985960
    input_output_curve: RelHashLike = 219049753
    input: Dat15MixModuleInput | int = Dat15MixModuleInput.NONE
    scale_min: float = 0.0
    scale_max: float = 10.0

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.SCENE_VARIABLE_MODULE_SETTINGS)

    def to_data(self) -> bytes:
        return self.typed_name_header_bytes() + struct.pack(
            "<IIBff",
            rel_hash(self.scene_variable),
            rel_hash(self.input_output_curve),
            int(self.input),
            self.scale_min,
            self.scale_max,
        )


@dataclass(slots=True)
class Dat15SceneTransitionModuleSettings(Dat15RelItem):
    input: Dat15MixModuleInput | int = Dat15MixModuleInput.NONE
    threshold: float = 0.0
    transition: RelHashLike = 3817852694

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.SCENE_TRANSITION_MODULE_SETTINGS)

    def to_data(self) -> bytes:
        return self.typed_name_header_bytes() + struct.pack(
            "<BfI",
            int(self.input),
            self.threshold,
            rel_hash(self.transition),
        )


@dataclass(slots=True)
class Dat15VehicleCollisionModuleSettings(Dat15RelItem):
    input: Dat15MixModuleInput | int = Dat15MixModuleInput.NONE
    transition: RelHashLike = 3817852694

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.VEHICLE_COLLISION_MODULE_SETTINGS)

    def to_data(self) -> bytes:
        return self.typed_name_header_bytes() + struct.pack(
            "<BI",
            int(self.input),
            rel_hash(self.transition),
        )


@dataclass(slots=True)
class Dat15MixGroupCategoryMapEntry:
    category: RelHashLike = 0
    parent: RelHashLike = 0

    def to_bytes(self) -> bytes:
        return struct.pack("<II", rel_hash(self.category), rel_hash(self.parent))


@dataclass(slots=True)
class Dat15MixGroupCategoryMap(Dat15RelItem):
    entries: list[Dat15MixGroupCategoryMapEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat15RelType.MIX_GROUP_CATEGORY_MAP)

    def to_data(self) -> bytes:
        count = checked_count(self.entries, 1024, "DAT15 mix group map entries")
        return (
            self.typed_name_header_bytes()
            + struct.pack("<H", count)
            + b"".join(entry.to_bytes() for entry in self.entries)
        )


__all__ = [
    "Dat15DynamicMixModuleSettings",
    "Dat15MixCategory",
    "Dat15MixGroup",
    "Dat15MixGroupCategoryMap",
    "Dat15MixGroupCategoryMapEntry",
    "Dat15MixGroupList",
    "Dat15MixerPatch",
    "Dat15MixerScene",
    "Dat15PatchGroup",
    "Dat15RelItem",
    "Dat15SceneState",
    "Dat15SceneStateEntry",
    "Dat15SceneTransitionModuleSettings",
    "Dat15SceneVariableModuleSettings",
    "Dat15VehicleCollisionModuleSettings",
    "rel_tristate",
    "replace_rel_tristate",
]
