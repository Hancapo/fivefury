from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Iterator
from enum import IntEnum
from pathlib import Path

from ..authoring.context import BuildContext
from ..authoring.diagnostics import DiagnosticSeverity, ValidationReport
from .geometry import (
    WaterAlpha,
    WaterBounds,
    WaterCornerAlphas,
    _centered_bounds,
    _coerce_alphas,
    _coerce_bounds,
    _contains_xy,
    _grid_integer,
)

_S16_MIN = -(1 << 15)
_S16_MAX = (1 << 15) - 1
_U8_MAX = (1 << 8) - 1
_U16_MAX = (1 << 16) - 1
_FLOAT32_MAX = 3.4028234663852886e38
_WAVE_AMPLITUDE_MAX = ((1 << 16) - 1) / 255.0


class WaterQuadType(IntEnum):
    RECTANGLE = 0
    TRIANGLE_A = 1
    TRIANGLE_B = 2
    TRIANGLE_C = 3
    TRIANGLE_D = 4


def _coerce_quad_type(value: WaterQuadType | int) -> WaterQuadType | int:
    number = int(value)
    try:
        return WaterQuadType(number)
    except ValueError:
        return number


def _validate_bounds(
    report: ValidationReport,
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
    *,
    path: str,
    code: str,
) -> None:
    for name, value in (
        ("min_x", min_x),
        ("min_y", min_y),
        ("max_x", max_x),
        ("max_y", max_y),
    ):
        if not _S16_MIN <= int(value) <= _S16_MAX:
            report.issue(f"{code}.{name}.range", f"{name} must fit a signed 16-bit integer", path=f"{path}.{name}")
    if int(min_x) >= int(max_x):
        report.issue(f"{code}.x.inverted", "min_x must be lower than max_x", path=f"{path}.min_x")
    if int(min_y) >= int(max_y):
        report.issue(f"{code}.y.inverted", "min_y must be lower than max_y", path=f"{path}.min_y")


