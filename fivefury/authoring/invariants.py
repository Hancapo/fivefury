from __future__ import annotations

from ..binary import fits_unsigned
from ..vector import Vector3
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
    minimum: Vector3,
    maximum: Vector3,
    *,
    code: str,
    path: str,
) -> None:
    if not isinstance(minimum, Vector3) or not isinstance(maximum, Vector3):
        raise TypeError("AABB bounds must be Vector3 values")
    if not minimum.is_finite or not maximum.is_finite:
        report.issue(f"{code}.non_finite", f"{path} contains non-finite values", path=path)
    elif (
        minimum.x > maximum.x
        or minimum.y > maximum.y
        or minimum.z > maximum.z
    ):
        report.issue(f"{code}.inverted", f"{path} is inverted", path=path)


__all__ = ["check_finite_aabb", "check_unsigned"]
