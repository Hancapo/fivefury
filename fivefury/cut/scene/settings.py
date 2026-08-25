from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntFlag
from typing import TYPE_CHECKING

from ..flags import CutSceneFlags, unpack_cutscene_flags

if TYPE_CHECKING:
    from .base import CutScene


class CutSectioningMode(IntFlag):
    NONE = 0
    CAMERA_CUTS = 1 << 0
    DURATION = 1 << 1
    SPLIT = 1 << 2


class CutConcatMode(IntFlag):
    NONE = 0
    INTERNAL = 1 << 0
    EXTERNAL = 1 << 1


_BOOLEAN_FLAGS = (
    ("fade_in_game", CutSceneFlags.FADE_IN_GAME),
    ("fade_out_game", CutSceneFlags.FADE_OUT_GAME),
    ("fade_in_cutscene", CutSceneFlags.FADE_IN_CUTSCENE),
    ("fade_out_cutscene", CutSceneFlags.FADE_OUT_CUTSCENE),
    ("short_fade_out", CutSceneFlags.SHORT_FADE_OUT),
    ("long_fade_out", CutSceneFlags.LONG_FADE_OUT),
    ("fade_between_sections", CutSceneFlags.FADE_BETWEEN_SECTIONS),
    ("no_ambient_lights", CutSceneFlags.NO_AMBIENT_LIGHTS),
    ("no_vehicle_lights", CutSceneFlags.NO_VEHICLE_LIGHTS),
    ("mute_music_player", CutSceneFlags.MUTE_MUSIC_PLAYER),
    ("leak_radio", CutSceneFlags.LEAK_RADIO),
    ("translate_bone_ids", CutSceneFlags.TRANSLATE_BONE_IDS),
    ("interpolate_camera", CutSceneFlags.INTERP_CAMERA),
    ("sectioned", CutSceneFlags.IS_SECTIONED),
    ("use_parent_scale", CutSceneFlags.USE_PARENT_SCALE),
    ("use_one_scene_orientation", CutSceneFlags.USE_ONE_SCENE_ORIENTATION),
    ("enable_depth_of_field", CutSceneFlags.ENABLE_DEPTH_OF_FIELD),
    ("stream_processed", CutSceneFlags.STREAM_PROCESSED),
    ("use_story_mode", CutSceneFlags.USE_STORY_MODE),
    ("use_in_game_dof_start", CutSceneFlags.USE_IN_GAME_DOF_START),
    ("use_in_game_dof_end", CutSceneFlags.USE_IN_GAME_DOF_END),
    ("use_catchup_camera", CutSceneFlags.USE_CATCHUP_CAMERA),
    ("part", CutSceneFlags.PART),
    ("use_audio_events_concat", CutSceneFlags.USE_AUDIO_EVENTS_CONCAT),
    (
        "use_in_game_dof_start_second_cut",
        CutSceneFlags.USE_IN_GAME_DOF_START_SECOND_CUT,
    ),
)


