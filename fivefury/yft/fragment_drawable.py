from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence

from ..bounds import Bound
from ..vector import Vector3
from ..ydr import Ydr, YdrBuild

_MATRIX_FLAG = 0x7F800001


class YftFragmentDrawableName(enum.Enum):
    DERIVE = "derive"
    NULL = "null"


def _normalize_skeleton_type_name(
    value: str | YftFragmentDrawableName | None,
) -> str | YftFragmentDrawableName:
    if value is None:
        return YftFragmentDrawableName.NULL
    if isinstance(value, YftFragmentDrawableName):
        return value
    if not isinstance(value, str):
        raise TypeError(
            "skeleton_type_name must be a string, None, or "
            "YftFragmentDrawableName"
        )
    return value if value else YftFragmentDrawableName.DERIVE


@dataclasses.dataclass(frozen=True, slots=True)
class YftFragmentMatrix:
    columns: tuple[Vector3, Vector3, Vector3, Vector3] = (
        Vector3(1.0, 0.0, 0.0),
        Vector3(0.0, 1.0, 0.0),
        Vector3(0.0, 0.0, 1.0),
        Vector3(),
    )
    flags: tuple[int, int, int, int] = (
        _MATRIX_FLAG,
        _MATRIX_FLAG,
        _MATRIX_FLAG,
        _MATRIX_FLAG,
    )

    def __post_init__(self) -> None:
        if len(self.columns) != 4 or not all(
            isinstance(column, Vector3) for column in self.columns
        ):
            raise TypeError("YftFragmentMatrix columns must contain four Vector3 values")

    @classmethod
    def identity(cls) -> YftFragmentMatrix:
        return cls()


@dataclasses.dataclass(slots=True)
class YftFragmentDrawable(Ydr):
    fragment_matrix: YftFragmentMatrix = dataclasses.field(
        default_factory=YftFragmentMatrix.identity
    )
    extra_bounds: tuple[Bound | None, ...] = ()
    extra_bound_matrices: tuple[YftFragmentMatrix, ...] = ()
    skeleton_type_name: str | YftFragmentDrawableName = (
        YftFragmentDrawableName.DERIVE
    )
    load_skeleton: bool = True
    locators_pointer: int = 0
    animations_pointer: int = 0
    cloned_shader_group_pointer: int = 0

    def __post_init__(self) -> None:
        Ydr.__post_init__(self)
        self.skeleton_type_name = _normalize_skeleton_type_name(
            self.skeleton_type_name
        )

    @classmethod
    def from_ydr(
        cls,
        drawable: Ydr,
        *,
        skeleton_type_name: str | YftFragmentDrawableName | None = (
            YftFragmentDrawableName.DERIVE
        ),
        fragment_matrix: YftFragmentMatrix | None = None,
        extra_bounds: Sequence[Bound | None] = (),
        extra_bound_matrices: Sequence[YftFragmentMatrix] = (),
        load_skeleton: bool = True,
    ) -> YftFragmentDrawable:
        values = {
            field.name: getattr(drawable, field.name)
            for field in dataclasses.fields(Ydr)
            if field.init
        }
        return cls(
            **values,
            skeleton_type_name=_normalize_skeleton_type_name(skeleton_type_name),
            fragment_matrix=fragment_matrix or YftFragmentMatrix.identity(),
            extra_bounds=tuple(extra_bounds),
            extra_bound_matrices=tuple(extra_bound_matrices),
            load_skeleton=bool(load_skeleton),
        )


@dataclasses.dataclass(slots=True)
class YftFragmentDrawableBuild(YdrBuild):
    fragment_matrix: YftFragmentMatrix = dataclasses.field(
        default_factory=YftFragmentMatrix.identity
    )
    extra_bounds: tuple[Bound | None, ...] = ()
    extra_bound_matrices: tuple[YftFragmentMatrix, ...] = ()
    skeleton_type_name: str | YftFragmentDrawableName = (
        YftFragmentDrawableName.DERIVE
    )
    load_skeleton: bool = True

    def __post_init__(self) -> None:
        YdrBuild.__post_init__(self)
        self.skeleton_type_name = _normalize_skeleton_type_name(
            self.skeleton_type_name
        )

    @classmethod
    def from_build(
        cls,
        drawable: YdrBuild,
        *,
        skeleton_type_name: str | YftFragmentDrawableName | None = (
            YftFragmentDrawableName.DERIVE
        ),
        fragment_matrix: YftFragmentMatrix | None = None,
        extra_bounds: Sequence[Bound | None] = (),
        extra_bound_matrices: Sequence[YftFragmentMatrix] = (),
        load_skeleton: bool = True,
    ) -> YftFragmentDrawableBuild:
        values = {
            field.name: getattr(drawable, field.name)
            for field in dataclasses.fields(YdrBuild)
            if field.init
        }
        return cls(
            **values,
            skeleton_type_name=_normalize_skeleton_type_name(skeleton_type_name),
            fragment_matrix=fragment_matrix or YftFragmentMatrix.identity(),
            extra_bounds=tuple(extra_bounds),
            extra_bound_matrices=tuple(extra_bound_matrices),
            load_skeleton=bool(load_skeleton),
        )

    @classmethod
    def from_fragment(
        cls,
        fragment: YftFragmentDrawable,
        drawable: YdrBuild,
    ) -> YftFragmentDrawableBuild:
        unsupported = tuple(
            name
            for name in (
                "locators_pointer",
                "animations_pointer",
                "cloned_shader_group_pointer",
            )
            if getattr(fragment, name)
        )
        if unsupported:
            raise ValueError(
                "fragment drawable contains unsupported owned resources: "
                + ", ".join(unsupported)
            )
        return cls.from_build(
            drawable,
            fragment_matrix=fragment.fragment_matrix,
            extra_bounds=fragment.extra_bounds,
            extra_bound_matrices=fragment.extra_bound_matrices,
            skeleton_type_name=fragment.skeleton_type_name,
            load_skeleton=fragment.load_skeleton,
        )


__all__ = [
    "YftFragmentDrawable",
    "YftFragmentDrawableBuild",
    "YftFragmentDrawableName",
    "YftFragmentMatrix",
]
