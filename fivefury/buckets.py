from __future__ import annotations

from bisect import bisect_right
from typing import Final


AT_HASH_BUCKET_CAPACITIES: Final[tuple[int, ...]] = (
    11,
    29,
    59,
    107,
    191,
    331,
    563,
    953,
    1609,
    2729,
    4621,
    7841,
    13297,
    22571,
    38351,
    65167,
)
AT_HASH_BUCKET_MAX: Final[int] = 65521


def at_hash_bucket_capacity(item_count: int) -> int:
    """Return the bucket capacity used by GTA's atHashMap variants."""

    count = max(0, int(item_count))
    index = bisect_right(AT_HASH_BUCKET_CAPACITIES, count)
    if index < len(AT_HASH_BUCKET_CAPACITIES):
        return AT_HASH_BUCKET_CAPACITIES[index]
    return AT_HASH_BUCKET_MAX


__all__ = ["AT_HASH_BUCKET_CAPACITIES", "AT_HASH_BUCKET_MAX", "at_hash_bucket_capacity"]
