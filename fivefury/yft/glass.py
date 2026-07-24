from __future__ import annotations

import dataclasses
import enum
from collections.abc import Iterable, Sequence

Vec3 = tuple[float, float, float]
Matrix44 = tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
]


class YftGlassPaneFlag(enum.IntFlag):
    NONE = 0
    DECAL_COORDINATES = 1 << 0
    TANGENT = 1 << 1


@dataclasses.dataclass(frozen=True, slots=True)
class YftGlassVertexDeclaration:
    flags: int
    stride: int
    types: int
    component_count: int = 0

    @property
    def count(self) -> int:
        return int(self.component_count or int(self.flags).bit_count())


@dataclasses.dataclass(slots=True)
class YftGlassPane:
    position_base: Vec3 = (0.0, 0.0, 0.0)
    position_width: Vec3 = (1.0, 0.0, 0.0)
    position_height: Vec3 = (0.0, 1.0, 0.0)
    uv_min: tuple[float, float] = (0.0, 0.0)
    uv_max: tuple[float, float] = (1.0, 1.0)
    vertex_declaration: YftGlassVertexDeclaration = dataclasses.field(
        default_factory=lambda: YftGlassVertexDeclaration(
            flags=217,
            stride=44,
            types=0x7655555555996996,
        )
    )
    thickness: float = 0.013671875
    flags: YftGlassPaneFlag = YftGlassPaneFlag.TANGENT
    glass_type: int = 0
    shader_index: int = 0
    bounds_offset_front: float = 0.0
    bounds_offset_back: float = 0.0
    tangent: Vec3 = (1.0, 0.0, 0.0)


class YftVehicleGlassFlag(enum.IntFlag):
    NONE = 0
    HAS_EXPOSED_EDGES = 1 << 0
    FROM_HIGH_DETAIL_MESH = 1 << 1
    VERSION_2 = 2 << 16
    ERROR_MULTIPLE_MATERIALS = 1 << 24
    ERROR_MIXED_MATERIALS = 1 << 25
    ERROR_MULTIPLE_GEOMETRIES = 1 << 26
    ERROR_DAMAGE_SCALE_NOT_UNIT = 1 << 27
    ERROR_NO_BOUNDARY_EDGES = 1 << 28


@dataclasses.dataclass(frozen=True, slots=True)
class YftVehicleGlassSpan:
    start: int
    values: bytes

    @classmethod
    def declare(
        cls, start: int, values: bytes | bytearray | memoryview | Iterable[int]
    ) -> YftVehicleGlassSpan:
        return cls(int(start), bytes(values))

    @property
    def end(self) -> int:
        return int(self.start) + len(self.values) - 1


@dataclasses.dataclass(frozen=True, slots=True)
class YftVehicleGlassRow:
    first: YftVehicleGlassSpan | None = None
    second: YftVehicleGlassSpan | None = None

    @classmethod
    def declare(
        cls,
        start: int,
        values: bytes | bytearray | memoryview | Iterable[int],
        *,
        second_start: int | None = None,
        second_values: bytes | bytearray | memoryview | Iterable[int] = b"",
    ) -> YftVehicleGlassRow:
        second = (
            YftVehicleGlassSpan.declare(second_start, second_values)
            if second_start is not None
            else None
        )
        return cls(YftVehicleGlassSpan.declare(start, values), second)

    @classmethod
    def empty(cls) -> YftVehicleGlassRow:
        return cls()

    @property
    def width(self) -> int:
        return (
            max(
                self.first.end if self.first else -1,
                self.second.end if self.second else -1,
            )
            + 1
        )


@dataclasses.dataclass(slots=True)
class YftVehicleGlassWindow:
    component_id: int
    geometry_index: int
    rows: list[YftVehicleGlassRow] = dataclasses.field(default_factory=list)
    basis: Matrix44 = (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    data_min: float = 0.0
    data_max: float = 1.0
    flags: YftVehicleGlassFlag = YftVehicleGlassFlag.VERSION_2
    texture_scale: float = 2.0
    data_columns: int = 0
    data_rows: int = 0

    @classmethod
    def declare(
        cls,
        component_id: int,
        geometry_index: int,
        rows: Sequence[YftVehicleGlassRow],
        **kwargs,
    ) -> YftVehicleGlassWindow:
        return cls(
            component_id=int(component_id),
            geometry_index=int(geometry_index),
            rows=list(rows),
            **kwargs,
        )

    @property
    def column_count(self) -> int:
        return int(
            self.data_columns or max((row.width for row in self.rows), default=0)
        )

    @property
    def row_count(self) -> int:
        return int(self.data_rows or len(self.rows))


@dataclasses.dataclass(slots=True)
class YftVehicleGlassWindows:
    windows: list[YftVehicleGlassWindow] = dataclasses.field(default_factory=list)

    def append(self, window: YftVehicleGlassWindow) -> None:
        self.windows.append(window)


__all__ = [
    "YftGlassPane",
    "YftGlassPaneFlag",
    "YftGlassVertexDeclaration",
    "YftVehicleGlassFlag",
    "YftVehicleGlassRow",
    "YftVehicleGlassSpan",
    "YftVehicleGlassWindow",
    "YftVehicleGlassWindows",
]
