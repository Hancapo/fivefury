from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Protocol

from ..hashing import jenk_continue_hash, jenk_finalize_hash, jenk_partial_hash
from ..metahash import MetaHash
from .reference_values import field_reference
from .scene.base import CutScene

if TYPE_CHECKING:
    from ..rel import RelSoundGraph, RelSoundIndex

_AUDIO_CONTAINER_VARIANTS = (
    "_edited",
    "_mastered",
    "_mastered_only",
    "_mastered_replay",
    "_mastered_replay_only",
    "_mastered_trimmed",
)

_CUTSCENE_SOUND_SUFFIXES = (
    "",
    "_EDITED",
    "_MASTERED_TRIMMED",
    "_MASTERED",
    "_MASTERED_ONLY",
    "_MASTERED_REPLAY",
    "_MASTERED_REPLAY_ONLY",
    "_CUSTOM_REPLAY",
)

_SYNCED_SCENE_SOUND_SUFFIXES = (
    "_CUSTOM",
    "_SYNC_MASTERED",
    "_SYNC_MASTERED_TRIMMED",
    "_SYNC_MASTERED_ONLY",
    "_SYNC_MASTERED_REPLAY",
    "_SYNC_MASTERED_REPLAY_ONLY",
)


class _NamedAsset(Protocol):
    @property
    def stem(self) -> str: ...

    @property
    def path(self) -> str: ...


def cut_event_references(
    scene: CutScene, names: set[str]
) -> tuple[str | int, ...]:
    values: list[str | int] = []
    seen: set[str | int] = set()
    for event in scene.timeline:
        if event.event_name not in names:
            continue
        value = field_reference(event.payload.get("cName"))
        if value is not None and value not in seen:
            seen.add(value)
            values.append(value)
    return tuple(values)


def _audio_binding_reference(
    scene: CutScene,
    target_id: int | None,
) -> str | int | None:
    if target_id is None:
        return None
    binding = scene.get_binding(target_id)
    if binding is None or binding.role != "audio":
        return None
    return field_reference(binding.fields.get("cName")) or binding.name


def cut_audio_references(scene: CutScene) -> tuple[str | int, ...]:
    values: list[str | int] = []
    seen: set[str | int] = set()
    for event in scene.timeline:
        if event.event_name not in {"load_audio", "play_audio"}:
            continue
        value = _audio_binding_reference(scene, event.target_id)
        if value is not None and value not in seen:
            seen.add(value)
            values.append(value)
    return tuple(values)


def cut_audio_reference_hash(reference: str | int) -> int:
    if isinstance(reference, str):
        stem = PurePosixPath(reference.replace("\\", "/")).stem.casefold()
        return MetaHash(stem).uint
    return int(reference) & 0xFFFFFFFF


def cut_audio_sound_hashes(reference: str | int) -> tuple[int, ...]:
    if isinstance(reference, str):
        path = PurePosixPath(reference.replace("\\", "/"))
        display_name = str(path.with_suffix("")) if path.suffix else str(path)
        partial_hash = jenk_partial_hash(f"CUTSCENES_{display_name.upper()}")
        candidates: list[int] = []
    else:
        partial_hash = int(reference) & 0xFFFFFFFF
        candidates = [partial_hash]
    for suffix in _CUTSCENE_SOUND_SUFFIXES + _SYNCED_SCENE_SOUND_SUFFIXES:
        continued = (
            partial_hash
            if not suffix
            else jenk_continue_hash(partial_hash, suffix)
        )
        candidates.append(jenk_finalize_hash(continued))
    return tuple(dict.fromkeys(candidates))


def resolve_cut_audio_sound_graph(
    sound_index: RelSoundIndex,
    reference: str | int,
) -> RelSoundGraph | None:
    for sound_hash in cut_audio_sound_hashes(reference):
        graph = sound_index.resolve(sound_hash)
        if graph.sound_hashes:
            return graph
    return None


def cut_audio_asset_reference_hashes(asset: _NamedAsset) -> tuple[int, ...]:
    stem = asset.stem.casefold()
    names = [stem]
    for suffix in ("_mastered_only", "_seq_mastered_only"):
        if stem.endswith(suffix):
            names.append(stem[: -len(suffix)])
    return tuple(dict.fromkeys(MetaHash(name).uint for name in names if name))


def cut_audio_asset_container_hashes(asset: _NamedAsset) -> tuple[int, ...]:
    path = asset.path.strip().replace("\\", "/").casefold()
    marker = "audio/sfx/"
    marker_index = path.find(marker)
    if marker_index < 0 or not path.endswith(".awc"):
        return ()
    relative = path[marker_index + len(marker) : -4].strip("/")
    parts = list(PurePosixPath(relative).parts)
    if len(parts) < 2:
        return ()
    parts[0] = parts[0].removesuffix(".rpf")
    bank_name = "/".join(parts)
    return (MetaHash(bank_name).uint,) if bank_name else ()


def _normalize_audio_container_hint(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = PurePosixPath(value.strip().replace("\\", "/"))
    name = path.name.casefold()
    if name.endswith((".wa", ".awc")):
        name = name.rsplit(".", 1)[0]
    return name or None


def cut_audio_container_hints(
    scene: CutScene,
    references: tuple[str | int, ...],
) -> dict[str | int, tuple[str, ...]]:
    wanted = set(references)
    hints: dict[str | int, list[str]] = {reference: [] for reference in references}
    for event in scene.timeline:
        if event.event_name not in {"load_audio", "play_audio"}:
            continue
        reference = _audio_binding_reference(scene, event.target_id)
        if reference not in wanted:
            continue
        binding = (
            scene.get_binding(event.target_id)
            if event.target_id is not None
            else None
        )
        values = (
            event.target_name,
            getattr(binding, "name", None),
            getattr(binding, "fields", {}).get("cName")
            if binding is not None
            else None,
        )
        for value in values:
            hint = _normalize_audio_container_hint(value)
            if hint is not None and hint not in hints[reference]:
                hints[reference].append(hint)
    return {reference: tuple(values) for reference, values in hints.items()}


def cut_audio_hint_rank(asset: _NamedAsset, hints: tuple[str, ...]) -> int | None:
    stem = asset.stem.casefold()
    for hint in hints:
        if stem == hint:
            return 0
        if not stem.startswith(f"{hint}_"):
            continue
        remainder = stem[len(hint) :]
        if remainder.endswith(_AUDIO_CONTAINER_VARIANTS):
            return 1
    return None


def cut_audio_asset_rank(
    asset: _NamedAsset,
    reference: str | int,
    hints: tuple[str, ...] = (),
) -> int | None:
    if cut_audio_reference_hash(reference) in cut_audio_asset_reference_hashes(asset):
        return 0
    hint_rank = cut_audio_hint_rank(asset, hints)
    return None if hint_rank is None else hint_rank + 1


def cut_audio_hint_names(hints: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            name
            for hint in hints
            for name in (hint, *(f"{hint}{suffix}" for suffix in _AUDIO_CONTAINER_VARIANTS))
        )
    )


__all__ = [
    "cut_audio_asset_container_hashes",
    "cut_audio_asset_rank",
    "cut_audio_asset_reference_hashes",
    "cut_audio_container_hints",
    "cut_audio_hint_names",
    "cut_audio_hint_rank",
    "cut_audio_reference_hash",
    "cut_audio_references",
    "cut_audio_sound_hashes",
    "cut_event_references",
    "resolve_cut_audio_sound_graph",
]
