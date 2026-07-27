from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from .model import Bound, BoundComposite


def calculate_bound_ref_counts(roots: Iterable[Bound]) -> Mapping[int, int]:
    counts: Counter[int] = Counter()
    expanded: set[int] = set()
    active: set[int] = set()

    def expand(bound: Bound) -> None:
        identity = id(bound)
        if identity in active:
            raise ValueError("Bound ownership graph contains a composite cycle")
        if identity in expanded:
            return
        expanded.add(identity)
        if not isinstance(bound, BoundComposite):
            return
        active.add(identity)
        for child in bound.children:
            if child.bound is None:
                continue
            counts[id(child.bound)] += 1
            expand(child.bound)
        active.remove(identity)

    for root in roots:
        counts[id(root)] += 1
        expand(root)
    return dict(counts)


def apply_bound_ref_counts(roots: Iterable[Bound]) -> Mapping[int, int]:
    declared_roots = tuple(roots)
    counts = calculate_bound_ref_counts(declared_roots)
    visited: set[int] = set()

    def apply(bound: Bound) -> None:
        identity = id(bound)
        if identity in visited:
            return
        visited.add(identity)
        bound.ref_count = counts.get(identity, 0)
        if isinstance(bound, BoundComposite):
            for child in bound.children:
                if child.bound is not None:
                    apply(child.bound)

    for root in declared_roots:
        apply(root)
    return counts


__all__ = ["apply_bound_ref_counts", "calculate_bound_ref_counts"]
