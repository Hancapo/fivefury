from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..bounds import (
    Bound,
    BoundComposite,
    apply_bound_ref_counts,
    calculate_bound_ref_counts,
)
from .physics import YftPhysicsLod


def _child_bound(root: Bound, index: int, child_count: int) -> Bound | None:
    if isinstance(root, BoundComposite):
        return root.children[index].bound if index < len(root.children) else None
    return root if child_count == 1 and index == 0 else None


def physics_bound_owner_roots(
    lod: YftPhysicsLod,
    *,
    root: Bound | None = None,
    damaged: bool = False,
    fragment_drawable_fallback: bool = False,
) -> tuple[Bound, ...]:
    bound = root or lod.composite_bound
    if bound is None:
        return ()
    roots: list[Bound] = []
    if damaged:
        if lod.damaged_damp_archetype is not None:
            roots.append(bound)
    else:
        roots.append(bound)
        if lod.undamaged_damp_archetype is not None:
            roots.append(bound)

    for index, child in enumerate(lod.children):
        entity = child.damaged_entity if damaged else child.undamaged_entity
        has_drawable = entity is not None and entity.drawable is not None
        if len(lod.children) == 1 and fragment_drawable_fallback:
            has_drawable = True
        child_bound = _child_bound(bound, index, len(lod.children))
        if has_drawable and child_bound is not None:
            roots.append(child_bound)
    return tuple(roots)


def calculate_physics_lod_bound_ref_counts(
    lod: YftPhysicsLod,
    *,
    root: Bound | None = None,
    damaged: bool = False,
    fragment_drawable_fallback: bool = False,
) -> Mapping[int, int]:
    return calculate_bound_ref_counts(
        physics_bound_owner_roots(
            lod,
            root=root,
            damaged=damaged,
            fragment_drawable_fallback=fragment_drawable_fallback,
        )
    )


def apply_physics_lod_bound_ref_counts(
    lod: YftPhysicsLod,
    *,
    fragment_drawable_fallback: bool = False,
) -> Mapping[int, int]:
    return apply_bound_ref_counts(
        physics_bound_owner_roots(
            lod,
            fragment_drawable_fallback=fragment_drawable_fallback,
        )
    )


def iter_bound_graph(root: Bound) -> Iterable[Bound]:
    visited: set[int] = set()
    pending = [root]
    while pending:
        bound = pending.pop()
        if id(bound) in visited:
            continue
        visited.add(id(bound))
        yield bound
        if isinstance(bound, BoundComposite):
            pending.extend(
                child.bound for child in reversed(bound.children) if child.bound is not None
            )


__all__ = [
    "apply_physics_lod_bound_ref_counts",
    "calculate_physics_lod_bound_ref_counts",
    "iter_bound_graph",
    "physics_bound_owner_roots",
]
