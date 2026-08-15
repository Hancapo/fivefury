from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ...common import atomic_write_bytes
from ...game_target import GameTarget
from ...hashing import jenk_partial_hash
from ...vector import vec3, vec4
from ..payloads import CutCameraCutPayload, CutLoadScenePayload
from .base import CutScene
from .bindings import CutBinding, CutCamera
from .io import read_cut_scene

if TYPE_CHECKING:
    from ...authoring import BuildContext, ValidationReport
    from ...ycd.cutscene import YcdCutsceneBoneAnimation, YcdCutsceneBuilder
    from ...ycd.model import Ycd
    from ..model import CutFile
    from .timeline import CutTimelineEvent


def _file_name(value: str, suffix: str) -> str:
    name = Path(str(value)).name
    return name if name.lower().endswith(suffix) else f"{name}{suffix}"


@dataclass(slots=True)
class CutsceneAssets:
    scene: CutScene
    ycds: tuple[Ycd, ...] = ()
    cut_name: str | None = None

    @property
    def output_name(self) -> str:
        return _file_name(self.cut_name or self.scene.scene_name or "cutscene", ".cut")

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        from .asset_validation import validate_cutscene_assets

        return validate_cutscene_assets(self, context=context)

    def build(self) -> CutsceneAssets:
        for ycd in self.ycds:
            ycd.build()
        self.scene.clip_dicts = list(self.ycds)
        self.scene.build()
        return self

    def build_files(
        self,
        *,
        context: BuildContext | None = None,
        template: CutFile | bytes | str | Path | None = None,
    ) -> dict[str, bytes]:
        from ...ycd.reader import read_ycd
        from ...ycd.write import build_ycd_bytes

        self.build()
        self.validate(context=context).raise_for_errors()
        files: dict[str, bytes] = {}
        rebuilt_ycds: list[Ycd] = []
        for ycd in self.ycds:
            name = _file_name(ycd.path or "cutscene", ".ycd")
            data = build_ycd_bytes(ycd)
            rebuilt = read_ycd(data)
            rebuilt.path = name
            rebuilt.build()
            rebuilt_ycds.append(rebuilt)
            files[name] = data

        cut_data = self.scene.to_bytes(template=template)
        rebuilt_scene = read_cut_scene(cut_data)
        rebuilt_scene.clip_dicts = rebuilt_ycds
        CutsceneAssets(
            scene=rebuilt_scene,
            ycds=tuple(rebuilt_ycds),
            cut_name=self.output_name,
        ).validate().raise_for_errors()
        files[self.output_name] = cut_data
        return files

    def save(
        self,
        directory: str | Path,
        *,
        context: BuildContext | None = None,
        template: CutFile | bytes | str | Path | None = None,
    ) -> list[Path]:
        files = self.build_files(context=context, template=template)
        target = Path(directory)
        return [atomic_write_bytes(target / name, data) for name, data in files.items()]


class CutsceneProject:
    def __init__(self, scene: CutScene, animations: YcdCutsceneBuilder) -> None:
        self.scene = scene
        self.animations = animations
        self.asset_manager = scene.asset_manager("assets")
        self.animation_manager = scene.animation_manager("animations")
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
        offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
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

    def _load_animation_sections(self) -> None:
        existing = {
            (round(float(event.start), 6), str(event.label or "").lower())
            for event in self.scene.timeline
            if event.event_name == "load_anim_dict"
        }
        for section in self.animations.sections:
            index = self.animations.section_index_start + section.index
            dictionary = f"{self.animations.name}-{index}"
            key = (round(section.start_time, 6), dictionary.lower())
            if key not in existing:
                self.scene.load_anim_dict(
                    section.start_time, dictionary, target=self.animation_manager
                )
                existing.add(key)

    def _bind_animation_sections(
        self, binding: CutBinding, *, start: float
    ) -> None:
        for section in self.animations.sections:
            event_time = max(float(start), section.start_time)
            if event_time <= section.end_time:
                self.scene.set_anim(
                    event_time, binding, target=self.animation_manager
                )

    def animate(
        self,
        binding: CutBinding,
        *,
        clip: str | None = None,
        start: float = 0.0,
        position: object | None = None,
        rotation: object | None = None,
        mover_position: object | None = None,
        mover_rotation: object | None = None,
        bone_id: int = 0,
        bones: Mapping[int, YcdCutsceneBoneAnimation | Mapping[str, object]]
        | None = None,
    ) -> CutBinding:
        self._require_binding(binding)
        if binding.role not in {"ped", "prop", "vehicle"}:
            raise ValueError(
                f"Cutscene role '{binding.role}' cannot use object animation tracks"
            )
        if all(
            value is None
            for value in (position, rotation, mover_position, mover_rotation, bones)
        ):
            raise ValueError(
                "Object animation requires at least one transform or bone track"
            )
        self._load_model(binding)
        clip_name = (
            clip or getattr(binding, "animation_clip_base", None) or binding.name
        )
        if not clip_name:
            raise ValueError("Animated cutscene objects require a clip name")
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
        self._load_animation_sections()
        self._bind_animation_sections(binding, start=start)
        return binding

    def camera(
        self,
        name: str = "exportcamera",
        *,
        start: float = 0.0,
        position: object | None = None,
        rotation: object | None = None,
        field_of_view: object | None = None,
        near_clip: float = 0.05,
        far_clip: float = 1000.0,
        cut_name: str | None = None,
        cut_position: object | None = None,
        cut_rotation: object | None = None,
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
            animation_streaming_base=(
                jenk_partial_hash(name) if animated else None
            ),
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
            self._load_animation_sections()
            self._bind_animation_sections(camera, start=start)
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
        position: object | None = None,
        rotation: object | None = None,
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
        cut_position = (0.0, 0.0, 0.0) if cut_position is None else vec3(cut_position)
        cut_rotation = (
            (0.0, 0.0, 0.0, 1.0)
            if cut_rotation is None
            else vec4(cut_rotation)
        )
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

    def build(self, *, cut_name: str | None = None) -> CutsceneAssets:
        return CutsceneAssets(
            scene=self.scene,
            ycds=tuple(self.animations.build_ycds()),
            cut_name=cut_name,
        )


__all__ = ["CutsceneAssets", "CutsceneProject"]