@dataclass(slots=True)
class CutSceneSettings:
    """Semantic CUT authoring settings used to derive the serialized flags.

    ``None`` selects structural inference where possible and the retail
    authoring default otherwise. Values read from a CUT are always explicit.
    """

    fade_in_game: bool = False
    fade_out_game: bool = False
    fade_in_cutscene: bool = False
    fade_out_cutscene: bool = False
    short_fade_out: bool = False
    long_fade_out: bool = False
    fade_between_sections: bool = False
    no_ambient_lights: bool = False
    no_vehicle_lights: bool = False
    use_one_audio: bool | None = None
    mute_music_player: bool = False
    leak_radio: bool = False
    translate_bone_ids: bool = False
    interpolate_camera: bool = False
    sectioned: bool = True
    sectioning: CutSectioningMode | None = None
    use_parent_scale: bool = False
    use_one_scene_orientation: bool = False
    enable_depth_of_field: bool = False
    stream_processed: bool = False
    use_story_mode: bool = True
    use_in_game_dof_start: bool = True
    use_in_game_dof_end: bool = False
    use_catchup_camera: bool = False
    use_blend_out_camera: bool | None = None
    part: bool = False
    concat: CutConcatMode | None = None
    use_audio_events_concat: bool = False
    use_in_game_dof_start_second_cut: bool = False

    @classmethod
    def from_flags(cls, value: CutSceneFlags | int | Sequence[int]) -> CutSceneSettings:
        flags = unpack_cutscene_flags(value)
        settings = cls(
            use_one_audio=bool(flags & CutSceneFlags.USE_ONE_AUDIO),
            sectioning=CutSectioningMode.NONE,
            use_blend_out_camera=bool(flags & CutSceneFlags.USE_BLENDOUT_CAMERA),
            concat=CutConcatMode.NONE,
        )
        for field_name, flag in _BOOLEAN_FLAGS:
            setattr(settings, field_name, bool(flags & flag))
        if flags & CutSceneFlags.SECTION_BY_CAMERA_CUTS:
            settings.sectioning |= CutSectioningMode.CAMERA_CUTS
        if flags & CutSceneFlags.SECTION_BY_DURATION:
            settings.sectioning |= CutSectioningMode.DURATION
        if flags & CutSceneFlags.SECTION_BY_SPLIT:
            settings.sectioning |= CutSectioningMode.SPLIT
        if flags & CutSceneFlags.INTERNAL_CONCAT:
            settings.concat |= CutConcatMode.INTERNAL
        if flags & CutSceneFlags.EXTERNAL_CONCAT:
            settings.concat |= CutConcatMode.EXTERNAL
        return settings


def _resolved_sectioning(scene: CutScene) -> CutSectioningMode:
    if scene.settings.sectioning is not None:
        return scene.settings.sectioning
    if scene.camera_cut_list:
        return CutSectioningMode.CAMERA_CUTS
    if scene.section_split_list:
        return CutSectioningMode.SPLIT
    if scene.section_by_time_slice_duration is not None:
        return CutSectioningMode.DURATION
    return CutSectioningMode.NONE


def derive_cutscene_flags(scene: CutScene) -> CutSceneFlags:
    settings = scene.settings
    flags = CutSceneFlags.NONE
    for field_name, flag in _BOOLEAN_FLAGS:
        if getattr(settings, field_name):
            flags |= flag

    use_one_audio = settings.use_one_audio
    if use_one_audio is None:
        use_one_audio = any(
            binding.type_name == "rage__cutfAudioObject" for binding in scene.bindings
        )
    if use_one_audio:
        flags |= CutSceneFlags.USE_ONE_AUDIO

    sectioning = _resolved_sectioning(scene)
    if sectioning & CutSectioningMode.CAMERA_CUTS:
        flags |= CutSceneFlags.SECTION_BY_CAMERA_CUTS
    if sectioning & CutSectioningMode.DURATION:
        flags |= CutSceneFlags.SECTION_BY_DURATION
    if sectioning & CutSectioningMode.SPLIT:
        flags |= CutSceneFlags.SECTION_BY_SPLIT

    use_blend_out_camera = settings.use_blend_out_camera
    if use_blend_out_camera is None:
        use_blend_out_camera = bool(
            scene.blend_out_cutscene_duration or scene.blend_out_cutscene_offset
        )
    if use_blend_out_camera:
        flags |= CutSceneFlags.USE_BLENDOUT_CAMERA

    concat = settings.concat
    if concat is None:
        concat = CutConcatMode.EXTERNAL
    if concat & CutConcatMode.INTERNAL:
        flags |= CutSceneFlags.INTERNAL_CONCAT
    if concat & CutConcatMode.EXTERNAL:
        flags |= CutSceneFlags.EXTERNAL_CONCAT
    return flags


__all__ = [
    "CutConcatMode",
    "CutSceneSettings",
    "CutSectioningMode",
    "derive_cutscene_flags",
]