@dataclasses.dataclass(slots=True, kw_only=True)
class WaterQuad:
    min_x: int
    min_y: int
    max_x: int
    max_y: int
    z: float = 0.0
    type: WaterQuadType | int = WaterQuadType.RECTANGLE
    is_invisible: bool = False
    has_limited_depth: bool = False
    alpha_sw: int = 26
    alpha_se: int = 26
    alpha_ne: int = 26
    alpha_nw: int = 26
    no_stencil: bool = False

    def __post_init__(self) -> None:
        self.build()

    @classmethod
    def rectangle(
        cls,
        *,
        center: tuple[float, float, float],
        size: tuple[float, float],
        alpha: WaterAlpha = 26,
        invisible: bool = False,
        limited_depth: bool = False,
        no_stencil: bool = False,
    ) -> WaterQuad:
        return cls._from_center(
            center=center,
            size=size,
            shape=WaterQuadType.RECTANGLE,
            alpha=alpha,
            invisible=invisible,
            limited_depth=limited_depth,
            no_stencil=no_stencil,
        )

    @classmethod
    def triangle(
        cls,
        *,
        center: tuple[float, float, float],
        size: tuple[float, float],
        shape: WaterQuadType,
        alpha: WaterAlpha = 26,
        invisible: bool = False,
        limited_depth: bool = False,
        no_stencil: bool = False,
    ) -> WaterQuad:
        shape = WaterQuadType(shape)
        if shape is WaterQuadType.RECTANGLE:
            raise ValueError("triangle shape must be TRIANGLE_A through TRIANGLE_D")
        return cls._from_center(
            center=center,
            size=size,
            shape=shape,
            alpha=alpha,
            invisible=invisible,
            limited_depth=limited_depth,
            no_stencil=no_stencil,
        )

    @classmethod
    def _from_center(
        cls,
        *,
        center: tuple[float, float, float],
        size: tuple[float, float],
        shape: WaterQuadType,
        alpha: WaterAlpha,
        invisible: bool,
        limited_depth: bool,
        no_stencil: bool,
    ) -> WaterQuad:
        if len(center) != 3:
            raise ValueError("center must contain x, y, and z")
        min_x, min_y, max_x, max_y = _centered_bounds(center[:2], size)
        alpha_sw, alpha_se, alpha_ne, alpha_nw = _coerce_alphas(alpha)
        return cls(
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=max_y,
            z=float(center[2]),
            type=shape,
            is_invisible=invisible,
            has_limited_depth=limited_depth,
            alpha_sw=alpha_sw,
            alpha_se=alpha_se,
            alpha_ne=alpha_ne,
            alpha_nw=alpha_nw,
            no_stencil=no_stencil,
        )

    @property
    def width(self) -> int:
        return self.max_x - self.min_x

    @property
    def height(self) -> int:
        return self.max_y - self.min_y

    @property
    def center(self) -> tuple[float, float, float]:
        return (
            (self.min_x + self.max_x) * 0.5,
            (self.min_y + self.max_y) * 0.5,
            self.z,
        )

    @property
    def area(self) -> float:
        area = float(self.width * self.height)
        return area if int(self.type) == WaterQuadType.RECTANGLE else area * 0.5

    @property
    def alphas(self) -> tuple[int, int, int, int]:
        return self.alpha_sw, self.alpha_se, self.alpha_ne, self.alpha_nw

    @property
    def uses_default_alpha(self) -> bool:
        return self.alpha_sw == 0

    @alphas.setter
    def alphas(self, values: tuple[int, int, int, int]) -> None:
        self.alpha_sw, self.alpha_se, self.alpha_ne, self.alpha_nw = (
            int(value) for value in values
        )

    def corners(self) -> tuple[tuple[float, float, float], ...]:
        nw = (float(self.min_x), float(self.max_y), self.z)
        ne = (float(self.max_x), float(self.max_y), self.z)
        sw = (float(self.min_x), float(self.min_y), self.z)
        se = (float(self.max_x), float(self.min_y), self.z)
        points = {
            WaterQuadType.RECTANGLE: (sw, se, ne, nw),
            WaterQuadType.TRIANGLE_A: (sw, se, nw),
            WaterQuadType.TRIANGLE_B: (sw, ne, nw),
            WaterQuadType.TRIANGLE_C: (se, ne, nw),
            WaterQuadType.TRIANGLE_D: (sw, se, ne),
        }
        return points.get(self.type, ())

    def contains_xy(self, x: float, y: float) -> bool:
        return _contains_xy(self.corners(), x, y)

    def build(self) -> WaterQuad:
        self.min_x = int(self.min_x)
        self.min_y = int(self.min_y)
        self.max_x = int(self.max_x)
        self.max_y = int(self.max_y)
        self.z = float(self.z)
        self.type = _coerce_quad_type(self.type)
        self.is_invisible = bool(self.is_invisible)
        self.has_limited_depth = bool(self.has_limited_depth)
        self.alpha_sw = int(self.alpha_sw)
        self.alpha_se = int(self.alpha_se)
        self.alpha_ne = int(self.alpha_ne)
        self.alpha_nw = int(self.alpha_nw)
        self.no_stencil = bool(self.no_stencil)
        return self

    def validate(self, *, label: str = "water_quad") -> ValidationReport:
        errors = ValidationReport()
        _validate_bounds(
            errors,
            self.min_x,
            self.min_y,
            self.max_x,
            self.max_y,
            path=label,
            code="water.quad.bounds",
        )
        if not math.isfinite(self.z) or abs(self.z) > _FLOAT32_MAX:
            errors.issue("water.quad.z.range", "z must fit a finite 32-bit float", path=f"{label}.z")
        if int(self.type) not in WaterQuadType._value2member_map_:
            errors.issue("water.quad.type.range", "type must be between 0 and 4", path=f"{label}.type")
        for name, value in zip(
            ("alpha_sw", "alpha_se", "alpha_ne", "alpha_nw"),
            self.alphas,
            strict=True,
        ):
            if not 0 <= value <= _U8_MAX:
                errors.issue("water.quad.alpha.range", f"{name} must be between 0 and 255", path=f"{label}.{name}")
        if self.uses_default_alpha and any(self.alphas[1:]):
            errors.issue(
                "water.quad.alpha.ignored",
                "alpha_sw is zero, so the game ignores the other corner alphas",
                severity=DiagnosticSeverity.WARNING,
                path=f"{label}.alpha_sw",
            )
        return errors


