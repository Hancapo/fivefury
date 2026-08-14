from __future__ import annotations

from types import SimpleNamespace

import pytest

from fivefury import CutScene, MetaHash
from fivefury.cut.audio_references import (
    cut_audio_container_hints,
    cut_audio_references,
)
from fivefury.cut.resolution.audio import _resolve_audio
from fivefury.gamefile import GameFileType


def _asset(asset_id: int, path: str) -> SimpleNamespace:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return SimpleNamespace(
        id=asset_id,
        path=path,
        stem=name.rsplit(".", 1)[0],
        kind=GameFileType.AWC,
    )


def test_audio_container_hint_comes_from_the_target_audio_object() -> None:
    scene = CutScene.create(duration=2.0)
    audio = scene.audio("SUM23_CM1_INT.WA", object_id=3)
    reference = MetaHash("opaque_audio_event").uint
    scene.load_audio(0.0, str(reference), target=audio)

    assert cut_audio_references(scene) == ("SUM23_CM1_INT.WA",)
    assert cut_audio_container_hints(scene, ("SUM23_CM1_INT.WA",)) == {
        "SUM23_CM1_INT.WA": ("sum23_cm1_int",)
    }


def test_audio_resolution_uses_container_hint_and_source_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = MetaHash("opaque_audio_event").uint
    base = _asset(
        1,
        "x64/audio/sfx/base.rpf/sum23_cm1_int_mastered.awc",
    )
    update = _asset(
        2,
        "update/x64/dlcpacks/test/dlc.rpf/x64/audio/sfx/sum23_cm1_int_mastered.awc",
    )
    parsed = SimpleNamespace(wav_bytes=lambda: b"wav")
    loaded = {
        base.id: SimpleNamespace(parsed=parsed),
        update.id: SimpleNamespace(parsed=parsed),
    }

    class Cache:
        @staticmethod
        def iter_assets(kind):
            assert kind is GameFileType.AWC
            return iter((base, update))

    monkeypatch.setattr(
        "fivefury.cut.resolution.audio._load_file",
        lambda _cache, asset, _issues: loaded[asset.id],
    )
    issues = []

    resolved = _resolve_audio(
        Cache(),
        (reference,),
        issues,
        container_hints={reference: ("sum23_cm1_int",)},
    )

    assert not issues
    assert resolved[reference].asset is update
    assert resolved[reference].container_reference == "sum23_cm1_int"
