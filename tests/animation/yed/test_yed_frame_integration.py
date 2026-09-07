import os
from pathlib import Path

import pytest

from fivefury import GameTarget, YedFrameLayout, read_yed
from tests.support.yed import assert_scattered_yed


@pytest.mark.integration("FIVEFURY_TEST_YED_FRAME_CORPUS")
def test_large_enhanced_expression_sample_keeps_global_frame_bindings():
    paths = list(Path(os.environ["FIVEFURY_TEST_YED_FRAME_CORPUS"]).glob("*.yed"))
    assert paths
    for path in paths:
        raw = path.read_bytes()
        yed = read_yed(raw)
        assert yed.game == GameTarget.GTA5_ENHANCED
        report = yed.validate()
        if report.valid:
            assert yed.to_bytes() == raw
        else:
            assert {issue.code for issue in report.errors} <= {
                "resource.block.crosses_chunk",
                "yed.resource.pages.count",
            }
            with pytest.raises(ValueError, match="resource.block|yed.resource.pages"):
                yed.to_bytes()
        assert any(
            len(e.tracks) >= 500 and len(e.streams) >= 5 for e in yed.expressions
        )
        rebuilt = yed.recalculate_runtime_contract().to_bytes()
        reread = read_yed(rebuilt)
        assert reread.validate().valid
        assert_scattered_yed(rebuilt, yed)
        for expression in yed.expressions:
            frame = YedFrameLayout.derive(expression.tracks)
            indices = expression.resolve_frame_indices(frame)
            assert expression.validate_frame_binding(frame, indices).valid
            assert all(offset < frame.read_only_offset for offset in indices)
            assert (
                reread.require_expression(expression.name_hash).resolve_frame_indices(
                    frame
                )
                == indices
            )
