from __future__ import annotations

import colorsys
import re
from collections.abc import Sequence
from typing import TypeAlias

CssColor: TypeAlias = str | int | Sequence[float | int]
RGB8: TypeAlias = tuple[int, int, int]
RGBA8: TypeAlias = tuple[int, int, int, int]
RGBUnit: TypeAlias = tuple[float, float, float]
RGBAUnit: TypeAlias = tuple[float, float, float, float]


CSS_NAMED_COLORS: dict[str, RGBA8] = {
    "transparent": (0, 0, 0, 0),
    "black": (0, 0, 0, 255),
    "silver": (192, 192, 192, 255),
    "gray": (128, 128, 128, 255),
    "grey": (128, 128, 128, 255),
    "white": (255, 255, 255, 255),
    "maroon": (128, 0, 0, 255),
    "red": (255, 0, 0, 255),
    "purple": (128, 0, 128, 255),
    "fuchsia": (255, 0, 255, 255),
    "magenta": (255, 0, 255, 255),
    "green": (0, 128, 0, 255),
    "lime": (0, 255, 0, 255),
    "olive": (128, 128, 0, 255),
    "yellow": (255, 255, 0, 255),
    "navy": (0, 0, 128, 255),
    "blue": (0, 0, 255, 255),
    "teal": (0, 128, 128, 255),
    "aqua": (0, 255, 255, 255),
    "cyan": (0, 255, 255, 255),
    "orange": (255, 165, 0, 255),
    "pink": (255, 192, 203, 255),
    "hotpink": (255, 105, 180, 255),
    "brown": (165, 42, 42, 255),
    "gold": (255, 215, 0, 255),
    "violet": (238, 130, 238, 255),
}


_FUNCTION_RE = re.compile(r"^(rgba?|hsla?)\((.*)\)$", re.IGNORECASE)


def _clamp_byte(value: float | int) -> int:
    return max(0, min(255, int(round(float(value)))))


def _clamp_unit(value: float | int) -> float:
    return max(0.0, min(1.0, float(value)))


def _alpha_byte(value: str | float | int) -> int:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            return _clamp_byte(float(text[:-1]) * 255.0 / 100.0)
        number = float(text)
    else:
        number = float(value)
    if 0.0 <= number <= 1.0:
        return _clamp_byte(number * 255.0)
    return _clamp_byte(number)


def _rgb_component(value: str | float | int) -> int:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            return _clamp_byte(float(text[:-1]) * 255.0 / 100.0)
        return _clamp_byte(float(text))
    number = float(value)
    if 0.0 <= number <= 1.0:
        return _clamp_byte(number * 255.0)
    return _clamp_byte(number)


def _split_function_args(text: str) -> list[str]:
    normalized = text.replace(",", " ")
    if "/" in normalized:
        before, after = normalized.split("/", 1)
        return [*before.split(), *after.split()]
    return normalized.split()


def _parse_hex(text: str) -> RGBA8:
    value = text[1:]
    if len(value) == 3:
        r, g, b = (int(component * 2, 16) for component in value)
        return (r, g, b, 255)
    if len(value) == 4:
        r, g, b, a = (int(component * 2, 16) for component in value)
        return (r, g, b, a)
    if len(value) == 6:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255)
    if len(value) == 8:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), int(value[6:8], 16))
    raise ValueError(f"invalid CSS hex color: {text!r}")


def _parse_hue(value: str) -> float:
    text = value.strip().lower()
    if text.endswith("deg"):
        return float(text[:-3]) % 360.0
    if text.endswith("turn"):
        return (float(text[:-4]) * 360.0) % 360.0
    if text.endswith("rad"):
        return (float(text[:-3]) * 57.29577951308232) % 360.0
    return float(text) % 360.0


def _percentage_unit(value: str) -> float:
    text = value.strip()
    if not text.endswith("%"):
        raise ValueError(f"expected percentage component, got {value!r}")
    return _clamp_unit(float(text[:-1]) / 100.0)


