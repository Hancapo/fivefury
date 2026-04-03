from __future__ import annotations

from math import isclose
from pathlib import Path

import pytest

from fivefury import CutFile, CutHashedString, GameFileType, analyze_cut, read_cut, read_cutxml
from fivefury.gamefile import guess_game_file_type


TESTS_DIR = Path(__file__).resolve().parent
CUT_PATH = TESTS_DIR / "mp_int_mcs_18_a1.cut"
CUTXML_PATH = TESTS_DIR / "mp_int_mcs_18_a1.cutxml"


pytestmark = pytest.mark.skipif(not CUT_PATH.is_file() or not CUTXML_PATH.is_file(), reason="cut samples not available")


def _counts(cut: CutFile) -> dict[str, int]:
    root = cut.root.fields
    return {
        "objects": len(root["pCutsceneObjects"]),
        "load_events": len(root["pCutsceneLoadEventList"]),
        "events": len(root["pCutsceneEventList"]),
        "event_args": len(root["pCutsceneEventArgsList"]),
        "concat": len(root["concatDataList"]),
        "discard": len(root["discardFrameList"]),
    }


def test_read_cutxml_smoke() -> None:
    cutxml = read_cutxml(CUTXML_PATH)

    assert cutxml.root.type_name == "rage__cutfCutsceneFile2"
    assert _counts(cutxml) == {
        "objects": 11,
        "load_events": 6,
        "events": 32,
        "event_args": 26,
        "concat": 1,
        "discard": 1,
    }


def test_read_cut_matches_cutxml_shape() -> None:
    cut = read_cut(CUT_PATH)
    cutxml = read_cutxml(CUTXML_PATH)

    assert cut.root.type_name == cutxml.root.type_name
    assert isclose(cut.root.fields["fTotalDuration"], 64.36666870117188, rel_tol=0.0, abs_tol=1e-6)
    assert cut.root.fields["cFaceDir"] == r"x:/gta5/assets_ng\cuts\MP_INT_MCS_18_A1\faces"
    assert _counts(cut) == _counts(cutxml)
    assert cut.root.fields["pCutsceneObjects"][0].type_name == cutxml.root.fields["pCutsceneObjects"][0].type_name
    assert cut.root.fields["concatDataList"][0].fields["cSceneName"] == CutHashedString(hash=972297886)


def test_cut_game_file_type_mapping() -> None:
    assert guess_game_file_type("foo.cut") is GameFileType.CUT
    assert guess_game_file_type("foo.cutxml") is GameFileType.CUT


def test_cut_summary_and_resolution() -> None:
    cut = read_cut(CUT_PATH)
    summary = analyze_cut(cut)
    first_event = next(cut.iter_resolved_events(include_load_events=False))

    assert summary.root_type == "rage__cutfCutsceneFile2"
    assert summary.object_types["rage__cutfLightObject"] == 4
    assert summary.event_arg_types["rage__cutfSubtitleEventArgs"] == 16
    assert first_event.event.type_name == "rage__cutfObjectIdEvent"
    assert first_event.object is not None
    assert first_event.object.type_name == "rage__cutfAnimationManagerObject"
    assert first_event.event_args is not None
    assert first_event.event_args.type_name == "rage__cutfObjectIdEventArgs"
