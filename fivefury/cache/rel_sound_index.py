from __future__ import annotations

from pathlib import Path

from ..rel import RelSoundIndex, RelSoundRecord
from .sidecar_binary import SidecarReader, SidecarWriter
from .sidecars import load_sidecar_payload, save_sidecar_payload, sidecar_path

_MAGIC = b"FFREL001"
_MAX_RECORDS = 2_000_000
_MAX_REFERENCES = 4096
_MAX_ERRORS = 1_000_000


def rel_sound_index_path(index_path: str | Path) -> Path:
    return sidecar_path(index_path, "rel")


def load_rel_sound_index(
    index_path: str | Path,
) -> tuple[RelSoundIndex, tuple[str, ...]] | None:
    payload = load_sidecar_payload(index_path, "rel", _MAGIC)
    if payload is None:
        return None
    reader = SidecarReader(payload)
    try:
        records = []
        for _ in range(reader.count(_MAX_RECORDS)):
            name_hash = reader.u32()
            children = tuple(
                reader.u32()
                for _ in range(reader.count(_MAX_REFERENCES))
            )
            containers = tuple(
                reader.u32()
                for _ in range(reader.count(_MAX_REFERENCES))
            )
            streams = tuple(
                reader.u32()
                for _ in range(reader.count(_MAX_REFERENCES))
            )
            records.append(RelSoundRecord(name_hash, children, containers, streams))
        errors = tuple(reader.text() for _ in range(reader.count(_MAX_ERRORS)))
        reader.finish()
    except (ValueError, OverflowError):
        return None
    return RelSoundIndex.from_records(records), errors


def save_rel_sound_index(
    index_path: str | Path,
    index: RelSoundIndex,
    errors: tuple[str, ...] = (),
) -> Path | None:
    records = index.records
    writer = SidecarWriter()
    writer.count(len(records), _MAX_RECORDS)
    for record in records:
        writer.u32(record.name_hash)
        for values in (record.sound_hashes, record.container_hashes, record.stream_hashes):
            writer.count(len(values), _MAX_REFERENCES)
            for value in values:
                writer.u32(value)
    writer.count(len(errors), _MAX_ERRORS)
    for error in errors:
        writer.text(error)
    return save_sidecar_payload(index_path, "rel", _MAGIC, writer.to_bytes())


__all__ = ["load_rel_sound_index", "rel_sound_index_path", "save_rel_sound_index"]
