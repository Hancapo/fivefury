from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import MetaHash, YcdClipAnimation, read_ycd


TESTS_DIR = Path(__file__).resolve().parent
YCD_PATH = TESTS_DIR / "maude_mcs_1-0.ycd"


pytestmark = pytest.mark.skipif(not YCD_PATH.is_file(), reason="ycd samples not available")


def test_read_ycd_smoke() -> None:
    ycd = read_ycd(YCD_PATH)

    assert ycd.header.version == 46
    assert len(ycd.clips) == 5
    assert len(ycd.animations) == 5
    assert all(isinstance(clip, YcdClipAnimation) for clip in ycd.clips)

    export_camera = next(clip for clip in ycd.clips if clip.short_name == "exportcamera-0")
    assert export_camera.animation is not None
    assert export_camera.animation.frames == 241
    assert export_camera.animation.duration == pytest.approx(8.0)


def test_ycd_build_cutscene_map_strips_suffixes() -> None:
    ycd = read_ycd(YCD_PATH)
    cutscene_map = ycd.build_cutscene_map(0)

    camera = cutscene_map[MetaHash("exportcamera").uint]
    maude = cutscene_map[MetaHash("csb_maude").uint]

    assert camera.short_name == "exportcamera-0"
    assert maude.short_name == "csb_maude_dual-0"
