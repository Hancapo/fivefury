from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from ...awc.constants import AWC_STREAM_ID_MASK
from ...awc.validation import awc_playback_streams, resolve_awc_playback_stream
from ...gamefile import GameFile, GameFileType
from ...metahash import MetaHash
from ..model import CutHashedString
from ..reference_values import subtitle_hash
from ..scene import CutBinding, CutScene

if TYPE_CHECKING:
    from ...cache import AssetRecord
    from ...ycd import Ycd
    from ...yed import PedExpressionSet
    from .runtime import CutsceneResolutionTrace


@dataclass(slots=True, frozen=True)
class CutsceneResolveIssue:
    severity: str
    code: str
    message: str
    asset_path: str | None = None
    object_id: int | None = None
    event_id: int | None = None


@dataclass(slots=True, frozen=True)
class PedOutfitOption:
    slot: int
    drawable: int
    texture_count: int
    is_prop: bool
    file_stem: str | None
    prop_mask: int = 0
    num_alternatives: int = 0
    owns_cloth: bool = False
    drawable_asset: AssetRecord | None = None
    texture_assets: tuple[AssetRecord, ...] = ()


@dataclass(slots=True, frozen=True)
class PedOutfitCatalog:
    model_name: str
    model_hash: int | None
    variation_asset: AssetRecord | None
    slots: Mapping[int, tuple[PedOutfitOption, ...]]
    issues: tuple[CutsceneResolveIssue, ...] = ()


@dataclass(slots=True)
class ResolvedPedOutfitVariant:
    option: PedOutfitOption
    drawable_files: tuple[GameFile, ...] = ()
    texture_files: tuple[GameFile, ...] = ()
    issues: tuple[CutsceneResolveIssue, ...] = ()


@dataclass(slots=True)
class ResolvedPedExpressionSet:
    expression_set: PedExpressionSet
    source_asset: AssetRecord
    source_file: GameFile
    yed_asset: AssetRecord | None = None
    yed_file: GameFile | None = None
    selected_expression_names: tuple[str, ...] = ()
    selected_program_names: tuple[str, ...] = ()
    selected_program_hashes: tuple[MetaHash, ...] = ()
    missing_expression_names: tuple[str, ...] = ()

    @property
    def dictionary(self) -> Any | None:
        return self.yed_file.parsed if self.yed_file is not None else None


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
    ped_metadata_asset: AssetRecord | None = None
    ped_metadata_file: GameFile | None = None
    ped_init_data_candidates: tuple[Any, ...] = ()
    ped_init_data: Any | None = None
    resolved_expression_set: ResolvedPedExpressionSet | None = None

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

    @property
    def ped_metadata(self) -> Any | None:
        result = self.ped_metadata_file
        ymt = result.parsed if result is not None else None
        return getattr(ymt, "ped_metadata", None)

    @property
    def ped_init_data_asset(self) -> AssetRecord | None:
        return self.ped_metadata_asset if self.ped_init_data is not None else None

    @property
    def expression_file(self) -> GameFile | None:
        return self.files.get(GameFileType.YED)

    @property
    def expression_dictionary(self) -> Any | None:
        result = self.expression_file
        return result.parsed if result is not None else None

    @property
    def expression_set(self) -> PedExpressionSet | None:
        result = self.resolved_expression_set
        return result.expression_set if result is not None else None


@dataclass(slots=True)
class ResolvedCutAudio:
    reference: str | int
    asset: AssetRecord
    file: GameFile
    container_reference: str | None = None
    sound_hashes: tuple[int, ...] = ()
    stream_hashes: tuple[int, ...] = ()

    @property
    def awc(self) -> Any:
        return self.file.parsed

    @property
    def stream_candidates(self) -> tuple[Any, ...]:
        return awc_playback_streams(self.awc)

    @property
    def stream(self) -> Any | None:
        owners = {
            id(owner): owner
            for stream_hash in self.stream_hashes
            if (
                owner := resolve_awc_playback_stream(
                    self.awc,
                    stream_hash=stream_hash,
                )
            )
            is not None
        }
        if self.stream_hashes:
            return next(iter(owners.values())) if len(owners) == 1 else None
        return resolve_awc_playback_stream(self.awc, fallback_hash=self._reference_hash)

    @property
    def unresolved_stream_hashes(self) -> tuple[int, ...]:
        return tuple(
            stream_hash
            for stream_hash in self.stream_hashes
            if resolve_awc_playback_stream(self.awc, stream_hash=stream_hash) is None
        )

    @property
    def stream_ambiguity(self) -> tuple[int, ...]:
        if self.stream is not None:
            return ()
        return tuple(
            int(getattr(stream, "id", 0)) & AWC_STREAM_ID_MASK
            for stream in self.stream_candidates
        )

    @property
    def stream_id(self) -> int | None:
        stream = self.stream
        return (
            int(getattr(stream, "id", 0)) & AWC_STREAM_ID_MASK
            if stream is not None
            else None
        )

    @property
    def lipsync_chunk(self) -> Any | None:
        stream = self.stream
        return getattr(stream, "lipsync_chunk", None) if stream is not None else None

    @property
    def lipsync(self) -> Any | None:
        stream = self.stream
        return getattr(stream, "lipsync", None) if stream is not None else None

    @property
    def _reference_hash(self) -> int:
        if isinstance(self.reference, str):
            stem = PurePosixPath(self.reference.replace("\\", "/")).stem.casefold()
            return MetaHash(stem).uint & AWC_STREAM_ID_MASK
        return int(self.reference) & AWC_STREAM_ID_MASK

    @property
    def channel_count(self) -> int:
        stream = self.stream
        layout = getattr(stream, "stream_format_chunk", None)
        return len(layout.channels) if layout is not None else int(stream is not None)

    @property
    def sample_rate(self) -> int:
        stream = self.stream
        layout = getattr(stream, "stream_format_chunk", None)
        if layout is not None and layout.channels:
            return int(layout.channels[0].sample_rate)
        return int(getattr(stream, "sample_rate", 0)) if stream is not None else 0

    @property
    def sample_count(self) -> int:
        stream = self.stream
        layout = getattr(stream, "stream_format_chunk", None)
        if layout is not None and layout.channels:
            return int(layout.channels[0].samples)
        return int(getattr(stream, "sample_count", 0)) if stream is not None else 0

    def wav_bytes(self) -> bytes:
        stream = self.stream
        if stream is None:
            candidate_ids = ", ".join(
                f"0x{value:08X}" for value in self.stream_ambiguity
            )
            raise ValueError(
                "AWC audio stream is ambiguous"
                + (f": {candidate_ids}" if candidate_ids else "")
            )
        if getattr(self.awc, "multi_channel_flag", False):
            return self.awc.wav_bytes()
        return stream.wav_bytes()

    @property
    def duration(self) -> float:
        stream = self.stream
        if stream is None:
            return 0.0
        if getattr(self.awc, "multi_channel_flag", False):
            return max(
                (
                    float(getattr(channel, "duration", 0.0))
                    for channel in getattr(self.awc, "channel_streams", ())
                ),
                default=0.0,
            )
        return float(getattr(stream, "duration", 0.0))


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
