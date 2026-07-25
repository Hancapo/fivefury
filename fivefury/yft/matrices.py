from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from ..ydr import YdrSkeleton, skeleton_absolute_transforms

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
        absolute_transforms = skeleton_absolute_transforms(skeleton)
        matrices: list[Matrix43] = []
        for matrix in absolute_transforms:
            matrices.append(
                (
                    float(matrix[0][0]),
                    float(matrix[0][1]),
                    float(matrix[0][2]),
                    float(matrix[3][0]),
                    float(matrix[1][0]),
                    float(matrix[1][1]),
                    float(matrix[1][2]),
                    float(matrix[3][1]),
                    float(matrix[2][0]),
                    float(matrix[2][1]),
                    float(matrix[2][2]),
                    float(matrix[3][2]),
                )
            )
        return cls(
            matrices=matrices,
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
