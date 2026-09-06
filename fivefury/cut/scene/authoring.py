from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING

from ...authoring.operation import (
    AuthoringOperation,
    AuthoringProgress,
    AuthoringStage,
    iter_authoring_units,
)
from ...common import atomic_write_files
from ...game_target import GameTarget
from ...hashing import jenk_partial_hash
from ...vector import Quaternion, Vector3
from ..payloads import CutAnimationDictPayload, CutCameraCutPayload, CutLoadScenePayload
from .animation_dictionary import CutsceneAnimationDictionary
from .base import CutScene
from .bindings import CutAudio, CutBinding, CutCamera, CutFacialAnimationMode, CutPed
from .io import read_cut_scene

if TYPE_CHECKING:
    from ...authoring import BuildContext, ValidationReport
    from ...ycd.cutscene import (
        YcdCutsceneBoneAnimation,
        YcdCutsceneBuilder,
        YcdFacialTrackSet,
    )
    from ...ycd.model import Ycd
    from ..audio_authoring import CutsceneAudioAssets
    from ..model import CutFile
    from .timeline import CutTimelineEvent


def _file_name(value: str, suffix: str) -> str:
    name = Path(str(value)).name
    return name if name.lower().endswith(suffix) else f"{name}{suffix}"


@dataclass(slots=True)
class CutsceneAssets:
    scene: CutScene
    audio: tuple[CutsceneAudioAssets, ...] = ()
    cut_name: str | None = None

    @property
    def output_name(self) -> str:
        return _file_name(self.cut_name or self.scene.scene_name or "cutscene", ".cut")

    def validate(
        self,
        *,
        context: BuildContext | None = None,
        operation: AuthoringOperation | None = None,
    ) -> ValidationReport:
        from .asset_validation import validate_cutscene_assets

        return validate_cutscene_assets(self, context=context, operation=operation)

    def build(self, *, operation: AuthoringOperation | None = None) -> CutsceneAssets:
        dictionary = self.scene.animation_dictionary
        for ycd in iter_authoring_units(
            dictionary.sections if dictionary else (),
            operation,
            AuthoringStage.BUILD,
            self.output_name,
        ):
            ycd.build(operation=operation)
        self.scene.build()
        return self

    def build_files(
        self,
        *,
        context: BuildContext | None = None,
        template: CutFile | bytes | str | Path | None = None,
        operation: AuthoringOperation | None = None,
    ) -> dict[str, bytes]:
        from ...ycd.reader import read_ycd
        from ...ycd.write import build_ycd_bytes
        from .asset_validation import _inspect_cutscene_assets

        self.build(operation=operation)
        scene, report = _inspect_cutscene_assets(
            self, context=context, operation=operation
        )
        report.raise_for_errors()
        files: dict[str, bytes] = {}
        rebuilt_ycds: list[Ycd] = []
        rebuilt_audio: list[CutsceneAudioAssets] = []
        dictionary = scene.animation_dictionary
        for ycd in iter_authoring_units(
            dictionary.sections if dictionary else (),
            operation,
            AuthoringStage.WRITE,
            self.output_name,
        ):
            name = _file_name(ycd.path or "cutscene", ".ycd")
            data = build_ycd_bytes(ycd, operation=operation)
            rebuilt = read_ycd(data)
            rebuilt.path = name
            rebuilt.build(operation=operation)
            rebuilt_ycds.append(rebuilt)
            files[name] = data

        from ...awc import read_awc
        from ...rel import read_rel
        from ..audio_authoring import CutsceneAudioAssets

        for audio in iter_authoring_units(
            self.audio, operation, AuthoringStage.WRITE, self.output_name
        ):
            audio_files = audio.build_files()
            files.update(audio_files)
            rebuilt_audio.append(
                CutsceneAudioAssets(
                    reference=audio.reference,
                    awc=read_awc(audio_files[audio.awc_name], path=audio.awc_name),
                    sounds=read_rel(
                        audio_files[
                            f"{audio.sounds_name}{int(audio.sounds.rel_type)}.rel"
                        ],
                        path=audio.sounds_name,
                    ),
                    awc_name=audio.awc_name,
                    sounds_name=audio.sounds_name,
                    wavepack_name=audio.wavepack_name,
                    game=audio.game,
                    channels=audio.channels,
                    codec=audio.codec,
                )
            )

        cut_data = scene.to_bytes(template=template, operation=operation)
        rebuilt_scene = read_cut_scene(cut_data)
        if dictionary is not None:
            rebuilt_scene.animation_dictionary = CutsceneAnimationDictionary(
                reference=dictionary.reference,
                sections=rebuilt_ycds,
            )
        CutsceneAssets(
            scene=rebuilt_scene,
            audio=tuple(rebuilt_audio),
            cut_name=self.output_name,
        ).validate(context=context, operation=operation).raise_for_errors()
        files[self.output_name] = cut_data
        return files

    def save(
        self,
        directory: str | Path,
        *,
        context: BuildContext | None = None,
        template: CutFile | bytes | str | Path | None = None,
        operation: AuthoringOperation | None = None,
    ) -> list[Path]:
        files = self.build_files(
            context=context, template=template, operation=operation
        )
        target = Path(directory)

        def prepare(path: Path, index: int, total: int) -> None:
            if operation is not None:
                operation.checkpoint(
                    AuthoringProgress(AuthoringStage.WRITE, str(path), index, total)
                )

        return atomic_write_files(
            {target / name: data for name, data in files.items()}, prepare=prepare
        )


