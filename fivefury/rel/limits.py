from __future__ import annotations

from collections.abc import Sized


def checked_count(values: Sized, maximum: int, label: str) -> int:
    count = len(values)
    if count > maximum:
        raise ValueError(f"{label} supports at most {maximum} entries, got {count}")
    return count


__all__ = ["checked_count"]
