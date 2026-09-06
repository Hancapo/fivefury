import os
from pathlib import Path

import pytest

from fivefury import read_yed
from fivefury.yed.contract.derive import derive_contract


@pytest.mark.integration("FIVEFURY_TEST_YED_CONTRACT_CORPUS")
def test_retail_contracts_and_bounded_preservation():
    root = Path(os.environ["FIVEFURY_TEST_YED_CONTRACT_CORPUS"])
    exact = 0
    unverifiable = []
    for name in ("a_c_cat_01.yed", "ambient.yed", "player.yed", "ig_natalia.yed"):
        raw = (root / name).read_bytes()
        yed = read_yed(raw)
        assert yed.validate_runtime_contract().valid
        assert yed.to_bytes() == raw
        for expression in yed.expressions:
            derived = derive_contract(expression)
            assert derived.tracks == expression.tracks
            if expression.signature == derived.signature:
                exact += 1
            else:
                unverifiable.append(expression.short_name)
                with pytest.raises(ValueError, match="pre-packing traversal"):
                    expression.recalculate_runtime_contract()
    assert exact == 21
    assert set(unverifiable) == {"wrinkletest", "ballistics", "ig_natalia"}
