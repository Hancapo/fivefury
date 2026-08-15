from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Sequence
from enum import IntEnum, IntFlag
from pathlib import Path

from ..authoring.context import BuildContext
from ..authoring.diagnostics import ValidationReport

HeightCell = int | float
HeightGrid = Sequence[Sequence[float | None]]
_FLOAT32_MAX = 3.4028234663852886e38


class HeightMapCellFormat(IntEnum):
    UINT8 = 1
    UINT16 = 2
    FLOAT32 = 4


class HeightMapFlags(IntFlag):
    NONE = 0
    RLE_DATA = 1 << 0
    WATER_MASK = 1 << 1


class HeightMapByteOrder(IntEnum):
    BIG = 0
    LITTLE = 1


@dataclasses.dataclass(frozen=True, slots=True)
class HeightMapBounds:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @classmethod
    def from_value(
        cls,
        value: HeightMapBounds | Sequence[float],
    ) -> HeightMapBounds:
        if isinstance(value, cls):
            return value
        if len(value) != 6:
            raise ValueError(
                "bounds must contain min_x, min_y, min_z, max_x, max_y, max_z"
            )
        return cls(*(float(component) for component in value))

    @property
    def size(self) -> tuple[float, float, float]:
        return (
            self.max_x - self.min_x,
            self.max_y - self.min_y,
            self.max_z - self.min_z,
        )

    def validate(
        self,
        *,
        context: BuildContext | None = None,
        game_compatible: bool = True,
    ) -> ValidationReport:
        del context
        errors = ValidationReport()
        values = dataclasses.astuple(self)
        if not all(math.isfinite(value) for value in values):
            errors.issue("heightmap.bounds.non_finite", "bounds must contain only finite values")
        elif any(abs(value) > _FLOAT32_MAX for value in values):
            errors.issue("heightmap.bounds.float32_range", "bounds must fit finite 32-bit floats")
        if self.min_x >= self.max_x:
            errors.issue("heightmap.bounds.x.inverted", "bounds.min_x must be lower than bounds.max_x", path="min_x")
        if self.min_y >= self.max_y:
            errors.issue("heightmap.bounds.y.inverted", "bounds.min_y must be lower than bounds.max_y", path="min_y")
        if self.min_z >= self.max_z:
            errors.issue("heightmap.bounds.z.inverted", "bounds.min_z must be lower than bounds.max_z", path="min_z")
        if game_compatible and any(
            value < -16000.0 or value > 16000.0 for value in values
        ):
            errors.issue(
                "heightmap.bounds.runtime_range",
                "game height-map bounds must stay within -16000.0 and 16000.0",
            )
        return errors


def _coerce_cell_format(value: HeightMapCellFormat | int) -> HeightMapCellFormat:
    try:
        return HeightMapCellFormat(int(value))
    except ValueError as exc:
        raise ValueError("cell_format must be UINT8, UINT16, or FLOAT32") from exc


def _grid_shape(grid: HeightGrid, *, name: str) -> tuple[int, int]:
    rows = len(grid)
    if rows == 0:
        raise ValueError(f"{name} must contain at least one row")
    columns = len(grid[0])
    if columns == 0:
        raise ValueError(f"{name} rows must contain at least one cell")
    if any(len(row) != columns for row in grid):
        raise ValueError(f"{name} must be rectangular")
    return columns, rows