@dataclasses.dataclass(slots=True, kw_only=True)
class WaterCalmingQuad:
    min_x: int
    min_y: int
    max_x: int
    max_y: int
    dampening: float = 0.0

    def __post_init__(self) -> None:
        self.build()

    @classmethod
    def rectangle(
        cls,
        *,
        center: tuple[float, float],
        size: tuple[float, float],
        dampening: float,
    ) -> WaterCalmingQuad:
        min_x, min_y, max_x, max_y = _centered_bounds(center, size)
        return cls(
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=max_y,
            dampening=dampening,
        )

    def build(self) -> WaterCalmingQuad:
        self.min_x = int(self.min_x)
        self.min_y = int(self.min_y)
        self.max_x = int(self.max_x)
        self.max_y = int(self.max_y)
        self.dampening = float(self.dampening)
        return self

    def validate(self, *, label: str = "calming_quad") -> ValidationReport:
        errors = ValidationReport()
        _validate_bounds(
            errors,
            self.min_x,
            self.min_y,
            self.max_x,
            self.max_y,
            path=label,
            code="water.calming_quad.bounds",
        )
        if not math.isfinite(self.dampening) or not 0.0 <= self.dampening < 1.0:
            errors.issue("water.calming_quad.dampening.range", "dampening must be finite and in the range [0, 1)", path=f"{label}.dampening")
        return errors


@dataclasses.dataclass(slots=True, kw_only=True)
class WaterWaveQuad:
    min_x: int
    min_y: int
    max_x: int
    max_y: int
    amplitude: float = 0.0
    direction_x: float = 0.0
    direction_y: float = 0.0

    def __post_init__(self) -> None:
        self.build()

    @classmethod
    def from_angle(
        cls,
        *,
        bounds: WaterBounds,
        amplitude: float,
        degrees: float,
    ) -> WaterWaveQuad:
        min_x, min_y, max_x, max_y = _coerce_bounds(bounds)
        radians = math.radians(float(degrees))
        return cls(
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=max_y,
            amplitude=amplitude,
            direction_x=math.cos(radians),
            direction_y=math.sin(radians),
        )

    @classmethod
    def from_center(
        cls,
        *,
        center: tuple[float, float],
        size: tuple[float, float],
        amplitude: float,
        degrees: float,
    ) -> WaterWaveQuad:
        return cls.from_angle(
            bounds=_centered_bounds(center, size),
            amplitude=amplitude,
            degrees=degrees,
        )

    @property
    def direction(self) -> tuple[float, float]:
        return self.direction_x, self.direction_y

    @direction.setter
    def direction(self, value: tuple[float, float]) -> None:
        self.direction_x, self.direction_y = (float(component) for component in value)

    def normalize_direction(self) -> WaterWaveQuad:
        length = math.hypot(self.direction_x, self.direction_y)
        if length > 0.0:
            self.direction_x /= length
            self.direction_y /= length
        return self

    def build(self) -> WaterWaveQuad:
        self.min_x = int(self.min_x)
        self.min_y = int(self.min_y)
        self.max_x = int(self.max_x)
        self.max_y = int(self.max_y)
        self.amplitude = float(self.amplitude)
        self.direction_x = float(self.direction_x)
        self.direction_y = float(self.direction_y)
        return self

    def validate(self, *, label: str = "wave_quad") -> ValidationReport:
        errors = ValidationReport()
        _validate_bounds(
            errors,
            self.min_x,
            self.min_y,
            self.max_x,
            self.max_y,
            path=label,
            code="water.wave_quad.bounds",
        )
        if (
            not math.isfinite(self.amplitude)
            or not 0.0 <= self.amplitude <= _WAVE_AMPLITUDE_MAX
        ):
            errors.issue(
                "water.wave_quad.amplitude.range",
                "amplitude must be finite and fit the game's u16/255 storage",
                path=f"{label}.amplitude",
            )
        for name, value in (
            ("direction_x", self.direction_x),
            ("direction_y", self.direction_y),
        ):
            if not math.isfinite(value) or not -1.0 <= value <= 1.0:
                errors.issue("water.wave_quad.direction.range", f"{name} must be finite and in the range [-1, 1]", path=f"{label}.{name}")
        return errors


WaterComponent = WaterQuad | WaterCalmingQuad | WaterWaveQuad


