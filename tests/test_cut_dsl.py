from __future__ import annotations

import pytest

from fivefury import CutEventType, CutScriptError, parse_cutscript, read_cut, save_cutscript


DSL_SAMPLE = """
CUTSCENE "miku_test"
DURATION 14.0
OFFSET 0.0 0.0 100.0
ROTATION 0.0
FLAGS PLAYABLE SECTIONED STORY_MODE

ASSETS
  ASSET_MANAGER assets
  ANIM_MANAGER anims

  CAMERA cam_wide
  CAMERA cam_close

  PROP stage MODEL "stage01" YTYP "stage01"
  PROP miku MODEL "miku_hatsune" YTYP "miku_pack" ANIM_BASE "miku_hatsune" PRESET COMMON_PROP
  PROP microphone MODEL "mic_01" YTYP "stage_props"

  LIGHT key_light
    TYPE SPOT
    POSITION 0.0 -3.0 4.0
    DIRECTION 0.0 1.0 -0.5
    COLOR 1.0 0.85 0.7
    INTENSITY 4.0
    FALLOFF 12.0
  FADE screen
  OVERLAY title_card

TRACK LOAD
  0.000 SCENE "miku_test"
  0.000 MODELS stage, miku, microphone
  0.000 LOAD_OVERLAYS title_card
  0.000 ANIM_DICT "miku_test"
  0.000 SUBTITLES "miku_subs"

TRACK CAMERA
  0.000 CUT cam_wide NAME "cam_wide_intro" POS 0 -8 3 ROT 0 0 0 NEAR 0.05 FAR 1000
  2.000 DRAW_DISTANCE cam_wide 750
  4.000 CUT cam_close NAME "cam_close_face" POS 0 -3 2 ROT 10 0 0 NEAR 0.05 FAR 500
  9.000 CUT cam_wide NAME "cam_wide_outro" POS 0 -9 3 ROT 0 20 0 NEAR 0.05 FAR 1000

TRACK ANIMATION
  0.033 PLAY miku
  12.500 STOP miku

TRACK OBJECTS
  0.000 SHOW stage, miku
  0.250 ATTACH microphone TO "p_mic_hand"
  0.000 HIDE microphone
  3.000 SHOW microphone
  10.000 HIDE microphone

TRACK FADE
  0.000 OUT screen VALUE 1.0 COLOR 0xff000000
  0.500 IN screen VALUE 0.0 COLOR 0xff000000

TRACK OVERLAYS
  0.500 SHOW title_card
  2.000 HIDE title_card

TRACK LIGHTS
  0.000 ENABLE key_light
  8.000 DISABLE key_light

TRACK SUBTITLES
  1.000 SHOW "SUB_MIKU_001" FOR 3.0
  5.000 SHOW "SUB_MIKU_002" FOR 3.0
  10.000 SHOW "SUB_MIKU_003" FOR 2.5

TRACK AUDIO
  0.000 LOAD "miku_audio"
  0.500 PLAY "song_intro"
  12.500 STOP "song_intro"

TRACK CLEANUP
  13.000 UNLOAD_MODELS stage, miku, microphone
  13.000 UNLOAD_OVERLAYS title_card
  13.000 UNLOAD_ANIM_DICT "miku_test"
  13.000 UNLOAD_SUBTITLES "miku_subs"
  13.500 UNLOAD_SCENE "miku_test"

SAVE "miku_test.cut"
"""


def test_cutscript_parses_video_editor_style_script() -> None:
    result = parse_cutscript(DSL_SAMPLE)
    scene = result.scene

    assert result.save_path is not None
    assert result.save_path.name == "miku_test.cut"
    assert scene.scene_name == "miku_test"
    assert scene.duration == pytest.approx(14.0)
    assert scene.offset == (0.0, 0.0, 100.0)
    assert len(scene.cameras) == 2
    assert len(scene.props) == 3
    assert len(scene.lights) == 1
    assert len(scene.overlays) == 1
    assert scene.props[1].animation_clip_base == "miku_hatsune"
    assert scene.props[1].type_file == "miku_pack"


def test_cutscript_writes_valid_cut_bytes() -> None:
    scene = parse_cutscript(DSL_SAMPLE).scene

    cut = read_cut(scene.to_bytes())

    assert cut.root.fields["fTotalDuration"] == pytest.approx(14.0)
    assert len(cut.objects) >= 10
    assert any(event.fields["iEventId"] == int(CutEventType.CAMERA_CUT) for event in cut.events)
    assert any(event.fields["iEventId"] == int(CutEventType.SET_ANIM) for event in cut.events)
    assert any(event.fields["iEventId"] == int(CutEventType.SHOW_SUBTITLE) for event in cut.events)
    assert any(event.fields["iEventId"] == int(CutEventType.SET_LIGHT) for event in cut.events)
    assert any(event.fields["iEventId"] == int(CutEventType.FADE_IN) for event in cut.events)
    assert any(event.fields["iEventId"] == int(CutEventType.FADE_OUT) for event in cut.events)
    assert any(event.fields["iEventId"] == int(CutEventType.SHOW_OVERLAY) for event in cut.events)
    assert any(event.fields["iEventId"] == int(CutEventType.SET_DRAW_DISTANCE) for event in cut.events)
    assert any(event.fields["iEventId"] == int(CutEventType.SET_ATTACHMENT) for event in cut.events)


def test_cutscript_save_uses_script_save_path(tmp_path) -> None:
    script = tmp_path / "sample.cuts"
    script.write_text(DSL_SAMPLE, encoding="utf-8")

    output = save_cutscript(script)

    assert output == tmp_path / "miku_test.cut"
    assert output.is_file()


def test_cutscript_reports_line_errors() -> None:
    with pytest.raises(CutScriptError) as excinfo:
        parse_cutscript(
            """
CUTSCENE "bad"
DURATION 5
TRACK CAMERA
  0.0 CUT missing_camera FAR 1000
"""
        )

    assert excinfo.value.line == 5
    assert excinfo.value.code == "asset.unknown"
    assert "missing_camera" in str(excinfo.value)
