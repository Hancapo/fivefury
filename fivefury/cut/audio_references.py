from __future__ import annotations

from pathlib import PurePosixPath
from typing import Protocol

from ..metahash import MetaHash
from .reference_values import field_reference
from .scene.base import CutScene

_AUDIO_CONTAINER_VARIANTS = (
    "_edited",
    "_mastered",
    "_mastered_only",
    "_mastered_replay",
    "_mastered_replay_only",
    "_mastered_trimmed",
)


class _NamedAsset(Protocol):
    @property
    def stem(self) -> str: ...


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


def cut_audio_reference_hash(reference: str | int) -> int:
    if isinstance(reference, str):
        stem = PurePosixPath(reference.replace("\\", "/")).stem.casefold()
        return MetaHash(stem).uint
    return int(reference) & 0xFFFFFFFF


def cut_audio_asset_reference_hashes(asset: _NamedAsset) -> tuple[int, ...]:
    stem = asset.stem.casefold()
    names = [stem]
    for suffix in ("_mastered_only", "_seq_mastered_only"):
        if stem.endswith(suffix):
            names.append(stem[: -len(suffix)])
    return tuple(dict.fromkeys(MetaHash(name).uint for name in names if name))


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
    bindings = {binding.object_id: binding for binding in scene.bindings}
    hints: dict[str | int, list[str]] = {reference: [] for reference in references}
    for event in scene.timeline:
        if event.event_name not in {"load_audio", "play_audio"}:
            continue
        reference = field_reference(event.payload.get("cName"))
        if reference not in wanted:
            continue
        binding = bindings.get(event.target_id)
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


__all__ = [
    "cut_audio_asset_reference_hashes",
    "cut_audio_container_hints",
    "cut_audio_hint_rank",
    "cut_audio_reference_hash",
    "cut_event_references",
]
