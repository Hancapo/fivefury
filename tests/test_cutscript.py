from __future__ import annotations

from fivefury import cutscene_from_cutscript, cutscript_from_scene


def test_cutscript_dispatch_round_trip() -> None:
    source = """
CUTSCENE dispatch
DURATION 3
OFFSET 1 2 3
ASSETS
  ASSET_MANAGER assets
  ANIM_MANAGER anims
  CAMERA camera
  STATIC_PROP stage
  MODEL stage
  YTYP stage
  LIGHT key
  TYPE POINT
  POSITION 1 2 3
  COLOR #ff8040
  INTENSITY 2
  STATIC true
  AUDIO audio
  SUBTITLE subtitles
END
TRACK LOAD
  0 SCENE stage
  0 MODELS stage
  0 ANIM_DICT dance
  0 LOAD song
  0 SUBTITLES dialog
END
TRACK CAMERA
  0 CUT camera
    NAME shot
    POS 1 2 3
    QUAT 0 0 0 1
    NEAR 0.1
    FAR 1000
END
TRACK ANIMATION
  0 PLAY stage CLIP idle
  1 STOP stage
END
TRACK LIGHTS
  0 ENABLE key
  2 DISABLE key
END
TRACK SUBTITLES
  0 SHOW hello FOR 1
  1 HIDE hello
END
"""

    scene = cutscene_from_cutscript(source)
    rendered = cutscript_from_scene(scene, include_comments=False)
    reparsed = cutscene_from_cutscript(rendered)

    assert len(scene.bindings) == len(reparsed.bindings) == 7
    assert len(scene.timeline) == len(reparsed.timeline) == 12
    assert {event.kind for event in reparsed.timeline} == {
        "camera_cut",
        "clear_anim",
        "clear_light",
        "hide_subtitle",
        "load_anim_dict",
        "load_audio",
        "load_models",
        "load_scene",
        "load_subtitles",
        "set_anim",
        "set_light",
        "show_subtitle",
    }
