import sys

import pytest

from fivefury import _native_abi3 as native
from fivefury.awc.audio import decode_awc_adpcm


@pytest.mark.parametrize("count", [sys.maxsize, sys.maxsize // 2 + 1])
def test_adpcm_checks_python_buffer_limits_before_allocating(count):
    with pytest.raises(OverflowError, match="Python size"):
        decode_awc_adpcm(b'', count)
    assert decode_awc_adpcm(b'', 0) == b''


def test_adpcm_preserves_silence_padding():
    assert decode_awc_adpcm(b'', 4) == bytes(8)


def test_peaks_do_not_iterate_over_missing_samples():
    assert native.awc_build_peak_values(b'', sys.maxsize, sys.maxsize) == [0]
    assert native.awc_build_peak_values(b'\xff\x7f', sys.maxsize, sys.maxsize - 1) == [65534, 0]
