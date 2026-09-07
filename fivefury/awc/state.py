from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .structures import Awc


def serialized_state(awc: Awc) -> tuple:
    """Snapshot the wire semantics, not derived decoder caches or file paths."""
    return (
        awc.version,
        awc.flags,
        awc.endian,
        awc.whole_file_encrypted,
        tuple(
            (
                stream.hash,
                tuple(
                    (
                        chunk.type_value,
                        chunk.seek_table_entry_size,
                        chunk.to_payload(awc.endian),
                    )
                    for chunk in stream.chunks
                ),
            )
            for stream in awc.streams
        ),
    )
