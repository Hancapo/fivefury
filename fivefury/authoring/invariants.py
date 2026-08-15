from __future__ import annotations

import math
from collections.abc import Sequence

from ..binary import fits_unsigned
from .diagnostics import ValidationReport


def check_unsigned(
    report: ValidationReport,
    value: int,
    bits: int,
    *,
    code: str,
    path: str,
) -> None:
    if not fits_unsigned(value, bits):
        report.issue(code, f"{path} is outside the uint{bits} range", path=path)


def check_finite_aabb(
    report: ValidationReport,
    minimum: Sequence[float],
    maximum: Sequence[float],
    *,
    code: str,
    path: str,
) -> None:
    if not all(math.isfinite(value) for value in (*minimum, *maximum)):
        report.issue(f"{code}.non_finite", f"{path} contains non-finite values", path=path)
    elif any(minimum[axis] > maximum[axis] for axis in range(3)):
        report.issue(f"{code}.inverted", f"{path} is inverted", path=path)


__all__ = ["check_finite_aabb", "check_unsigned"]
