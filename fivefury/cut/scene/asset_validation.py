from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from ...authoring import (
    BuildContext,
    DiagnosticSeverity,
    ValidationReport,
)
from ...awc.structures import Awc, AwcStream
from ...awc.validation import resolve_awc_playback_stream, validate_awc_stream
from ...gamefile import GameFileType
from ...metahash import MetaHash
from ...rel import RelFile, RelSoundGraph, RelSoundIndex
from ...ycd import Ycd, YcdAnimationTrack
from ...yed import (
    PedExpressionSetMetadata,
    Yed,
    is_null_expression_reference,
    validate_yed,
)
from ..asset_kinds import CUT_DRAWABLE_KINDS_BY_ROLE
from ..audio_references import (
    cut_audio_asset_rank,
    cut_audio_container_hints,
    cut_audio_reference_hash,
    cut_audio_references,
    cut_event_references,
    resolve_cut_audio_sound_graph,
)
from ..reference_values import field_reference
from .asset_context import CutAssetContext, CutContextAsset, cut_asset_reference_hash
from .bindings import CutBinding, CutPed
from .shared import _technical_cut_index

if TYPE_CHECKING:
    from ...ycd.model import YcdAnimation, YcdClip
    from .authoring import CutsceneAssets
    from .base import CutScene


_BONE_TRACKS = {
    int(YcdAnimationTrack.BONE_TRANSLATION),
    int(YcdAnimationTrack.BONE_ROTATION),
    int(YcdAnimationTrack.BONE_SCALE),
    int(YcdAnimationTrack.BONE_CONSTRAINT),
}


def _severity(context: BuildContext) -> DiagnosticSeverity:
    return (
        DiagnosticSeverity.ERROR
        if context.strict
        else DiagnosticSeverity.WARNING
    )


def _field_hash(value: object) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return cut_asset_reference_hash(str(value))


def _scene_copy(assets: CutsceneAssets) -> CutScene:
    scene = deepcopy(assets.scene)
    scene.clip_dicts = list(assets.ycds)
    return scene


def _extend_scene_report(
    assets: CutsceneAssets,
    scene: CutScene,
    report: ValidationReport,
) -> None:
    for issue in scene.validation_report(strict=True):
        message = issue.message
        if issue.hint:
            message = f"{message} {issue.hint}"
        report.issue(
            issue.code,
            message,
            severity=(
                DiagnosticSeverity.ERROR
                if issue.severity == "error"
                else DiagnosticSeverity.WARNING
            ),
            asset=assets.output_name,
        )


def _validate_ycd_paths(assets: CutsceneAssets, report: ValidationReport) -> None:
    names: set[str] = set()
    for index, ycd in enumerate(assets.ycds):
        if not ycd.path:
            report.issue(
                "cut.ycd.path.missing",
                f"Cutscene YCD section {index} has no output path",
                asset=assets.output_name,
                path=f"ycds[{index}].path",
            )
            continue
        name = Path(ycd.path).name.casefold()
        if name in names:
            report.issue(
                "cut.ycd.path.duplicate",
                f"Duplicate cutscene YCD output name: {name}",
                asset=assets.output_name,
                path=f"ycds[{index}].path",
            )
        names.add(name)


