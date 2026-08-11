from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ...gamefile import GameFile, GameFileType
from ..model import CutHashedString
from ..scene import CutBinding, CutScene
from .values import subtitle_hash

if TYPE_CHECKING:
    from ...cache import AssetRecord
    from ...ycd import Ycd
    from .runtime import CutsceneResolutionTrace


@dataclass(slots=True, frozen=True)
class CutsceneResolveIssue:
    severity: str
    code: str
    message: str
    asset_path: str | None = None
    object_id: int | None = None
    event_id: int | None = None


@dataclass(slots=True)
class ResolvedCutBinding:
    binding: CutBinding
    reference_hash: int | None = None
    assets: dict[GameFileType, AssetRecord] = field(default_factory=dict)
    files: dict[GameFileType, GameFile] = field(default_factory=dict)
    component_assets: list[AssetRecord] = field(default_factory=list)
    component_files: list[GameFile] = field(default_factory=list)
    component_texture_assets: list[AssetRecord] = field(default_factory=list)
    component_texture_files: list[GameFile] = field(default_factory=list)
    texture_assets: list[AssetRecord] = field(default_factory=list)
    texture_files: list[GameFile] = field(default_factory=list)

    @property
    def model_file(self) -> GameFile | None:
        for kind in (GameFileType.YDR, GameFileType.YDD, GameFileType.YFT):
            result = self.files.get(kind)
            if result is not None:
                return result
        return None

    @property
    def model(self) -> Any | None:
        result = self.model_file
        return result.parsed if result is not None else None


@dataclass(slots=True)
class ResolvedCutAudio:
    reference: str | int
    asset: AssetRecord
    file: GameFile

    @property
    def awc(self) -> Any:
        return self.file.parsed

    @property
    def duration(self) -> float:
        awc = self.awc
        if getattr(awc, "multi_channel_flag", False):
            streams = getattr(awc, "channel_streams", ())
        else:
            streams = getattr(awc, "streams", ())
        return max(
            (float(getattr(stream, "duration", 0.0)) for stream in streams), default=0.0
        )


@dataclass(slots=True)
class ResolvedCutSubtitleDictionary:
    reference: str | int
    language: str = "american"
    assets: tuple[AssetRecord, ...] = ()
    files: tuple[GameFile, ...] = ()

    def get(self, value: Any, default: str | None = None) -> str | None:
        key_hash = subtitle_hash(value)
        if key_hash is None:
            return default
        for game_file in self.files:
            dictionary = game_file.parsed
            if dictionary is None or not hasattr(dictionary, "get"):
                continue
            text = dictionary.get(key_hash)
            if text is not None:
                return str(text)
        return default


@dataclass(slots=True)
class CutsceneAssetBundle:
    source: AssetRecord
    cut_file: GameFile
    scene: CutScene
    ycd_by_section: dict[int, Ycd] = field(default_factory=dict)
    ycd_assets_by_section: dict[int, AssetRecord] = field(default_factory=dict)
    bindings: dict[int, ResolvedCutBinding] = field(default_factory=dict)
    audio_references: tuple[str | int, ...] = ()
    audio: dict[str | int, ResolvedCutAudio] = field(default_factory=dict)
    subtitle_references: tuple[str | int, ...] = ()
    subtitle_dictionaries: dict[str | int, ResolvedCutSubtitleDictionary] = field(
        default_factory=dict
    )
    subtitle_language: str = "american"
    initial_ped_variations: dict[int, dict[int, tuple[int, int]]] = field(
        default_factory=dict
    )
    issues: list[CutsceneResolveIssue] = field(default_factory=list)
    trace: CutsceneResolutionTrace | None = None

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def diagnostics(self) -> tuple[CutsceneResolveIssue, ...]:
        return tuple(self.issues)

    def subtitle_dictionary(
        self, reference: str | int
    ) -> ResolvedCutSubtitleDictionary | None:
        result = self.subtitle_dictionaries.get(reference)
        if result is not None or not isinstance(reference, str):
            return result
        folded = reference.casefold()
        return next(
            (
                dictionary
                for key, dictionary in self.subtitle_dictionaries.items()
                if isinstance(key, str) and key.casefold() == folded
            ),
            None,
        )

    def resolve_subtitle(
        self,
        value: Any,
        *,
        active_references: tuple[str | int, ...] | list[str | int] | None = None,
        default: str | None = None,
    ) -> str | None:
        dictionaries: list[ResolvedCutSubtitleDictionary] = []
        if active_references:
            for reference in active_references:
                dictionary = self.subtitle_dictionary(reference)
                if dictionary is not None and dictionary not in dictionaries:
                    dictionaries.append(dictionary)
        if not dictionaries:
            dictionaries.extend(self.subtitle_dictionaries.values())
        for dictionary in dictionaries:
            text = dictionary.get(value)
            if text is not None:
                return text
        if isinstance(value, CutHashedString) and value.text:
            return value.text
        return default
