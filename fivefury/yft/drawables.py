from __future__ import annotations

import dataclasses

from ..ydr import Ydr, YdrBuild, YdrModel, YdrModelInput
from .fragment_drawable import YftFragmentDrawable


@dataclasses.dataclass(slots=True)
class YftDrawable:
    label: str
    drawable: Ydr | YdrBuild | YftFragmentDrawable
    pointer: int = 0
    name: str = ""


@dataclasses.dataclass(slots=True)
class YftDrawableMatch:
    label: str
    drawable: Ydr | YdrBuild | YftFragmentDrawable
    models: list[YdrModel | YdrModelInput] = dataclasses.field(default_factory=list)


__all__ = [
    "YftDrawable",
    "YftDrawableMatch",
]
