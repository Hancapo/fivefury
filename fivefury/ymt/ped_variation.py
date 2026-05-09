from __future__ import annotations

import enum
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass
from typing import Any

from . import Ymt


class PedComponent(enum.IntEnum):
    HEAD = 0
    BEARD = 1
    HAIR = 2
    UPPER = 3
    LOWER = 4
    HAND = 5
    FEET = 6
    TEETH = 7
    ACCESSORIES = 8
    TASK = 9
    DECL = 10
    JBIB = 11


_COMPONENT_ALIASES = {
    "head": PedComponent.HEAD,
    "berd": PedComponent.BEARD,
    "beard": PedComponent.BEARD,
    "hair": PedComponent.HAIR,
    "uppr": PedComponent.UPPER,
    "upper": PedComponent.UPPER,
    "lowr": PedComponent.LOWER,
    "lower": PedComponent.LOWER,
    "hand": PedComponent.HAND,
    "hands": PedComponent.HAND,
    "feet": PedComponent.FEET,
    "teef": PedComponent.TEETH,
    "teeth": PedComponent.TEETH,
    "accs": PedComponent.ACCESSORIES,
    "accessory": PedComponent.ACCESSORIES,
    "accessories": PedComponent.ACCESSORIES,
    "task": PedComponent.TASK,
    "decl": PedComponent.DECL,
    "jbib": PedComponent.JBIB,
}

_COMPONENT_FILE_STEMS = {
    PedComponent.HEAD: "head",
    PedComponent.BEARD: "berd",
    PedComponent.HAIR: "hair",
    PedComponent.UPPER: "uppr",
    PedComponent.LOWER: "lowr",
    PedComponent.HAND: "hand",
    PedComponent.FEET: "feet",
    PedComponent.TEETH: "teef",
    PedComponent.ACCESSORIES: "accs",
    PedComponent.TASK: "task",
    PedComponent.DECL: "decl",
    PedComponent.JBIB: "jbib",
}

_ROOT_COMPONENTS = ("aComponentData3", "0xE2489C4F")
_ROOT_AVAILABLE = ("availComp", "0xB29BE228")
_COMPONENT_DRAWABLES = ("aDrawblData3", "0x68AC8351")
_DRAWABLE_TEXTURES = ("aTexData", "0x4A92222A")
_DRAWABLE_CLOTH = ("clothData", "0x92E68DB3")
_CLOTH_OWNS = ("ownsCloth", "0xA893A361")
_PROP_MASK = ("propMask", "0xAECFE243")
_NUM_ALTERNATIVES = ("numAlternatives", "0xA7431FBA")


@dataclass(slots=True, frozen=True)
class PedDrawableVariation:
    component: PedComponent
    drawable_index: int
    texture_count: int
    prop_mask: int = 0
    num_alternatives: int = 0
    owns_cloth: bool = False

    @property
    def file_stem(self) -> str:
        suffix = "u"
        prop_type = (int(self.prop_mask) >> 4) & 3
        if prop_type == 1:
            suffix = "r"
        elif prop_type in {2, 3}:
            suffix = "m"
        return f"{_COMPONENT_FILE_STEMS[self.component]}_{self.drawable_index:03d}_{suffix}"


def coerce_ped_component(value: PedComponent | str | int) -> PedComponent:
    if isinstance(value, PedComponent):
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _COMPONENT_ALIASES:
            return _COMPONENT_ALIASES[key]
        if key.isdigit():
            return PedComponent(int(key))
        raise ValueError(f"Unknown ped component {value!r}")
    return PedComponent(int(value))


def iter_ped_drawables(ymt: Ymt) -> Iterator[PedDrawableVariation]:
    root = _require_ped_root(ymt)
    for component in PedComponent:
        component_data = _component_data(root, component)
        if component_data is None:
            continue
        drawables = _get(component_data, _COMPONENT_DRAWABLES, default=())
        for drawable_index, drawable in enumerate(drawables):
            textures = _get(drawable, _DRAWABLE_TEXTURES, default=())
            cloth_data = _get(drawable, _DRAWABLE_CLOTH, default={})
            yield PedDrawableVariation(
                component=component,
                drawable_index=drawable_index,
                texture_count=len(textures),
                prop_mask=int(_get(drawable, _PROP_MASK, default=0) or 0),
                num_alternatives=int(_get(drawable, _NUM_ALTERNATIVES, default=0) or 0),
                owns_cloth=bool(_get(cloth_data, _CLOTH_OWNS, default=False)),
            )


def set_ped_drawable_cloth(
    ymt: Ymt,
    component: PedComponent | str | int,
    drawable: int = 0,
    *,
    owns: bool = True,
) -> Ymt:
    root = _require_ped_root(ymt)
    component_enum = coerce_ped_component(component)
    component_data = _component_data(root, component_enum)
    if component_data is None:
        raise ValueError(f"YMT does not define component {component_enum.name}")
    drawables = _get(component_data, _COMPONENT_DRAWABLES, default=None)
    if not isinstance(drawables, list):
        raise ValueError(f"YMT component {component_enum.name} has no drawable list")
    drawable_index = int(drawable)
    if drawable_index < 0 or drawable_index >= len(drawables):
        raise IndexError(f"Drawable {drawable_index} is outside component {component_enum.name}")
    drawable_data = drawables[drawable_index]
    cloth_data = _get(drawable_data, _DRAWABLE_CLOTH, default=None)
    if not isinstance(cloth_data, MutableMapping):
        cloth_data = {}
        _set(drawable_data, _DRAWABLE_CLOTH, cloth_data)
    _set(cloth_data, _CLOTH_OWNS, bool(owns))
    return ymt


def ped_drawable_file_stem(component: PedComponent | str | int, drawable: int, prop_mask: int = 0) -> str:
    variation = PedDrawableVariation(
        component=coerce_ped_component(component),
        drawable_index=int(drawable),
        texture_count=0,
        prop_mask=int(prop_mask),
    )
    return variation.file_stem


def _require_ped_root(ymt: Ymt) -> MutableMapping[str, Any]:
    root = ymt.root_value
    if not isinstance(root, MutableMapping):
        raise TypeError("YMT root is not a decoded ped variation mapping")
    return root


def _component_data(root: MutableMapping[str, Any], component: PedComponent) -> MutableMapping[str, Any] | None:
    available = tuple(_get(root, _ROOT_AVAILABLE, default=()))
    if int(component) >= len(available):
        return None
    component_data_index = int(available[int(component)])
    if component_data_index == 0xFF:
        return None
    components = _get(root, _ROOT_COMPONENTS, default=())
    if component_data_index < 0 or component_data_index >= len(components):
        return None
    component_data = components[component_data_index]
    return component_data if isinstance(component_data, MutableMapping) else None


def _get(mapping: Any, names: tuple[str, str], *, default: Any = None) -> Any:
    if not isinstance(mapping, MutableMapping):
        return default
    for name in names:
        if name in mapping:
            return mapping[name]
    return default


def _set(mapping: MutableMapping[str, Any], names: tuple[str, str], value: Any) -> None:
    for name in names:
        if name in mapping:
            mapping[name] = value
            return
    mapping[names[0]] = value


__all__ = [
    "PedComponent",
    "PedDrawableVariation",
    "coerce_ped_component",
    "iter_ped_drawables",
    "ped_drawable_file_stem",
    "set_ped_drawable_cloth",
]
