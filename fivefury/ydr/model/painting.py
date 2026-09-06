from __future__ import annotations

import enum
from collections.abc import Iterator, Sequence

from ...colors import parse_css_rgba_unit
from ..build_types import YdrMeshInput
from .geometry import YdrMesh, YdrModel

Color4 = tuple[float, float, float, float]
_PaintableMesh = YdrMesh | YdrMeshInput
_Paintable = _PaintableMesh | YdrModel


def _vertex_count(mesh: _PaintableMesh) -> int:
    return len(mesh.positions)


def _set_colours(
    mesh: _PaintableMesh,
    channel: int,
    colours: list[Color4],
) -> None:
    if channel == 0:
        if isinstance(mesh, YdrMesh):
            mesh.colours0 = colours
        else:
            object.__setattr__(mesh, "colours0", colours)
    else:
        if isinstance(mesh, YdrMesh):
            mesh.colours1 = colours
        else:
            object.__setattr__(mesh, "colours1", colours)


def _get_colours(mesh: _PaintableMesh, channel: int) -> list[Color4]:
    source = mesh.colours0 if channel == 0 else mesh.colours1
    if source is None:
        return [(0.0, 0.0, 0.0, 1.0)] * _vertex_count(mesh)
    return [tuple(c) for c in source]


class ColorChannel(enum.IntEnum):
    R = 0
    G = 1
    B = 2
    A = 3
    RG = 10
    RGB = 11
    RGBA = 12
    GA = 13
    BA = 14
    RGA = 15
    GBA = 16
    RBA = 17


_CHANNEL_INDICES: dict[ColorChannel, tuple[int, ...]] = {
    ColorChannel.R: (0,),
    ColorChannel.G: (1,),
    ColorChannel.B: (2,),
    ColorChannel.A: (3,),
    ColorChannel.RG: (0, 1),
    ColorChannel.RGB: (0, 1, 2),
    ColorChannel.RGBA: (0, 1, 2, 3),
    ColorChannel.GA: (1, 3),
    ColorChannel.BA: (2, 3),
    ColorChannel.RGA: (0, 1, 3),
    ColorChannel.GBA: (1, 2, 3),
    ColorChannel.RBA: (0, 2, 3),
}


def _apply_color(
    existing: Color4,
    values: tuple[float, ...],
    components: ColorChannel | None,
) -> Color4:
    if components is None:
        return (*values[:3], values[3] if len(values) > 3 else 1.0)
    result = list(existing)
    for i, target in enumerate(_CHANNEL_INDICES[components]):
        if i < len(values):
            result[target] = values[i]
    return (result[0], result[1], result[2], result[3])


def _iter_meshes(target: _Paintable) -> Iterator[YdrMesh | YdrMeshInput]:
    if isinstance(target, YdrModel):
        yield from target.meshes
    else:
        yield target


def paint_mesh(
    target: _Paintable,
    color: float | tuple[float, ...] | str,
    *,
    channel: int = 0,
    components: ColorChannel | None = None,
) -> None:
    """Fill all vertices with a uniform colour.

    *target* — a :class:`YdrMesh`, :class:`YdrMeshInput`, or
    :class:`YdrModel` (paints every mesh in the model).

    *color* — CSS color string, RGBA tuple, RGB tuple, or a single float for
    single-component painting. Numeric tuple values are 0-1.

    *channel* — selects ``colours0`` (0, default) or ``colours1`` (1).

    *components* — a :class:`ColorChannel` selecting which RGBA channels to
    overwrite (e.g. ``ColorChannel.R``, ``ColorChannel.GA``).  ``None``
    (default) overwrites all four channels.
    """
    for mesh in _iter_meshes(target):
        values = (
            parse_css_rgba_unit(color)
            if isinstance(color, str)
            else ((float(color),) if isinstance(color, (int, float)) else tuple(color))
        )
        if components is None:
            rgba = _apply_color((0.0, 0.0, 0.0, 1.0), values, None)
            _set_colours(mesh, channel, [rgba] * _vertex_count(mesh))
        else:
            colours = _get_colours(mesh, channel)
            colours = [_apply_color(c, values, components) for c in colours]
            _set_colours(mesh, channel, colours)


def paint_vertices(
    target: _Paintable,
    vertex_indices: Sequence[int],
    color: float | tuple[float, ...] | str,
    *,
    channel: int = 0,
    components: ColorChannel | None = None,
) -> None:
    """Paint specific vertices by index.

    *target* — a :class:`YdrMesh`, :class:`YdrMeshInput`, or
    :class:`YdrModel` (applies to every mesh in the model).

    *color* — CSS color string, RGBA tuple, RGB tuple, or a single float for
    single-component painting.

    *components* — a :class:`ColorChannel` selecting which channels to write.
    ``None`` overwrites all four.  Unmentioned channels and unlisted vertices
    keep their current colour.  If the mesh has no colours yet, unpainted
    vertices default to ``(0, 0, 0, 1)``.
    """
    for mesh in _iter_meshes(target):
        values = (
            parse_css_rgba_unit(color)
            if isinstance(color, str)
            else ((float(color),) if isinstance(color, (int, float)) else tuple(color))
        )
        colours = _get_colours(mesh, channel)
        for idx in vertex_indices:
            if idx < len(colours):
                colours[idx] = _apply_color(colours[idx], values, components)
        _set_colours(mesh, channel, colours)
