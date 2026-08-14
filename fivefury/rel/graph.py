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


class RelSoundIndex:
    def __init__(self, rels: Iterable[RelFile]) -> None:
        self.sounds: dict[int, Dat54Sound] = {}
        for rel in rels:
            for item in rel.iter_items(Dat54Sound):
                self.sounds.setdefault(int(item.name_hash) & 0xFFFFFFFF, item)

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
            sound = self.sounds.get(sound_hash)
            if sound is None:
                unresolved.append(sound_hash)
                continue
            resolved.append(sound_hash)
            containers = sound.audio_container_hashes()
            streams = sound.audio_stream_hashes()
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
                reversed([value for value in sound.sound_hashes() if value])
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
    "resolve_rel_sound_graph",
]