class CutsceneProject:
    def __init__(self, scene: CutScene, animations: YcdCutsceneBuilder) -> None:
        self.scene = scene
        self.animations = animations
        self.asset_manager = scene.asset_manager("assets")
        self.animation_manager = scene.animation_manager("animations")
        self.scene.animation_dictionary = CutsceneAnimationDictionary()
        self._animated_binding_ids: set[int] = set()
        self._animation_teardown: list[CutTimelineEvent] = []
        self._animation_load: CutTimelineEvent | None = None
        self._animation_load_reference: str | None = None
        self.audio_assets: list[CutsceneAudioAssets] = []
        self.scene.load_scene(
            0.0,
            CutLoadScenePayload(scene.scene_name or animations.name),
            target=self.asset_manager,
        )

    @classmethod
    def create(
        cls,
        name: str,
        *,
        duration: float,
        offset: Vector3 = Vector3(),
        rotation: float = 0.0,
        camera_cuts: list[float] | None = None,
        fps: float = 30.0,
        game: str | GameTarget = GameTarget.GTA5,
    ) -> CutsceneProject:
        from ...ycd.cutscene import YcdCutsceneBuilder

        scene = CutScene.create(
            scene_name=name,
            duration=duration,
            offset=offset,
            rotation=rotation,
            camera_cut_list=camera_cuts or [],
        )
        animations = YcdCutsceneBuilder.from_cut(scene, name=name, fps=fps, game=game)
        return cls(scene, animations)

    def _require_binding(self, binding: CutBinding) -> CutBinding:
        current = self.scene.get_binding(binding.object_id)
        if current is not binding:
            raise ValueError("Cutscene binding does not belong to this project")
        return binding

    def _load_model(self, binding: CutBinding, *, start: float = 0.0) -> None:
        self._require_binding(binding)
        for event in self.scene.timeline:
            if event.event_name != "load_models" or float(event.start) != float(start):
                continue
            object_ids = event.payload.get("iObjectIdList")
            if isinstance(object_ids, list):
                if binding.object_id not in object_ids:
                    object_ids.append(binding.object_id)
                return
        self.scene.load_models(start, [binding.object_id], target=self.asset_manager)

    def model(self, binding: CutBinding, *, load_at: float = 0.0) -> CutBinding:
        self._load_model(binding, start=load_at)
        return binding

    def _bind_animation(self, binding: CutBinding, *, start: float) -> None:
        dictionary = self.scene.animation_dictionary
        if dictionary is None:
            raise RuntimeError("Cutscene project has no animation dictionary")
        if not any(
            event.event_name == "load_anim_dict" for event in self.scene.timeline
        ):
            self._animation_load = self.scene.load_anim_dict(
                0.0,
                dictionary.reference,
                target=self.animation_manager,
            )
            self._animation_load_reference = dictionary.reference
        if binding.object_id in self._animated_binding_ids:
            raise ValueError(
                f"{binding.name or binding.object_id!r} is already animated"
            )
        self.scene.set_anim(float(start), binding, target=self.animation_manager)
        self._animated_binding_ids.add(binding.object_id)

    def animate(
        self,
        binding: CutBinding,
        *,
        clip: str | None = None,
        start: float = 0.0,
        position: Vector3 | Mapping[float, Vector3] | None = None,
        rotation: Quaternion | Mapping[float, Quaternion] | None = None,
        mover_position: Vector3 | Mapping[float, Vector3] | None = None,
        mover_rotation: Quaternion | Mapping[float, Quaternion] | None = None,
        bone_id: int = 0,
        bones: Mapping[int, YcdCutsceneBoneAnimation | Mapping[str, object]]
        | None = None,
        facial: YcdFacialTrackSet | None = None,
    ) -> CutBinding:
        from ...ycd.cutscene import YcdFacialTrackSet

        self._require_binding(binding)
        if facial is not None:
            if not isinstance(facial, YcdFacialTrackSet):
                raise TypeError("facial must be a YcdFacialTrackSet")
            if not isinstance(binding, CutPed):
                raise ValueError("Facial animation requires a ped binding")
        if binding.role not in {"ped", "prop", "vehicle"}:
            raise ValueError(
                f"Cutscene role '{binding.role}' cannot use object animation tracks"
            )
        if all(
            value is None
            for value in (
                position,
                rotation,
                mover_position,
                mover_rotation,
                bones,
                facial,
            )
        ):
            raise ValueError(
                "Object animation requires at least one transform, bone or facial track"
            )
        self._load_model(binding)
        clip_name = (
            clip or getattr(binding, "animation_clip_base", None) or binding.name
        )
        if not clip_name:
            raise ValueError("Animated cutscene objects require a clip name")
        if facial is not None:
            clip_name = clip_name.removesuffix("_dual")
        if hasattr(binding, "animation_clip_base"):
            binding.animation_clip_base = clip_name
        self.animations.object(
            clip_name,
            position=position,
            rotation=rotation,
            mover_position=mover_position,
            mover_rotation=mover_rotation,
            bone_id=bone_id,
            bones=bones,
        )
        if facial is not None:
            self.animations.facial_animation(clip_name, facial)
            binding.configure_facial_animation(CutFacialAnimationMode.MERGED)
        self._bind_animation(binding, start=start)
        return binding

    def camera(
        self,
        name: str = "exportcamera",
        *,
        start: float = 0.0,
        position: Vector3 | Mapping[float, Vector3] | None = None,
        rotation: Quaternion | Mapping[float, Quaternion] | None = None,
        field_of_view: object | None = None,
        near_clip: float = 0.05,
        far_clip: float = 1000.0,
        cut_name: str | None = None,
        cut_position: Vector3 | None = None,
        cut_rotation: Quaternion | None = None,
        **tracks: object,
    ) -> CutCamera:
        if self.scene.cameras:
            raise ValueError(
                "A cutscene project has one runtime camera; use camera_cut() "
                "to author additional shots"
            )
        animated = any(
            value is not None
            for value in (position, rotation, field_of_view, *tracks.values())
        )
        camera = self.scene.camera(
            name,
            animation_streaming_base=(jenk_partial_hash(name) if animated else None),
            near_draw_distance=near_clip,
            far_draw_distance=far_clip,
        )
        if animated:
            self.animations.camera(
                name,
                position=position,
                rotation=rotation,
                field_of_view=field_of_view,
                **tracks,
            )
            self._bind_animation(camera, start=start)
        self.camera_cut(
            camera,
            start=start,
            name=cut_name,
            position=cut_position,
            rotation=cut_rotation,
        )
        return camera

    def camera_cut(
        self,
        camera: CutCamera,
        *,
        start: float,
        name: str | None = None,
        position: Vector3 | None = None,
        rotation: Quaternion | None = None,
    ) -> CutTimelineEvent:
        self._require_binding(camera)
        if camera.role != "camera":
            raise ValueError("Camera cuts must target the project runtime camera")
        sample = self.animations.sample_camera(camera.name or "", start)
        cut_position = position if position is not None else sample.position
        cut_rotation = rotation if rotation is not None else sample.rotation
        if camera.animation_streaming_base is not None and (
            cut_position is None or cut_rotation is None
        ):
            raise ValueError(
                "Animated camera cuts require position and rotation tracks "
                "or explicit cut pose values"
            )
        cut_position = Vector3() if cut_position is None else cut_position
        cut_rotation = Quaternion() if cut_rotation is None else cut_rotation
        return self.scene.camera_cut(
            start,
            camera,
            CutCameraCutPayload(
                name or camera.name or "exportcamera",
                position=cut_position,
                rotation_quaternion=cut_rotation,
                near_draw_distance=float(camera.near_draw_distance or 0.0),
                far_draw_distance=float(camera.far_draw_distance or 0.0),
            ),
        )

    def audio(
        self,
        assets: CutsceneAudioAssets,
        *,
        start: float = 0.0,
        offset: float = 0.0,
        stop: float | None = None,
    ) -> CutAudio:
        from ..audio_authoring import CutsceneAudioAssets

        if not isinstance(assets, CutsceneAudioAssets):
            raise TypeError(
                f"expected CutsceneAudioAssets, got {type(assets).__name__}"
            )
        assets.validate().raise_for_errors()
        start_time = float(start)
        offset_time = float(offset)
        stop_time = float(self.scene.duration or 0.0) if stop is None else float(stop)
        if not all(isfinite(value) for value in (start_time, offset_time, stop_time)):
            raise ValueError("CUT audio times must be finite")
        if start_time < 0.0 or offset_time < 0.0 or stop_time <= start_time:
            raise ValueError(
                "CUT audio requires non-negative start/offset and stop after start"
            )
        if stop_time > float(self.scene.duration or 0.0):
            raise ValueError("CUT audio stop cannot exceed the cutscene duration")
        if any(
            current.reference.casefold() == assets.reference.casefold()
            for current in self.audio_assets
        ):
            raise ValueError(
                f"CUT audio reference {assets.reference!r} is already bound"
            )
        if offset_time + stop_time > assets.duration + 1e-6:
            raise ValueError(
                "CUT audio offset and stop exceed the mastered AWC duration"
            )

        binding = self.scene.audio(
            assets.reference,
            fields={"fOffset": offset_time},
        )
        self.scene.load_audio(start_time, assets.reference, target=binding)
        self.scene.play_audio(start_time, binding, assets.reference)
        self.scene.stop_audio(stop_time, binding, assets.reference)
        self.audio_assets.append(assets)
        return binding

    def build(
        self,
        *,
        cut_name: str | None = None,
        operation: AuthoringOperation | None = None,
    ) -> CutsceneAssets:
        from .shared import _runtime_animation_section_starts

        if operation is not None:
            operation.checkpoint()
        self.animations.duration = float(self.scene.duration or 0.0)
        self.animations.camera_cuts = list(
            _runtime_animation_section_starts(self.scene)[1:]
        )
        dictionary = self.scene.animation_dictionary
        if dictionary is not None:
            dictionary.sections = list(self.animations.build_ycds(operation=operation))
            if (
                self._animation_load is not None
                and self._animation_load.label == self._animation_load_reference
                and self._animation_load.payload.get("cName")
                == self._animation_load_reference
            ):
                self._animation_load.label = dictionary.reference
                self._animation_load.payload = CutAnimationDictPayload(
                    dictionary.reference
                ).to_fields()
                self._animation_load_reference = dictionary.reference
        generated = {id(event) for event in self._animation_teardown}
        for track in self.scene.tracks:
            track.events[:] = [
                event for event in track.events if id(event) not in generated
            ]
        self._animation_teardown.clear()
        if self._animated_binding_ids:
            end = float(self.scene.duration or 0.0)
            for object_id in sorted(self._animated_binding_ids):
                event = self.scene.clear_anim(
                    end,
                    object_id,
                    target=self.animation_manager,
                )
                self._animation_teardown.append(event)
            if dictionary is not None:
                event = self.scene.unload_anim_dict(
                    end,
                    dictionary.reference,
                    target=self.animation_manager,
                )
                self._animation_teardown.append(event)
        return CutsceneAssets(
            scene=self.scene,
            audio=tuple(self.audio_assets),
            cut_name=cut_name,
        )


__all__ = ["CutsceneAssets", "CutsceneProject"]