@dataclasses.dataclass(slots=True, kw_only=True)
class HeightMap:
    columns: int
    rows: int
    bounds: HeightMapBounds | Sequence[float]
    minimum_cells: list[HeightCell] = dataclasses.field(default_factory=list)
    maximum_cells: list[HeightCell] = dataclasses.field(default_factory=list)
    water_cells: list[bool] | None = None
    cell_format: HeightMapCellFormat = HeightMapCellFormat.UINT8
    version: int = 1
    flags: HeightMapFlags | int = HeightMapFlags.RLE_DATA
    source_byte_order: HeightMapByteOrder = HeightMapByteOrder.BIG

    def __post_init__(self) -> None:
        self.build()

    @classmethod
    def empty(
        cls,
        *,
        columns: int,
        rows: int,
        bounds: HeightMapBounds | Sequence[float],
        cell_format: HeightMapCellFormat = HeightMapCellFormat.UINT8,
        water_mask: bool = False,
    ) -> HeightMap:
        count = int(columns) * int(rows)
        return cls(
            columns=columns,
            rows=rows,
            bounds=bounds,
            minimum_cells=[0] * count,
            maximum_cells=[0] * count,
            water_cells=[False] * count if water_mask else None,
            cell_format=cell_format,
        )

    @classmethod
    def from_height_grids(
        cls,
        minimum: HeightGrid,
        maximum: HeightGrid | None = None,
        *,
        bounds: HeightMapBounds | Sequence[float],
        water: Sequence[Sequence[bool]] | None = None,
        cell_format: HeightMapCellFormat = HeightMapCellFormat.UINT8,
    ) -> HeightMap:
        columns, rows = _grid_shape(minimum, name="minimum")
        if maximum is None:
            maximum = minimum
        if _grid_shape(maximum, name="maximum") != (columns, rows):
            raise ValueError("minimum and maximum grids must have the same shape")
        if water is not None and _grid_shape(water, name="water") != (columns, rows):
            raise ValueError("water and height grids must have the same shape")

        result = cls.empty(
            columns=columns,
            rows=rows,
            bounds=bounds,
            cell_format=cell_format,
            water_mask=water is not None,
        )
        for row in range(rows):
            for column in range(columns):
                lower = minimum[row][column]
                upper = maximum[row][column]
                if lower is None and upper is None:
                    continue
                if lower is None or upper is None:
                    raise ValueError(
                        "a cell must provide both minimum and maximum heights"
                    )
                result.set_height(
                    column, row, minimum=float(lower), maximum=float(upper)
                )
                if water is not None:
                    result.set_water(column, row, bool(water[row][column]))
        return result

    @property
    def cell_count(self) -> int:
        return self.columns * self.rows

    @property
    def cell_size(self) -> tuple[float, float]:
        return (
            (self.bounds.max_x - self.bounds.min_x) / self.columns,
            (self.bounds.max_y - self.bounds.min_y) / self.rows,
        )

    @property
    def uses_rle(self) -> bool:
        return bool(int(self.flags) & int(HeightMapFlags.RLE_DATA))

    @property
    def has_water_mask(self) -> bool:
        return self.water_cells is not None

    def build(self) -> HeightMap:
        self.columns = int(self.columns)
        self.rows = int(self.rows)
        self.bounds = HeightMapBounds.from_value(self.bounds)
        self.cell_format = _coerce_cell_format(self.cell_format)
        self.version = int(self.version)
        self.flags = HeightMapFlags(int(self.flags))
        self.source_byte_order = HeightMapByteOrder(self.source_byte_order)
        self.minimum_cells = list(self.minimum_cells)
        self.maximum_cells = list(self.maximum_cells)
        if self.water_cells is not None:
            self.water_cells = [bool(value) for value in self.water_cells]
            self.flags |= HeightMapFlags.WATER_MASK
        else:
            self.flags &= ~HeightMapFlags.WATER_MASK
        return self

    def _index(self, column: int, row: int) -> int:
        column = int(column)
        row = int(row)
        if not 0 <= column < self.columns or not 0 <= row < self.rows:
            raise IndexError(
                f"height-map cell ({column}, {row}) is outside {self.columns}x{self.rows}"
            )
        return column + row * self.columns

    def world_to_cell(self, x: float, y: float) -> tuple[int, int] | None:
        if not (
            self.bounds.min_x <= x < self.bounds.max_x
            and self.bounds.min_y <= y < self.bounds.max_y
        ):
            return None
        cell_x, cell_y = self.cell_size
        return (
            math.floor((x - self.bounds.min_x) / cell_x),
            math.floor((y - self.bounds.min_y) / cell_y),
        )

    def cell_center(self, column: int, row: int) -> tuple[float, float]:
        self._index(column, row)
        cell_x, cell_y = self.cell_size
        return (
            self.bounds.min_x + (column + 0.5) * cell_x,
            self.bounds.min_y + (row + 0.5) * cell_y,
        )

    def cell_bounds(
        self,
        column: int,
        row: int,
    ) -> tuple[float, float, float, float]:
        self._index(column, row)
        cell_x, cell_y = self.cell_size
        min_x = self.bounds.min_x + column * cell_x
        min_y = self.bounds.min_y + row * cell_y
        return min_x, min_y, min_x + cell_x, min_y + cell_y

    def is_empty(self, column: int, row: int) -> bool:
        index = self._index(column, row)
        return self.minimum_cells[index] == 0 and self.maximum_cells[index] == 0

    def _quantize(self, value: float, *, maximum: bool) -> HeightCell:
        if not math.isfinite(value):
            raise ValueError("height must be finite")
        if self.cell_format is HeightMapCellFormat.FLOAT32:
            return float(value)
        limit = 255 if self.cell_format is HeightMapCellFormat.UINT8 else 65535
        normalized = (
            limit
            * (value - self.bounds.min_z)
            / (self.bounds.max_z - self.bounds.min_z)
        )
        quantized = math.ceil(normalized) if maximum else math.floor(normalized)
        return min(limit, max(0, quantized))

    def _unquantize(self, value: HeightCell) -> float:
        if self.cell_format is HeightMapCellFormat.FLOAT32:
            return float(value)
        limit = 255 if self.cell_format is HeightMapCellFormat.UINT8 else 65535
        return self.bounds.min_z + (
            (self.bounds.max_z - self.bounds.min_z) * int(value) / limit
        )

    def set_height(
        self,
        column: int,
        row: int,
        *,
        minimum: float,
        maximum: float | None = None,
    ) -> HeightMap:
        maximum = minimum if maximum is None else maximum
        if minimum > maximum:
            raise ValueError("minimum height must not exceed maximum height")
        index = self._index(column, row)
        self.minimum_cells[index] = self._quantize(minimum, maximum=False)
        self.maximum_cells[index] = self._quantize(maximum, maximum=True)
        return self

    def set_height_at(
        self,
        x: float,
        y: float,
        *,
        minimum: float,
        maximum: float | None = None,
    ) -> HeightMap:
        cell = self.world_to_cell(x, y)
        if cell is None:
            raise ValueError(f"coordinate ({x}, {y}) is outside the height-map bounds")
        return self.set_height(*cell, minimum=minimum, maximum=maximum)

    def clear_cell(self, column: int, row: int) -> HeightMap:
        index = self._index(column, row)
        empty: HeightCell = (
            0.0 if self.cell_format is HeightMapCellFormat.FLOAT32 else 0
        )
        self.minimum_cells[index] = empty
        self.maximum_cells[index] = empty
        if self.water_cells is not None:
            self.water_cells[index] = False
        return self

    def height_range(self, column: int, row: int) -> tuple[float, float] | None:
        index = self._index(column, row)
        if self.minimum_cells[index] == 0 and self.maximum_cells[index] == 0:
            return None
        return (
            self._unquantize(self.minimum_cells[index]),
            self._unquantize(self.maximum_cells[index]),
        )

    def height_range_at(self, x: float, y: float) -> tuple[float, float] | None:
        cell = self.world_to_cell(x, y)
        return None if cell is None else self.height_range(*cell)

    def height_range_in_bounds(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> tuple[float, float] | None:
        if min_x >= max_x or min_y >= max_y:
            raise ValueError("query minimums must be lower than maximums")
        cell_x, cell_y = self.cell_size
        first_column = max(
            0,
            math.floor((min_x - self.bounds.min_x) / cell_x),
        )
        first_row = max(
            0,
            math.floor((min_y - self.bounds.min_y) / cell_y),
        )
        last_column = min(
            self.columns,
            math.ceil((max_x - self.bounds.min_x) / cell_x),
        )
        last_row = min(
            self.rows,
            math.ceil((max_y - self.bounds.min_y) / cell_y),
        )
        if first_column >= last_column or first_row >= last_row:
            return None

        lower: float | None = None
        upper: float | None = None
        for row in range(first_row, last_row):
            for column in range(first_column, last_column):
                heights = self.height_range(column, row)
                if heights is None:
                    continue
                lower = heights[0] if lower is None else min(lower, heights[0])
                upper = heights[1] if upper is None else max(upper, heights[1])
        return None if lower is None or upper is None else (lower, upper)

    def set_water(self, column: int, row: int, enabled: bool = True) -> HeightMap:
        if self.water_cells is None:
            self.water_cells = [False] * self.cell_count
            self.flags |= HeightMapFlags.WATER_MASK
        self.water_cells[self._index(column, row)] = bool(enabled)
        return self

    def is_water(self, column: int, row: int) -> bool:
        return (
            self.water_cells is not None and self.water_cells[self._index(column, row)]
        )

    def set_water_at(self, x: float, y: float, enabled: bool = True) -> HeightMap:
        cell = self.world_to_cell(x, y)
        if cell is None:
            raise ValueError(f"coordinate ({x}, {y}) is outside the height-map bounds")
        return self.set_water(*cell, enabled=enabled)

    def is_water_at(self, x: float, y: float) -> bool:
        cell = self.world_to_cell(x, y)
        return cell is not None and self.is_water(*cell)

    def iter_occupied_cells(
        self,
    ) -> Iterable[tuple[int, int, tuple[float, float]]]:
        for row in range(self.rows):
            for column in range(self.columns):
                heights = self.height_range(column, row)
                if heights is not None:
                    yield column, row, heights

    def validate(
        self,
        *,
        context: BuildContext | None = None,
        game_compatible: bool = True,
    ) -> ValidationReport:
        errors = ValidationReport().extend(
            self.bounds.validate(context=context, game_compatible=game_compatible),
            path="bounds",
        )
        if not 1 <= self.columns <= 0xFFFF:
            errors.issue("heightmap.columns.range", "columns must fit an unsigned 16-bit integer", path="columns")
        if not 1 <= self.rows <= 0xFFFF:
            errors.issue("heightmap.rows.range", "rows must fit an unsigned 16-bit integer", path="rows")
        if game_compatible and not 10 <= self.columns <= 1000:
            errors.issue("heightmap.columns.runtime_range", "game height maps require between 10 and 1000 columns", path="columns")
        if game_compatible and not 10 <= self.rows <= 1000:
            errors.issue("heightmap.rows.runtime_range", "game height maps require between 10 and 1000 rows", path="rows")
        if not 0 <= self.version <= 0xFF:
            errors.issue("heightmap.version.range", "version must fit an unsigned byte", path="version")
        if game_compatible and self.version != 1:
            errors.issue("heightmap.version.runtime", "game height maps use version 1", path="version")
        if game_compatible and self.cell_format is not HeightMapCellFormat.UINT8:
            errors.issue("heightmap.cell_format.runtime", "WORLD_HEIGHTMAP_FILE requires UINT8 cells", path="cell_format")

        expected = self.cell_count
        if len(self.minimum_cells) != expected:
            errors.issue("heightmap.minimum_cells.count", f"minimum_cells must contain exactly {expected} values", path="minimum_cells")
        if len(self.maximum_cells) != expected:
            errors.issue("heightmap.maximum_cells.count", f"maximum_cells must contain exactly {expected} values", path="maximum_cells")
        if self.water_cells is not None and len(self.water_cells) != expected:
            errors.issue("heightmap.water_cells.count", f"water_cells must contain exactly {expected} values", path="water_cells")

        if len(self.minimum_cells) == expected and len(self.maximum_cells) == expected:
            limit = {
                HeightMapCellFormat.UINT8: 255,
                HeightMapCellFormat.UINT16: 65535,
            }.get(self.cell_format)
            for index, (lower, upper) in enumerate(
                zip(self.minimum_cells, self.maximum_cells, strict=True)
            ):
                if not math.isfinite(float(lower)) or not math.isfinite(float(upper)):
                    errors.issue("heightmap.cell.non_finite", f"cell {index} must contain finite values", path=f"cells[{index}]")
                    continue
                if limit is None and (
                    abs(float(lower)) > _FLOAT32_MAX or abs(float(upper)) > _FLOAT32_MAX
                ):
                    errors.issue("heightmap.cell.float32_range", f"cell {index} must fit finite 32-bit floats", path=f"cells[{index}]")
                    continue
                if limit is not None and (
                    not isinstance(lower, int)
                    or isinstance(lower, bool)
                    or not isinstance(upper, int)
                    or isinstance(upper, bool)
                    or not 0 <= lower <= limit
                    or not 0 <= upper <= limit
                ):
                    errors.issue(
                        "heightmap.cell.integer_range",
                        f"cell {index} must contain integers between 0 and {limit}",
                        path=f"cells[{index}]",
                    )
                    continue
                if lower > upper:
                    errors.issue("heightmap.cell.inverted", f"cell {index} minimum exceeds its maximum", path=f"cells[{index}]")
        if game_compatible:
            unknown_flags = int(self.flags) & ~int(
                HeightMapFlags.RLE_DATA | HeightMapFlags.WATER_MASK
            )
            if unknown_flags:
                errors.issue("heightmap.flags.unsupported", f"unsupported height-map flags: 0x{unknown_flags:X}", path="flags")
        return errors

    def to_bytes(
        self,
        *,
        rle: bool | None = None,
        byte_order: HeightMapByteOrder = HeightMapByteOrder.BIG,
        game_compatible: bool = True,
    ) -> bytes:
        from .io import build_heightmap_bytes

        return build_heightmap_bytes(
            self,
            rle=rle,
            byte_order=byte_order,
            game_compatible=game_compatible,
        )

    def save(
        self,
        destination: str | Path,
        *,
        rle: bool | None = None,
        byte_order: HeightMapByteOrder = HeightMapByteOrder.BIG,
        game_compatible: bool = True,
    ) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            self.to_bytes(
                rle=rle,
                byte_order=byte_order,
                game_compatible=game_compatible,
            )
        )
        return path

    @classmethod
    def from_bytes(
        cls, source: bytes | bytearray | memoryview | str | Path
    ) -> HeightMap:
        from .io import read_heightmap

        return read_heightmap(source)


__all__ = [
    "HeightCell",
    "HeightGrid",
    "HeightMap",
    "HeightMapBounds",
    "HeightMapByteOrder",
    "HeightMapCellFormat",
    "HeightMapFlags",
]
