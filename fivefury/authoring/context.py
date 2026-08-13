from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeVar

from ..game_target import GameTarget, coerce_game_target
from .assets import AssetRef, AssetSet

AssetT = TypeVar("AssetT")


@dataclass(slots=True, kw_only=True)
class BuildContext:
    game: GameTarget | str = GameTarget.GTA5
    assets: AssetSet = field(default_factory=AssetSet)
    cache: Any | None = None
    strict: bool = True

    def __post_init__(self) -> None:
        self.game = coerce_game_target(self.game)

    def resolve(self, reference: AssetRef[AssetT]) -> AssetT | None:
        target = reference.resolve(self.assets)
        if target is None and self.strict:
            return reference.require(self.assets)
        return target


__all__ = ["BuildContext"]
