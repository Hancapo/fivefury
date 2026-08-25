from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .model import Dat54Sound, RelFile, RelHashLike, rel_hash


@dataclass(frozen=True, slots=True)
class RelSoundEndpoint:
    sound_hash: int
    container_hash: int
    stream_hash: int


@dataclass(frozen=True, slots=True)
class RelSoundGraph:
    root_hash: int
    sound_hashes: tuple[int, ...]
    endpoints: tuple[RelSoundEndpoint, ...]
    unresolved_hashes: tuple[int, ...]

    @property
    def complete(self) -> bool:
        return not self.unresolved_hashes and bool(self.sound_hashes)

    @property
    def container_hashes(self) -> tuple[int, ...]:
        return tuple(
            dict.fromkeys(
                endpoint.container_hash
                for endpoint in self.endpoints
                if endpoint.container_hash
            )
        )

    @property
    def stream_hashes(self) -> tuple[int, ...]:
        return tuple(
            dict.fromkeys(
                endpoint.stream_hash
                for endpoint in self.endpoints
                if endpoint.stream_hash
            )
        )


@dataclass(frozen=True, slots=True)
class RelSoundRecord:
    name_hash: int
    sound_hashes: tuple[int, ...]
    container_hashes: tuple[int, ...]
    stream_hashes: tuple[int, ...]


class RelSoundIndex:
    def __init__(self, rels: Iterable[RelFile]) -> None:
        self.sounds: dict[int, Dat54Sound] = {}
        for rel in rels:
            for item in rel.iter_items(Dat54Sound):
                self.sounds.setdefault(int(item.name_hash) & 0xFFFFFFFF, item)
        self._records = {
            sound_hash: RelSoundRecord(
                name_hash=sound_hash,
                sound_hashes=tuple(sound.sound_hashes()),
                container_hashes=tuple(sound.audio_container_hashes()),
                stream_hashes=tuple(sound.audio_stream_hashes()),
            )
            for sound_hash, sound in self.sounds.items()
        }

    @classmethod
    def from_records(cls, records: Iterable[RelSoundRecord]) -> RelSoundIndex:
        instance = cls(())
        instance._records = {
            int(record.name_hash) & 0xFFFFFFFF: record for record in records
        }
        return instance

    @property
    def records(self) -> tuple[RelSoundRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def resolve(self, root: RelHashLike) -> RelSoundGraph:
        root_hash = rel_hash(root)
        pending = [root_hash]
        visited: set[int] = set()
        resolved: list[int] = []
        unresolved: list[int] = []
        endpoints: list[RelSoundEndpoint] = []
        while pending:
            sound_hash = pending.pop()
            if not sound_hash or sound_hash in visited:
                continue
            visited.add(sound_hash)
            sound = self._records.get(sound_hash)
            if sound is None:
                unresolved.append(sound_hash)
                continue
            resolved.append(sound_hash)
            containers = sound.container_hashes
            streams = sound.stream_hashes
            for index, container_hash in enumerate(containers):
                if not container_hash:
                    continue
                endpoints.append(
                    RelSoundEndpoint(
                        sound_hash=sound_hash,
                        container_hash=container_hash,
                        stream_hash=(
                            streams[index] if index < len(streams) else 0
                        ),
                    )
                )
            pending.extend(
                reversed([value for value in sound.sound_hashes if value])
            )

        return RelSoundGraph(
            root_hash=root_hash,
            sound_hashes=tuple(resolved),
            endpoints=tuple(endpoints),
            unresolved_hashes=tuple(unresolved),
        )


def resolve_rel_sound_graph(
    rels: Iterable[RelFile],
    root: RelHashLike,
) -> RelSoundGraph:
    return RelSoundIndex(rels).resolve(root)


__all__ = [
    "RelSoundEndpoint",
    "RelSoundGraph",
    "RelSoundIndex",
    "RelSoundRecord",
    "resolve_rel_sound_graph",
]
