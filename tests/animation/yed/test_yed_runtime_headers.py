from __future__ import annotations

import pytest

from fivefury import (
    GEN9_YED_RUNTIME_PROFILE,
    LEGACY_YED_RUNTIME_PROFILE,
    GameTarget,
    build_yed_bytes,
    create_yed,
    read_yed,
)


@pytest.mark.parametrize(
    ("game", "profile"),
    [
        (GameTarget.GTA5, LEGACY_YED_RUNTIME_PROFILE),
        (GameTarget.GTA5_ENHANCED, GEN9_YED_RUNTIME_PROFILE),
    ],
)
def test_yed_authoring_uses_target_runtime_headers(game, profile) -> None:
    source = create_yed("body_physics", game=game)

    rebuilt = read_yed(build_yed_bytes(source))

    assert rebuilt.game is game
    assert rebuilt.dictionary.file_vft == profile.dictionary_vft
    assert len(rebuilt.expressions) == 1
    assert rebuilt.expressions[0].vft == profile.expression_vft
    assert rebuilt.expressions[0].short_name == "body_physics"


def test_yed_intact_roundtrip_is_lossless_and_target_override_rebuilds() -> None:
    raw = build_yed_bytes(create_yed("body_physics"))
    source = read_yed(raw)

    assert build_yed_bytes(source) == raw

    enhanced = read_yed(build_yed_bytes(source, game=GameTarget.GTA5_ENHANCED))
    assert enhanced.game is GameTarget.GTA5_ENHANCED
    assert enhanced.dictionary.file_vft == GEN9_YED_RUNTIME_PROFILE.dictionary_vft
    assert {expression.vft for expression in enhanced.expressions} == {
        GEN9_YED_RUNTIME_PROFILE.expression_vft
    }