def _parse_function(text: str) -> RGBA8:
    match = _FUNCTION_RE.match(text)
    if match is None:
        raise ValueError(f"invalid CSS color function: {text!r}")
    name = match.group(1).lower()
    parts = _split_function_args(match.group(2))
    if name in {"rgb", "rgba"}:
        if len(parts) not in {3, 4}:
            raise ValueError(f"{name}() expects 3 color components and optional alpha")
        alpha = _alpha_byte(parts[3]) if len(parts) == 4 else 255
        return (_rgb_component(parts[0]), _rgb_component(parts[1]), _rgb_component(parts[2]), alpha)
    if len(parts) not in {3, 4}:
        raise ValueError(f"{name}() expects hue, saturation, lightness and optional alpha")
    hue = _parse_hue(parts[0]) / 360.0
    saturation = _percentage_unit(parts[1])
    lightness = _percentage_unit(parts[2])
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    alpha = _alpha_byte(parts[3]) if len(parts) == 4 else 255
    return (_clamp_byte(r * 255.0), _clamp_byte(g * 255.0), _clamp_byte(b * 255.0), alpha)


def parse_css_rgba(value: CssColor) -> RGBA8:
    """Parse a CSS-like color into 8-bit RGBA.

    Accepted string forms include named colors, ``#rgb``, ``#rgba``,
    ``#rrggbb``, ``#rrggbbaa``, ``rgb(...)``, ``rgba(...)``, ``hsl(...)`` and
    ``hsla(...)``. Integer input is treated as GTA-style ``0xAARRGGBB``.
    Numeric sequences accept RGB/RGBA values either in 0-1 or 0-255 range.
    """
    if isinstance(value, int):
        return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF, (value >> 24) & 0xFF)
    if isinstance(value, str):
        text = value.strip()
        lowered = text.lower()
        if lowered in CSS_NAMED_COLORS:
            return CSS_NAMED_COLORS[lowered]
        if lowered.startswith("#"):
            return _parse_hex(lowered)
        if lowered.startswith("0x"):
            return parse_css_rgba(int(lowered, 16))
        if _FUNCTION_RE.match(text):
            return _parse_function(text)
        parts = text.replace(",", " ").split()
        if len(parts) in {3, 4}:
            alpha = _alpha_byte(parts[3]) if len(parts) == 4 else 255
            return (_rgb_component(parts[0]), _rgb_component(parts[1]), _rgb_component(parts[2]), alpha)
        raise ValueError(f"invalid CSS color: {value!r}")
    parts = tuple(value)
    if len(parts) not in {3, 4}:
        raise ValueError(f"color sequence expects 3 or 4 components, got {len(parts)}")
    alpha = _alpha_byte(parts[3]) if len(parts) == 4 else 255
    return (_rgb_component(parts[0]), _rgb_component(parts[1]), _rgb_component(parts[2]), alpha)


def parse_css_rgb(value: CssColor) -> RGB8:
    r, g, b, _a = parse_css_rgba(value)
    return (r, g, b)


def parse_css_rgba_unit(value: CssColor) -> RGBAUnit:
    r, g, b, a = parse_css_rgba(value)
    return (r / 255.0, g / 255.0, b / 255.0, a / 255.0)


def parse_css_rgb_unit(value: CssColor) -> RGBUnit:
    r, g, b, _a = parse_css_rgba_unit(value)
    return (r, g, b)


def parse_css_argb(value: CssColor) -> int:
    r, g, b, a = parse_css_rgba(value)
    return (a << 24) | (r << 16) | (g << 8) | b


__all__ = [
    "CSS_NAMED_COLORS",
    "CssColor",
    "RGB8",
    "RGBA8",
    "RGBUnit",
    "RGBAUnit",
    "parse_css_argb",
    "parse_css_rgb",
    "parse_css_rgb_unit",
    "parse_css_rgba",
    "parse_css_rgba_unit",
]
