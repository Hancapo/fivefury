from __future__ import annotations

import dataclasses

from ..ydr import Ydr, YdrModel


@dataclasses.dataclass(slots=True)
class YftDrawable:
    label: str
    drawable: Ydr
    pointer: int = 0
    name: str = ""


@dataclasses.dataclass(slots=True)
class YftDrawableMatch:
    label: str
    drawable: Ydr
    models: list[YdrModel] = dataclasses.field(default_factory=list)


__all__ = [
    "YftDrawable",
    "YftDrawableMatch",
]