class _CutsceneContextValidator:
    def __init__(
        self,
        scene: CutScene,
        context: BuildContext,
        report: ValidationReport,
    ) -> None:
        self.scene = scene
        self.context = context
        self.report = report
        self.assets = CutAssetContext(context)
        self.models: dict[int, tuple[object, str | int]] = {}

    def validate(self) -> None:
        self._validate_models()
        self._validate_animation_skeletons()
        self._validate_expressions()
        self._validate_audio()

    def resolve_ycds(self) -> None:
        known_hashes = {
            cut_asset_reference_hash(ycd.stem)
            for ycd in self.scene.clip_dicts
            if ycd.stem
        }
        for reference in cut_event_references(
            self.scene,
            {"load_anim_dict"},
        ):
            reference_hash = cut_asset_reference_hash(reference)
            if reference_hash in known_hashes:
                continue
            asset = self.assets.find(reference, (GameFileType.YCD,))
            if asset is None:
                self.report.issue(
                    "cut.ycd.unresolved",
                    f"No YCD matches animation dictionary {reference!s}",
                    severity=_severity(self.context),
                    asset=self.scene.scene_name,
                    path="timeline.animation",
                )
                continue
            ycd = self._load(
                asset,
                code="cut.ycd.load_failed",
                path="timeline.animation",
            )
            if not isinstance(ycd, Ycd):
                if ycd is not None:
                    self.report.issue(
                        "cut.ycd.invalid",
                        f"Asset is not a decoded YCD: {asset.path}",
                        severity=_severity(self.context),
                        asset=asset.path,
                        path="timeline.animation",
                    )
                continue
            self.scene.clip_dicts.append(ycd)
            known_hashes.add(reference_hash)

    def _load(
        self,
        asset: CutContextAsset,
        *,
        code: str,
        path: str,
    ) -> object | None:
        try:
            value = asset.load()
        except Exception as exc:  # noqa: BLE001
            self.report.issue(
                code,
                f"Could not load {asset.path}: {type(exc).__name__}: {exc}",
                severity=_severity(self.context),
                asset=asset.path,
                path=path,
            )
            return None
        if value is None:
            self.report.issue(
                code,
                f"Could not load {asset.path}",
                severity=_severity(self.context),
                asset=asset.path,
                path=path,
            )
        return value

    def _binding_reference(self, binding: CutBinding, field: str) -> str | int | None:
        return field_reference(binding.fields.get(field))

    def _validate_models(self) -> None:
        for binding in self.scene.bindings:
            kinds = CUT_DRAWABLE_KINDS_BY_ROLE.get(binding.role)
            if not kinds:
                continue
            field_path = f"bindings[{binding.object_id}].StreamingName"
            reference = self._binding_reference(binding, "StreamingName")
            if reference is None:
                continue
            self._validate_ytyp(binding, reference)
            asset = self.assets.find(reference, kinds)
            if asset is None:
                self.report.issue(
                    "cut.binding.model.unresolved",
                    f"No drawable or fragment matches {binding.display_name}",
                    severity=_severity(self.context),
                    asset=self.scene.scene_name,
                    path=field_path,
                )
                continue
            model = self._load(
                asset,
                code="cut.binding.model.load_failed",
                path=field_path,
            )
            if model is None:
                continue
            if self._drawable(model, reference) is None:
                self.report.issue(
                    "cut.binding.model.invalid",
                    f"Asset is not a decoded drawable or fragment: {asset.path}",
                    severity=_severity(self.context),
                    asset=asset.path,
                    path=field_path,
                )
                continue
            self.models[binding.object_id] = (model, reference)

    def _validate_ytyp(self, binding: CutBinding, model_reference: str | int) -> None:
        type_reference = self._binding_reference(binding, "typeFile")
        if type_reference is None:
            return
        field_path = f"bindings[{binding.object_id}].typeFile"
        asset = self.assets.find(type_reference, (GameFileType.YTYP,))
        if asset is None:
            self.report.issue(
                "cut.binding.ytyp.unresolved",
                f"No YTYP matches typeFile for {binding.display_name}",
                severity=_severity(self.context),
                asset=self.scene.scene_name,
                path=field_path,
            )
            return
        ytyp = self._load(
            asset,
            code="cut.binding.ytyp.load_failed",
            path=field_path,
        )
        if ytyp is None:
            return
        model_hash = cut_asset_reference_hash(model_reference)
        archetypes = getattr(ytyp, "archetypes", ())
        if not any(
            model_hash
            in {
                _field_hash(getattr(archetype, "name", 0)),
                _field_hash(getattr(archetype, "asset_name", 0)),
            }
            for archetype in archetypes
        ):
            self.report.issue(
                "cut.binding.archetype.unresolved",
                f"YTYP {asset.path} has no archetype for {binding.display_name}",
                severity=_severity(self.context),
                asset=asset.path,
                path="archetypes",
            )

    @staticmethod
    def _drawable(model: object, reference: str | int) -> object | None:
        if hasattr(model, "skeleton"):
            return model
        finder = getattr(model, "get", None)
        if callable(finder):
            entry = finder(reference)
            if entry is not None:
                return getattr(entry, "drawable", None)
        return getattr(model, "main_drawable", None)

    @staticmethod
    def _clip_animations(clip: YcdClip) -> Iterator[YcdAnimation]:
        animation = getattr(clip, "animation", None)
        if animation is not None:
            yield animation
        for entry in getattr(clip, "animations", ()):
            animation = getattr(entry, "animation", None)
            if animation is not None:
                yield animation

    def _validate_animation_skeletons(self) -> None:
        seen: set[tuple[int, int]] = set()
        for event in self.scene.timeline:
            if event.event_name != "set_anim":
                continue
            object_id = event.payload.get("iObjectId")
            if not isinstance(object_id, int) or object_id not in self.models:
                continue
            binding = self.scene.get_binding(object_id)
            if binding is None:
                continue
            cut_index = _technical_cut_index(
                self.scene.camera_cut_list, float(event.start)
            )
            clip = self.scene.clip_for_binding(binding, cut_index=cut_index)
            if clip is None:
                continue
            model, reference = self.models[object_id]
            drawable = self._drawable(model, reference)
            skeleton = getattr(drawable, "skeleton", None)
            bone_ids = {
                int(bone.bone_id)
                for animation in self._clip_animations(clip)
                for bone in animation.bone_ids
                if int(bone.track) in _BONE_TRACKS
            }
            if (
                isinstance(binding, CutPed)
                and binding.has_face_animation
                and not any(
                    animation.has_facial_animation
                    for animation in self._clip_animations(clip)
                )
            ):
                self.report.issue(
                    "cut.binding.facial_tracks.missing",
                    f"{binding.display_name} enables facial animation but its clip has no facial tracks",
                    severity=_severity(self.context),
                    asset=self.scene.scene_name,
                    path=f"bindings[{object_id}].bFoundFaceAnimation",
                )
            for bone_id in sorted(bone_ids):
                key = (object_id, bone_id)
                if key in seen:
                    continue
                seen.add(key)
                if skeleton is None:
                    valid = bone_id == 0
                else:
                    valid = (
                        skeleton.get_bone_by_tag(bone_id) is not None
                        or skeleton.get_bone_by_index(bone_id) is not None
                    )
                if not valid:
                    self.report.issue(
                        "cut.binding.skeleton.bone_unresolved",
                        f"{binding.display_name} animation references missing bone {bone_id}",
                        severity=_severity(self.context),
                        asset=self.scene.scene_name,
                        path=f"bindings[{object_id}].animation.bones[{bone_id}]",
                    )

    def _validate_expressions(self) -> None:
        peds = tuple(
            binding
            for binding in self.scene.peds
            if isinstance(binding, CutPed) and binding.has_face_animation
        )
        if not peds:
            return

        init_data_by_model: dict[int, list[tuple[CutContextAsset, object]]] = {}
        for asset in self.assets.iter_kind(GameFileType.YMT):
            ymt = self._load(
                asset,
                code="cut.binding.ped_metadata.load_failed",
                path="facial.ped_metadata",
            )
            metadata = getattr(ymt, "ped_metadata", None)
            for item in getattr(metadata, "init_datas", ()):
                init_data_by_model.setdefault(int(item.name.uint), []).append(
                    (asset, item)
                )

        expression_sets: dict[int, tuple[CutContextAsset, object]] | None = None
        for ped in peds:
            reference = self._binding_reference(ped, "StreamingName")
            if reference is None:
                continue
            path = f"bindings[{ped.object_id}].facial"
            matches = init_data_by_model.get(cut_asset_reference_hash(reference), ())
            if not matches:
                self.report.issue(
                    "cut.binding.ped_metadata.unresolved",
                    f"No ped metadata matches {ped.display_name}",
                    severity=_severity(self.context),
                    asset=self.scene.scene_name,
                    path=path,
                )
                continue

            _metadata_asset, init_data = min(
                matches,
                key=lambda item: item[0].source_rank,
            )
            dictionary_reference = getattr(
                init_data, "expression_dictionary_name", None
            )
            expression_names: tuple[object, ...] = ()
            set_reference = getattr(init_data, "expression_set_name", None)
            if not is_null_expression_reference(set_reference):
                if expression_sets is None:
                    expression_sets = self._expression_sets()
                expression_set = expression_sets.get(MetaHash(set_reference).uint)
                if expression_set is None:
                    self.report.issue(
                        "cut.binding.expression_set.unresolved",
                        f"No expression set matches {ped.display_name}",
                        severity=_severity(self.context),
                        asset=self.scene.scene_name,
                        path=path,
                    )
                    continue
                _set_asset, resolved_set = expression_set
                dictionary_reference = resolved_set.dictionary_name
                expression_names = tuple(resolved_set.expression_names)
            elif not is_null_expression_reference(
                getattr(init_data, "expression_name", None)
            ):
                expression_names = (init_data.expression_name,)

            if is_null_expression_reference(dictionary_reference):
                self.report.issue(
                    "cut.binding.yed.reference_missing",
                    f"{ped.display_name} has facial animation without an expression dictionary",
                    severity=_severity(self.context),
                    asset=self.scene.scene_name,
                    path=path,
                )
                continue
            yed_asset = self.assets.find(
                MetaHash(dictionary_reference).uint,
                (GameFileType.YED,),
            )
            if yed_asset is None:
                self.report.issue(
                    "cut.binding.yed.unresolved",
                    f"No YED expression dictionary matches {ped.display_name}",
                    severity=_severity(self.context),
                    asset=self.scene.scene_name,
                    path=path,
                )
                continue
            yed = self._load(
                yed_asset,
                code="cut.binding.yed.load_failed",
                path=path,
            )
            if not isinstance(yed, Yed):
                if yed is not None:
                    self.report.issue(
                        "cut.binding.yed.invalid",
                        f"Asset is not a decoded YED: {yed_asset.path}",
                        severity=_severity(self.context),
                        asset=yed_asset.path,
                        path=path,
                    )
                continue
            for name in expression_names:
                if yed.get_expression(MetaHash(name)) is None:
                    self.report.issue(
                        "cut.binding.yed.expression_unresolved",
                        f"YED {yed_asset.path} is missing an expression required by {ped.display_name}",
                        severity=_severity(self.context),
                        asset=yed_asset.path,
                        path=path,
                    )
            model_entry = self.models.get(ped.object_id)
            skeleton = None
            if model_entry is not None:
                model, model_reference = model_entry
                skeleton = getattr(
                    self._drawable(model, model_reference), "skeleton", None
                )
            for issue in validate_yed(yed, skeleton=skeleton):
                self.report.issue(
                    f"cut.binding.yed.{issue.code}",
                    issue.message,
                    severity=_severity(self.context),
                    asset=yed_asset.path,
                    path=f"{path}.{issue.path}" if issue.path else path,
                )

    def _expression_sets(self) -> dict[int, tuple[CutContextAsset, object]]:
        result: dict[int, tuple[CutContextAsset, object]] = {}
        for asset in self.assets.iter_kind(GameFileType.EXPRESSION_SETS):
            metadata = self._load(
                asset,
                code="cut.binding.expression_set.load_failed",
                path="facial.expression_sets",
            )
            if not isinstance(metadata, PedExpressionSetMetadata):
                if metadata is not None:
                    self.report.issue(
                        "cut.binding.expression_set.invalid",
                        f"Asset is not decoded expression-set metadata: {asset.path}",
                        severity=_severity(self.context),
                        asset=asset.path,
                        path="facial.expression_sets",
                    )
                continue
            for expression_set in metadata.expression_sets:
                result.setdefault(
                    expression_set.name.uint,
                    (asset, expression_set),
                )
        return result

    def _validate_audio(self) -> None:
        references = cut_audio_references(self.scene)
        if not references:
            return
        rels: list[RelFile] = []
        rel_assets = tuple(self.assets.iter_kind(GameFileType.REL))
        for asset in rel_assets:
            rel = self._load(
                asset,
                code="cut.audio.rel.load_failed",
                path="timeline.audio",
            )
            if isinstance(rel, RelFile):
                rels.append(rel)
            elif rel is not None:
                self.report.issue(
                    "cut.audio.rel.invalid",
                    f"Asset is not decoded REL metadata: {asset.path}",
                    severity=_severity(self.context),
                    asset=asset.path,
                    path="timeline.audio",
                )
        hints = cut_audio_container_hints(self.scene, references)
        candidates = tuple(self.assets.iter_kind(GameFileType.AWC))
        sound_index = RelSoundIndex(rels) if rels else None
        for reference in references:
            graph = (
                resolve_cut_audio_sound_graph(sound_index, reference)
                if sound_index is not None
                else None
            )
            if sound_index is not None and graph is None:
                self.report.issue(
                    "cut.audio.sound.unresolved",
                    f"No REL sound matches CUT audio cue {reference!s}",
                    severity=_severity(self.context),
                    asset=self.scene.scene_name,
                    path="timeline.audio",
                )
            if graph is not None:
                self._validate_rel_graph(reference, graph)

            ranked = [
                (rank, asset)
                for asset in candidates
                if (
                    rank := cut_audio_asset_rank(
                        asset,
                        reference,
                        hints.get(reference, ()),
                    )
                )
                is not None
            ]
            if not ranked and graph is not None:
                endpoint_hashes = set(graph.container_hashes)
                ranked = [
                    (2, asset)
                    for asset in candidates
                    if asset.short_hash in endpoint_hashes
                ]
            matches = [
                asset
                for _rank, asset in sorted(
                    ranked,
                    key=lambda item: (
                        item[1].source_rank[0],
                        item[0],
                        item[1].source_rank[1],
                    ),
                )
            ]
            if not matches:
                self.report.issue(
                    "cut.audio.container.unresolved",
                    f"No AWC container matches CUT audio cue {reference!s}",
                    severity=(
                        _severity(self.context)
                        if graph is not None
                        else DiagnosticSeverity.WARNING
                    ),
                    asset=self.scene.scene_name,
                    path="timeline.audio",
                )
                continue
            awc = self._load(
                matches[0],
                code="cut.audio.container.load_failed",
                path="timeline.audio",
            )
            if awc is not None and not hasattr(awc, "streams"):
                self.report.issue(
                    "cut.audio.container.invalid",
                    f"Asset is not a decoded AWC: {matches[0].path}",
                    severity=_severity(self.context),
                    asset=matches[0].path,
                    path="timeline.audio",
                )
            elif isinstance(awc, Awc):
                stream_hashes = graph.stream_hashes if graph is not None else ()
                if stream_hashes:
                    streams: list[AwcStream] = []
                    for stream_hash in stream_hashes:
                        stream = resolve_awc_playback_stream(
                            awc,
                            stream_hash=stream_hash,
                        )
                        if stream is None:
                            self.report.issue(
                                "cut.audio.stream.unresolved",
                                f"AWC {matches[0].path} has no playable stream for 0x{stream_hash:08X}",
                                severity=_severity(self.context),
                                asset=matches[0].path,
                                path="timeline.audio",
                            )
                        elif stream not in streams:
                            streams.append(stream)
                    for stream in streams:
                        self._validate_awc_stream(matches[0], awc, stream)
                else:
                    stream = resolve_awc_playback_stream(
                        awc,
                        fallback_hash=cut_audio_reference_hash(reference),
                    )
                    if stream is None:
                        self.report.issue(
                            "cut.audio.stream.unresolved",
                            f"AWC {matches[0].path} has no unambiguous stream for cue {reference!s}",
                            severity=_severity(self.context),
                            asset=matches[0].path,
                            path="timeline.audio",
                        )
                    else:
                        self._validate_awc_stream(matches[0], awc, stream)

    def _validate_rel_graph(
        self,
        reference: str | int,
        graph: RelSoundGraph,
    ) -> None:
        endpoints = graph.endpoints
        if not endpoints:
            self.report.issue(
                "cut.audio.sound.no_stream",
                f"REL sound for CUT audio cue {reference!s} resolves to no AWC stream",
                severity=_severity(self.context),
                asset=self.scene.scene_name,
                path="timeline.audio",
            )
        for unresolved_hash in graph.unresolved_hashes:
            self.report.issue(
                "cut.audio.sound.child_unresolved",
                f"REL sound graph references missing sound 0x{unresolved_hash:08X}",
                severity=_severity(self.context),
                asset=self.scene.scene_name,
                path="timeline.audio",
            )

    def _validate_awc_stream(
        self,
        asset: CutContextAsset,
        awc: Awc,
        stream: AwcStream,
    ) -> None:
        for issue in validate_awc_stream(awc, stream):
            self.report.issue(
                f"cut.audio.{issue.code}",
                issue.message,
                severity=_severity(self.context),
                asset=asset.path,
                path=f"timeline.audio.{issue.path or 'stream'}",
            )


def validate_cutscene_assets(
    assets: CutsceneAssets,
    *,
    context: BuildContext | None = None,
) -> ValidationReport:
    _validate_ycd_paths(assets, report := ValidationReport())
    scene = _scene_copy(assets)
    validator = None
    if context is not None:
        validator = _CutsceneContextValidator(scene, context, report)
        validator.resolve_ycds()
    _extend_scene_report(assets, scene, report)
    if validator is not None:
        validator.validate()
    return report


__all__ = ["validate_cutscene_assets"]
