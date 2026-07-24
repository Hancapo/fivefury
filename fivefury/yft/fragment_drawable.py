from __future__ import annotations

import dataclasses

from ..ydr import Ydr

_MATRIX_FLAG = 0x7F800001


@dataclasses.dataclass(frozen=True, slots=True)
class YftFragmentMatrix:
    columns: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ] = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, 0.0),
    )
    flags: tuple[int, int, int, int] = (
        _MATRIX_FLAG,
        _MATRIX_FLAG,
        _MATRIX_FLAG,
        _MATRIX_FLAG,
    )

    @classmethod
    def identity(cls) -> YftFragmentMatrix:
        return cls()


@dataclasses.dataclass(slots=True)
class YftFragmentDrawable(Ydr):
    fragment_matrix: YftFragmentMatrix = dataclasses.field(
        default_factory=YftFragmentMatrix.identity
    )
    extra_bound_indices: tuple[int, ...] = ()
    extra_bound_matrices: tuple[YftFragmentMatrix, ...] = ()
    skeleton_type_name: str = ""
    load_skeleton: bool = True
    locators_pointer: int = 0
    animations_pointer: int = 0
    cloned_shader_group_pointer: int = 0

    @classmethod
    def from_ydr(
        cls,
        drawable: Ydr,
        *,
        skeleton_type_name: str = "",
        fragment_matrix: YftFragmentMatrix | None = None,
    ) -> YftFragmentDrawable:
        values = {
            field.name: getattr(drawable, field.name)
            for field in dataclasses.fields(Ydr)
            if field.init
        }
        return cls(
            **values,
            skeleton_type_name=str(skeleton_type_name),
            fragment_matrix=fragment_matrix or YftFragmentMatrix.identity(),
        )


__all__ = [
    "YftFragmentDrawable",
    "YftFragmentMatrix",
]
