import os

import pytest

from fivefury import GameFileCache, GameFileType, GameTarget, read_awc


@pytest.mark.integration
@pytest.mark.parametrize(
    "game,variable",
    [
        (GameTarget.GTA5, "FIVEFURY_GTA5_LEGACY_PATH"),
        (GameTarget.GTA5_ENHANCED, "FIVEFURY_GTA5_ENHANCED_PATH"),
    ],
)
def test_retail_playback_contracts_in_both_editions(game, variable):
    with GameFileCache(os.environ[variable], game=game) as cache:
        cache.scan_game(gen9=game is GameTarget.GTA5_ENHANCED)
        for name in (
            "pro_mcs_3_pt1_mastered_only.awc",
            "pro_mcs_5_seq_mastered_only.awc",
            "fix_pro_mcs1_mastered.awc",
        ):
            asset = cache.get_asset(name, kind=GameFileType.AWC)
            assert asset is not None
            awc = cache.load_asset(asset).parsed
            awc.validate().raise_for_errors()
            rebuilt = read_awc(awc.to_bytes())
            rebuilt.validate().raise_for_errors()
            owner = next(
                s for s in rebuilt.streams if s.stream_format_chunk is not None
            )
            channels = owner.stream_format_chunk.channels
            assert len(rebuilt.pcm_bytes()) == channels[0].samples * len(channels) * 2