@dataclasses.dataclass(slots=True)
class WaterData:
    water_quads: list[WaterQuad] = dataclasses.field(default_factory=list)
    calming_quads: list[WaterCalmingQuad] = dataclasses.field(default_factory=list)
    wave_quads: list[WaterWaveQuad] = dataclasses.field(default_factory=list)

    @property
    def quads(self) -> list[WaterQuad]:
        return self.water_quads

    def _append_component(self, item: WaterComponent) -> None:
        if isinstance(item, WaterQuad):
            self.water_quads.append(item)
        elif isinstance(item, WaterCalmingQuad):
            self.calming_quads.append(item)
        elif isinstance(item, WaterWaveQuad):
            self.wave_quads.append(item)
        else:
            raise TypeError(f"Unsupported water component: {type(item).__name__}")

    def extend(self, items: Iterable[WaterComponent]) -> WaterData:
        for item in items:
            self._append_component(item)
        return self

    @property
    def bounds(self) -> WaterBounds | None:
        items = list(self.iter_components())
        if not items:
            return None
        return (
            min(item.min_x for item in items),
            min(item.min_y for item in items),
            max(item.max_x for item in items),
            max(item.max_y for item in items),
        )

    def surfaces_at(
        self,
        x: float,
        y: float,
        *,
        include_invisible: bool = True,
    ) -> list[WaterQuad]:
        return [
            quad
            for quad in self.water_quads
            if (include_invisible or not quad.is_invisible) and quad.contains_xy(x, y)
        ]

    def translate(
        self,
        *,
        x: int = 0,
        y: int = 0,
        z: float = 0.0,
    ) -> WaterData:
        x = _grid_integer(x, label="x translation")
        y = _grid_integer(y, label="y translation")
        z = float(z)
        if not math.isfinite(z):
            raise ValueError("z translation must be finite")
        for item in self.iter_components():
            item.min_x += x
            item.max_x += x
            item.min_y += y
            item.max_y += y
        for quad in self.water_quads:
            quad.z += z
        return self

    def build(self) -> WaterData:
        for item in self.iter_components():
            item.build()
        return self

    def iter_components(self) -> Iterator[WaterComponent]:
        yield from self.water_quads
        yield from self.calming_quads
        yield from self.wave_quads

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        del context
        errors = ValidationReport()
        for name, items in (
            ("water_quads", self.water_quads),
            ("calming_quads", self.calming_quads),
            ("wave_quads", self.wave_quads),
        ):
            if len(items) > _U16_MAX:
                errors.issue("water.section.capacity", f"{name} cannot contain more than {_U16_MAX} items", path=name)
        for index, quad in enumerate(self.water_quads):
            errors.extend(quad.validate(label=f"water_quads[{index}]"))
        for index, quad in enumerate(self.calming_quads):
            errors.extend(quad.validate(label=f"calming_quads[{index}]"))
        for index, quad in enumerate(self.wave_quads):
            errors.extend(quad.validate(label=f"wave_quads[{index}]"))
        return errors

    def to_xml_bytes(self, *, validate: bool = True) -> bytes:
        from .io import build_water_xml

        return build_water_xml(self, validate=validate)

    def to_bytes(self, *, validate: bool = True) -> bytes:
        return self.to_xml_bytes(validate=validate)

    def save(self, path: str | Path, *, validate: bool = True) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.to_xml_bytes(validate=validate))
        return destination

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> WaterData:
        from .io import read_water

        return read_water(source)

    @classmethod
    def from_bytes(cls, source: bytes | str | Path) -> WaterData:
        return cls.from_xml(source)


def coerce_water_data(
    value: WaterData
    | WaterComponent
    | list[WaterComponent]
    | tuple[WaterComponent, ...],
) -> WaterData:
    if isinstance(value, WaterData):
        return value
    data = WaterData()
    if isinstance(value, (list, tuple)):
        for item in value:
            data._append_component(item)
    else:
        data._append_component(value)
    return data


__all__ = [
    "WaterAlpha",
    "WaterBounds",
    "WaterCalmingQuad",
    "WaterComponent",
    "WaterCornerAlphas",
    "WaterData",
    "WaterQuad",
    "WaterQuadType",
    "WaterWaveQuad",
    "coerce_water_data",
]
