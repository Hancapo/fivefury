from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...ycd.model import Ycd


@dataclass(slots=True)
class CutsceneAnimationDictionary:
    reference: str = "dict"
    sections: list[Ycd] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.reference:
            raise ValueError("Cutscene animation dictionary reference cannot be empty")


__all__ = ["CutsceneAnimationDictionary"]
