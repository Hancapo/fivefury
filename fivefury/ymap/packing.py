from __future__ import annotations

from ..colors import CssColor, parse_css_rgb


def clamp_byte(value: float | int) -> int:
    return max(0, min(255, int(round(value))))


def clamp_ushort(value: float | int) -> int:
    return max(0, min(65535, int(round(value))))


def pack_rgbi(colour: tuple[int, int, int] | CssColor, intensity: int) -> int:
    r, g, b = parse_css_rgb(colour)
    return r | (g << 8) | (b << 16) | (clamp_byte(intensity) << 24)


def unpack_rgbi(value: int) -> tuple[tuple[int, int, int], int]:
    return ((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF), (value >> 24) & 0xFF)


def pack_lod_light_u8(value: float | int, value_range: float) -> int:
    return clamp_byte(float(value) * (255.0 / float(value_range)))


def unpack_lod_light_u8(value: int, value_range: float) -> float:
    return (int(value) & 0xFF) * (float(value_range) / 255.0)


__all__ = [
    "clamp_byte",
    "clamp_ushort",
    "pack_lod_light_u8",
    "pack_rgbi",
    "unpack_lod_light_u8",
    "unpack_rgbi",
]
