from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal, overload

import numpy as np
import numpy.typing as npt

Float32Array = npt.NDArray[np.float32]
Float64Array = npt.NDArray[np.float64]
Int64Array = npt.NDArray[np.int64]


def float64_rows(
    values: Iterable[Sequence[float]] | np.ndarray,
    columns: int,
    *,
    name: str,
) -> Float64Array:
    source = values if isinstance(values, (np.ndarray, Sequence)) else tuple(values)
    result = np.asarray(source, dtype=np.float64, copy=None)
    if result.size == 0:
        return np.empty((0, columns), dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != columns:
        raise ValueError(
            f"{name} must be an Nx{columns} array, got shape {result.shape!r}"
        )
    if not np.isfinite(result).all():
        raise ValueError(f"{name} contains non-finite values")
    return result


def int64_array(values: object, *, name: str) -> Int64Array:
    raw = np.asarray(values, copy=None)
    try:
        return raw.astype(np.int64, casting="same_value", copy=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain exact 64-bit integer values") from exc


def normalized_rows(
    values: Float64Array,
    *,
    fallback: Sequence[float],
    epsilon: float,
) -> Float64Array:
    if values.ndim != 2 or values.shape[1] != len(fallback):
        raise ValueError("vector array width must match fallback width")
    result = np.broadcast_to(
        np.asarray(fallback, dtype=np.float64), values.shape
    ).copy()
    lengths = np.linalg.vector_norm(values, axis=1, keepdims=True)
    np.divide(values, lengths, out=result, where=lengths > float(epsilon))
    return result


@overload
def tuple_rows(
    values: np.ndarray, *, columns: Literal[2]
) -> list[tuple[float, float]]: ...


@overload
def tuple_rows(
    values: np.ndarray, *, columns: Literal[3]
) -> list[tuple[float, float, float]]: ...


@overload
def tuple_rows(
    values: np.ndarray, *, columns: Literal[4]
) -> list[tuple[float, float, float, float]]: ...


def tuple_rows(values: np.ndarray, *, columns: int) -> list[tuple[float, ...]]:
    if values.ndim != 2 or values.shape[1] != columns:
        raise ValueError(f"expected an Nx{columns} array, got shape {values.shape!r}")
    return [tuple(row) for row in values.tolist()]


__all__ = [
    "Float32Array",
    "Float64Array",
    "Int64Array",
    "float64_rows",
    "int64_array",
    "normalized_rows",
    "tuple_rows",
]
