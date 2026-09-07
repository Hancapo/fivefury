from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class YcdChannelEncoding(StrEnum):
    """Binary encoding used for varying CUT body, mover and facial components."""

    RETAIL = "retail"
    RAW_FLOAT = "raw_float"


@dataclass(frozen=True, slots=True)
class YcdChannelEncodingPolicy:
    """Encoding and read-back accuracy required from authored YCD channels.

    ``RETAIL`` uses 16-bit quantization for body/mover translation and rotation,
    and facial translation, rotation and scale. Other tracks retain raw floats.
    ``RAW_FLOAT`` writes varying components as retail-supported IEEE-754 floats.
    Error bounds are optional and are checked against a binary write/read cycle.
    Component and angular limits cover integer samples and runtime subframes at
    0.25, 0.5 and 0.75, including intervals across sequence boundaries. Quaternion
    component differences treat opposite signs as the same orientation.
    """

    encoding: YcdChannelEncoding = YcdChannelEncoding.RETAIL
    maximum_error: float | None = None
    maximum_angular_error_degrees: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.encoding, YcdChannelEncoding):
            raise TypeError("encoding must be a YcdChannelEncoding")
        for name in ("maximum_error", "maximum_angular_error_degrees"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value < 0.0):
                raise ValueError(f"{name} must be finite and non-negative")

    @property
    def requires_validation(self) -> bool:
        return (
            self.maximum_error is not None
            or self.maximum_angular_error_degrees is not None
        )


__all__ = [
    "YcdChannelEncoding",
    "YcdChannelEncodingPolicy",
]
