from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ...gxt2 import Gxt2
from ..payloads import CutFinalNamePayload, CutSubtitlePayload
from .bindings import CutBinding, CutSubtitle

if TYPE_CHECKING:
    from .base import CutScene
    from .timeline import CutTimelineEvent


@dataclass(slots=True)
class CutSubtitleCue:
    label: str
    text: str
    start: float
    duration: float
    language_id: int = -1
    transition_in: int = -1
    transition_in_duration: float = 0.0
    transition_out: int = -1
    transition_out_duration: float = 0.0

    def to_payload(self) -> CutSubtitlePayload:
        return CutSubtitlePayload(
            self.label,
            duration=float(self.duration),
            language_id=int(self.language_id),
            transition_in=int(self.transition_in),
            transition_in_duration=float(self.transition_in_duration),
            transition_out=int(self.transition_out),
            transition_out_duration=float(self.transition_out_duration),
        )


@dataclass(slots=True)
class CutSubtitleTrack:
    dictionary_name: str
    binding: CutBinding
    cues: list[CutSubtitleCue] = field(default_factory=list)
    events: list[CutTimelineEvent] = field(default_factory=list)

    def to_gxt2(self) -> Gxt2:
        return build_subtitle_gxt2(self.cues)

    def save_gxt2(self, path: str | Path) -> None:
        self.to_gxt2().save(path)


def build_subtitle_gxt2(cues: Iterable[CutSubtitleCue]) -> Gxt2:
    return Gxt2({cue.label: cue.text for cue in cues})


def subtitle_cues_from_text(
    text: str,
    *,
    label_prefix: str,
    start: float = 0.0,
    total_duration: float | None = None,
    cue_duration: float | None = None,
    language_id: int = -1,
    transition_in: int = -1,
    transition_out: int = -1,
) -> list[CutSubtitleCue]:
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines:
        return []
    if cue_duration is None:
        span = max(float(total_duration or len(lines)), float(len(lines))) / float(len(lines))
        cue_duration = max(span * 0.92, 0.25)
    else:
        span = float(cue_duration)
    prefix = str(label_prefix).upper()
    return [
        CutSubtitleCue(
            label=f"{prefix}_SUB_{index + 1:03d}",
            text=line,
            start=float(start) + index * span,
            duration=float(cue_duration),
            language_id=int(language_id),
            transition_in=int(transition_in),
            transition_out=int(transition_out),
        )
        for index, line in enumerate(lines)
    ]


def install_subtitles(
    self: CutScene,
    dictionary_name: str,
    cues: Iterable[CutSubtitleCue],
    *,
    asset_manager: CutBinding | int | None = None,
    subtitle: CutBinding | int | str | None = None,
    load_at: float = 0.0,
    unload_at: float | None = None,
    load_dictionary: bool = True,
) -> CutSubtitleTrack:
    cue_list = list(cues)
    if isinstance(subtitle, CutBinding):
        subtitle_binding: CutBinding = subtitle
    elif isinstance(subtitle, int):
        binding = self.get_binding(subtitle)
        if binding is None:
            raise ValueError(f"unknown subtitle object id {subtitle}")
        subtitle_binding = binding
    else:
        subtitle_binding = self.add(CutSubtitle(str(subtitle or dictionary_name)))

    target = asset_manager
    if target is None:
        managers = self.bindings_for_role("asset_manager")
        target = managers[0] if managers else self.add_asset_manager()

    events: list[CutTimelineEvent] = []
    if load_dictionary:
        events.append(self.load_subtitles(float(load_at), CutFinalNamePayload(dictionary_name), target=target))
    for cue in cue_list:
        events.append(self.show_subtitle(float(cue.start), subtitle_binding, cue.to_payload()))
    if load_dictionary and unload_at is not None:
        events.append(self.unload_subtitles(float(unload_at), CutFinalNamePayload(dictionary_name), target=target))
    return CutSubtitleTrack(dictionary_name=str(dictionary_name), binding=subtitle_binding, cues=cue_list, events=events)


__all__ = [
    "CutSubtitleCue",
    "CutSubtitleTrack",
    "build_subtitle_gxt2",
    "install_subtitles",
    "subtitle_cues_from_text",
]
