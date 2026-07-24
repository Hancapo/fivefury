from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from ..ydr import YdrSkeleton

Matrix43 = tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
]


@dataclasses.dataclass(slots=True)
class YftSharedMatrixSet:
    matrices: list[Matrix43] = dataclasses.field(default_factory=list)
    is_skinned: bool = False

    @classmethod
    def from_skeleton(
        cls,
        skeleton: YdrSkeleton,
        *,
        is_skinned: bool = False,
    ) -> YftSharedMatrixSet:
        identity: Matrix43 = (
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
        )
        return cls(
            matrices=[identity for _bone in skeleton.bones],
            is_skinned=bool(is_skinned),
        )

    @classmethod
    def declare(
        cls,
        matrices: Sequence[Sequence[float]],
        *,
        is_skinned: bool = False,
    ) -> YftSharedMatrixSet:
        declared: list[Matrix43] = []
        for index, matrix in enumerate(matrices):
            values = tuple(float(value) for value in matrix)
            if len(values) != 12:
                raise ValueError(
                    f"matrices[{index}] must contain 12 Matrix43 components"
                )
            declared.append(values)  # type: ignore[arg-type]
        return cls(
            matrices=declared,
            is_skinned=bool(is_skinned),
        )

    @property
    def matrix_count(self) -> int:
        return len(self.matrices)


__all__ = ["Matrix43", "YftSharedMatrixSet"]
