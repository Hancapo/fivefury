from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .enums import Dat4ConfigType
from .limits import checked_count
from .model import NamedRelItem, RelHashLike, rel_hash


def _padding(source: bytes, size: int) -> bytes:
    return source[:size].ljust(size, b"\x00")


@dataclass(slots=True)
class Dat4ConfigItem(NamedRelItem):
    flags: int = 0xAAAAAAAA


@dataclass(slots=True)
class Dat4ConfigInt(Dat4ConfigItem):
    value: int = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat4ConfigType.INT)

    def to_data(self) -> bytes:
        return self.typed_name_header_bytes() + struct.pack("<i", self.value)


@dataclass(slots=True)
class Dat4ConfigUnsignedInt(Dat4ConfigItem):
    value: int = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat4ConfigType.UNSIGNED_INT)

    def to_data(self) -> bytes:
        return self.typed_name_header_bytes() + struct.pack("<I", self.value)


@dataclass(slots=True)
class Dat4ConfigFloat(Dat4ConfigItem):
    value: float = 0.0

    def __post_init__(self) -> None:
        self.type_id = int(Dat4ConfigType.FLOAT)

    def to_data(self) -> bytes:
        return self.typed_name_header_bytes() + struct.pack("<f", self.value)


@dataclass(slots=True)
class Dat4ConfigString(Dat4ConfigItem):
    value: str = ""
    string_padding: bytes = b""

    def __post_init__(self) -> None:
        self.type_id = int(Dat4ConfigType.STRING)

    def to_data(self) -> bytes:
        encoded = self.value.encode("ascii")
        if len(encoded) > 64:
            raise ValueError("DAT4 config strings support at most 64 ASCII bytes")
        return self.typed_name_header_bytes() + encoded + _padding(
            self.string_padding, 64 - len(encoded)
        )


@dataclass(slots=True)
class Dat4ConfigVector3(Dat4ConfigItem):
    prefix_padding: bytes = b"\x00" * 8
    value: tuple[float, float, float] = (0.0, 0.0, 0.0)
    suffix_padding: bytes = b"\x00" * 4

    def __post_init__(self) -> None:
        self.type_id = int(Dat4ConfigType.VECTOR3)

    def to_data(self) -> bytes:
        return (
            self.typed_name_header_bytes()
            + _padding(self.prefix_padding, 8)
            + struct.pack("<3f", *self.value)
            + _padding(self.suffix_padding, 4)
        )


@dataclass(slots=True)
class Dat4ConfigVariable:
    name: RelHashLike = 0
    value: float = 0.0

    def to_bytes(self) -> bytes:
        return struct.pack("<If", rel_hash(self.name), self.value)


@dataclass(slots=True)
class Dat4ConfigVariableList(Dat4ConfigItem):
    variables: list[Dat4ConfigVariable] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat4ConfigType.VARIABLE_LIST)

    def to_data(self) -> bytes:
        count = checked_count(self.variables, 0x7FFFFFFF, "DAT4 config variables")
        return (
            self.typed_name_header_bytes()
            + struct.pack("<i", count)
            + b"".join(value.to_bytes() for value in self.variables)
        )


@dataclass(slots=True)
class Dat4ConfigWaveSlot(Dat4ConfigItem):
    load_type: int = 0
    max_header_size: int = 0
    size: int = 0
    static_bank: RelHashLike = 0
    max_metadata_size: int = 0
    max_data_size: int = 0

    def __post_init__(self) -> None:
        self.type_id = int(Dat4ConfigType.WAVE_SLOT)

    def to_data(self) -> bytes:
        return self.typed_name_header_bytes() + struct.pack(
            "<iIIIII",
            self.load_type,
            self.max_header_size,
            self.size,
            rel_hash(self.static_bank),
            self.max_metadata_size,
            self.max_data_size,
        )


@dataclass(slots=True)
class Dat4ConfigWaveSlotsList(Dat4ConfigItem):
    wave_slots: list[RelHashLike] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type_id = int(Dat4ConfigType.WAVE_SLOTS_LIST)

    def to_data(self) -> bytes:
        count = checked_count(self.wave_slots, 0x7FFFFFFF, "DAT4 wave slots")
        return (
            self.typed_name_header_bytes()
            + struct.pack("<i", count)
            + b"".join(struct.pack("<I", rel_hash(value)) for value in self.wave_slots)
        )

    def hash_table_offsets(self) -> list[int]:
        return [8 + index * 4 for index in range(len(self.wave_slots))]


@dataclass(slots=True)
class Dat4ConfigErPass:
    float_value: float = 0.0
    int_value: int = 0

    def to_bytes(self) -> bytes:
        return struct.pack("<fi", self.float_value, self.int_value)


@dataclass(slots=True)
class Dat4ConfigErSettings(Dat4ConfigItem):
    room_size: float = 0.0
    room_dimensions: tuple[float, float, float] = (0.0, 0.0, 0.0)
    listener_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    all_passes: list[Dat4ConfigErPass] = field(default_factory=list)
    node_gain_matrix: list[tuple[float, float, float, float]] = field(
        default_factory=lambda: [(0.0, 0.0, 0.0, 0.0)] * 6
    )
    gain_first_order: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    gain_second_order: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    gain_third_order: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    node_lpf_first_order: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )
    node_lpf_second_order: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )
    node_lpf_third_order: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        self.type_id = int(Dat4ConfigType.ER_SETTINGS)

    def to_data(self) -> bytes:
        if len(self.node_gain_matrix) != 6:
            raise ValueError("DAT4 ER settings require exactly 6 node gain vectors")
        all_pass_count = checked_count(
            self.all_passes, 0x7FFFFFFF, "DAT4 ER all-pass filters"
        )
        first_count = checked_count(
            self.node_lpf_first_order, 0x7FFFFFFF, "DAT4 ER first-order filters"
        )
        second_count = checked_count(
            self.node_lpf_second_order, 0x7FFFFFFF, "DAT4 ER second-order filters"
        )
        third_count = checked_count(
            self.node_lpf_third_order, 0x7FFFFFFF, "DAT4 ER third-order filters"
        )
        data = bytearray(self.typed_name_header_bytes())
        data += struct.pack(
            "<f3f3fi",
            self.room_size,
            *self.room_dimensions,
            *self.listener_position,
            all_pass_count,
        )
        data += b"".join(value.to_bytes() for value in self.all_passes)
        data += b"".join(struct.pack("<4f", *value) for value in self.node_gain_matrix)
        data += struct.pack("<4f", *self.gain_first_order)
        data += struct.pack("<4f", *self.gain_second_order)
        data += struct.pack("<4f", *self.gain_third_order)
        for count, values in (
            (first_count, self.node_lpf_first_order),
            (second_count, self.node_lpf_second_order),
            (third_count, self.node_lpf_third_order),
        ):
            data += struct.pack("<i", count)
            data += b"".join(struct.pack("<4f", *value) for value in values)
        return bytes(data)


__all__ = [
    "Dat4ConfigErPass",
    "Dat4ConfigErSettings",
    "Dat4ConfigFloat",
    "Dat4ConfigInt",
    "Dat4ConfigItem",
    "Dat4ConfigString",
    "Dat4ConfigUnsignedInt",
    "Dat4ConfigVariable",
    "Dat4ConfigVariableList",
    "Dat4ConfigVector3",
    "Dat4ConfigWaveSlot",
    "Dat4ConfigWaveSlotsList",
]
