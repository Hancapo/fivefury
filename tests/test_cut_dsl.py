from __future__ import annotations

import pytest

from fivefury import (
    CutDecalPayload,
    CutEventType,
    CutSceneFlags,
    CutScreenFadePayload,
    CutScriptError,
    GrassInstance,
    LightAttrDef,
    LodLight,
    YdrLight,
    parse_bound_material_names,
    parse_css_argb,
    parse_css_rgb,
    parse_css_rgb_unit,
    parse_css_rgba,
    parse_cutscript,
    read_cut,
    save_cutscript,
)
from fivefury.ydr import YdrMeshInput, paint_mesh


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

  PROP stage:
    MODEL "stage01"
    YTYP "stage01"
  PROP miku:
    MODEL "miku_hatsune"
    YTYP "miku_pack"
    ANIM_BASE "miku_hatsune"
    PRESET COMMON_PROP
  PROP microphone MODEL "mic_01" YTYP "stage_props"

  LIGHT key_light:
    TYPE SPOT
    POSITION 0.0 -3.0 4.0
    DIRECTION 0.0 1.0 -0.5
    COLOR #ffd9b3
    INTENSITY 4.0
    FALLOFF 12.0
  FADE screen
  OVERLAY title_card
END

TRACK LOAD
  0.000 SCENE "miku_test"
  0.000 MODELS stage, miku, microphone
  0.000 LOAD_OVERLAYS title_card
  0.000 ANIM_DICT "miku_test"
  0.000 SUBTITLES "miku_subs"
END

TRACK CAMERA
  0.000 CUT cam_wide:
    NAME "cam_wide_intro"
    POS 0 -8 3
    ROT 0 0 0
    NEAR 0.05
    FAR 1000
  2.000 DRAW_DISTANCE cam_wide 750
  4.000 CUT cam_close:
    NAME "cam_close_face"
    POS 0 -3 2
    ROT 10 0 0
    NEAR 0.05
    FAR 500
  9.000 CUT cam_wide NAME "cam_wide_outro" POS 0 -9 3 ROT 0 20 0 NEAR 0.05 FAR 1000
END

TRACK ANIMATION
  0.033 PLAY miku
  12.500 STOP miku
END

TRACK OBJECTS
  0.000 SHOW stage, miku
  0.250 ATTACH microphone TO "p_mic_hand"
  0.000 HIDE microphone
  3.000 SHOW microphone
  10.000 HIDE microphone
END

TRACK FADE
  0.000 OUT screen VALUE 1.0 COLOR black
  0.500 IN screen VALUE 0.0 COLOR rgba(0 0 0 / 100%)
END

TRACK OVERLAYS
  0.500 SHOW title_card
  2.000 HIDE title_card
END

TRACK LIGHTS
  0.000 ENABLE key_light
  8.000 DISABLE key_light
END

TRACK SUBTITLES
  1.000 SHOW "SUB_MIKU_001" FOR 3.0
  5.000 SHOW "SUB_MIKU_002" FOR 3.0
  10.000 SHOW "SUB_MIKU_003" FOR 2.5
END

TRACK AUDIO
  0.000 LOAD "miku_audio"
  0.500 PLAY "song_intro"
  12.500 STOP "song_intro"
END

TRACK CLEANUP
  13.000 UNLOAD_MODELS stage, miku, microphone
  13.000 UNLOAD_OVERLAYS title_card
  13.000 UNLOAD_ANIM_DICT "miku_test"
  13.000 UNLOAD_SUBTITLES "miku_subs"
  13.500 UNLOAD_SCENE "miku_test"
END

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
END
"""
        )

    assert excinfo.value.line == 5
    assert excinfo.value.code == "asset.unknown"
    assert "missing_camera" in str(excinfo.value)


def test_cutscript_accepts_all_cutscene_flags() -> None:
    flag_names = [flag.name for flag in CutSceneFlags if flag.name is not None]
    script = f"""
CUTSCENE "flags"
DURATION 1
FLAGS {" ".join(flag_names)}
"""

    scene = parse_cutscript(script).scene
    expected = CutSceneFlags.NONE
    for flag in CutSceneFlags:
        expected |= flag

    assert scene.cutscene_flags == expected


def test_cutscript_requires_explicit_section_end() -> None:
    with pytest.raises(CutScriptError) as excinfo:
        parse_cutscript(
            """
CUTSCENE "bad"
ASSETS
  CAMERA cam
TRACK CAMERA
  0.000 CUT cam
END
"""
        )

    assert excinfo.value.line == 5
    assert excinfo.value.code == "section.end.missing"


def test_css_color_values_work_across_high_level_apis() -> None:
    assert parse_css_rgb("#f80") == (255, 136, 0)
    assert parse_css_rgba("#ff880080") == (255, 136, 0, 128)
    assert parse_css_rgb("rgb(255 128 0)") == (255, 128, 0)
    assert parse_css_rgb("rgba(100%, 50%, 0%, 0.5)") == (255, 128, 0)
    assert parse_css_rgb("hsl(30 100% 50%)") == (255, 128, 0)
    assert parse_css_argb("rgba(255 0 0 / 50%)") == 0x80FF0000
    assert parse_css_rgb_unit("#808000") == pytest.approx((128 / 255.0, 128 / 255.0, 0.0))

    assert CutScreenFadePayload(1.0, color="rgba(0 0 0 / 50%)").to_fields()["color"] == 0x80000000
    assert CutDecalPayload(position=(0, 0, 0), colour="#ff8800").to_fields()["Colour"] == 0xFFFF8800
    assert YdrLight.point(color="orange").color == (255, 165, 0)
    assert GrassInstance(color="lime").color == (0, 255, 0)

    lod = LodLight()
    lod.colour = "hsl(240 100% 50%)"
    assert lod.colour == (0, 0, 255)

    light_attr = LightAttrDef(colour="#010203", vol_outer_colour="rgb(4 5 6)")
    assert light_attr.colour == (1, 2, 3)
    assert light_attr.vol_outer_colour == (4, 5, 6)

    library = parse_bound_material_names("DEFAULT | hotpink\nROCK | #123\n")
    assert library.get_color(0) == (255, 105, 180)
    assert library.get_color(1) == (17, 34, 51)

    mesh = YdrMeshInput(material="mat", positions=[(0.0, 0.0, 0.0)], indices=[0])
    paint_mesh(mesh, "rgba(255 128 0 / 25%)")
    assert mesh.colours0[0] == pytest.approx((1.0, 128 / 255.0, 0.0, 64 / 255.0))
