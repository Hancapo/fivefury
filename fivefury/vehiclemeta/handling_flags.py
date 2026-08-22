from __future__ import annotations

import dataclasses
import re

_HEX_TOKEN = re.compile(r"(?:0[xX])?[0-9A-Fa-f]+")
_SYMBOLIC_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_| ]*")


@dataclasses.dataclass(slots=True, frozen=True)
class HandlingFlagValue:
    """Lossless unsigned 32-bit flag word used by handling.meta."""

    raw: int | str = 0

    def __post_init__(self) -> None:
        value = self.raw
        if isinstance(value, bool):
            object.__setattr__(self, "raw", int(value))
        elif isinstance(value, str):
            token = value.strip()
            object.__setattr__(
                self,
                "raw",
                int(token, 16) if _HEX_TOKEN.fullmatch(token) else token,
            )
        elif not isinstance(value, int):
            raise TypeError("Handling flags require an integer or hexadecimal token")

    @property
    def value(self) -> int | None:
        return self.raw if isinstance(self.raw, int) else None

    @property
    def symbolic(self) -> bool:
        return (
            isinstance(self.raw, str)
            and _SYMBOLIC_TOKEN.fullmatch(self.raw) is not None
        )

    @property
    def valid(self) -> bool:
        return self.value is not None and 0 <= self.value <= 0xFFFFFFFF

    @property
    def xml_token(self) -> str:
        if not self.valid:
            raise ValueError("Retail handling flags require an unsigned 32-bit value")
        assert self.value is not None
        return f"{self.value:X}"

    def __int__(self) -> int:
        if self.value is None:
            raise ValueError(f"Invalid handling flag token {self.raw!r}")
        return self.value

    def __str__(self) -> str:
        return self.xml_token if self.valid else str(self.raw)


def handling_flag_value(value: object) -> HandlingFlagValue | None:
    if value is None:
        return None
    if isinstance(value, HandlingFlagValue):
        return value
    if isinstance(value, (int, str)):
        return HandlingFlagValue(value)
    raise TypeError("Handling flags require an integer or hexadecimal token")


def handling_flag_problem(value: HandlingFlagValue) -> tuple[str, str] | None:
    if value.value is None:
        if value.symbolic:
            return (
                "symbolic.unsupported",
                f"Symbolic handling flag text {value.raw!r} is not supported",
            )
        return (
            "hex.malformed",
            f"Handling flag token {value.raw!r} is not hexadecimal",
        )
    if not 0 <= value.value <= 0xFFFFFFFF:
        return (
            "out_of_range",
            "Retail handling flags require a value from 0x00000000 to 0xFFFFFFFF",
        )
    return None


__all__ = ["HandlingFlagValue"]
