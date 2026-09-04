import pytest

from fivefury import _native_abi3 as native
from tests.helpers import run_python


def test_native_allocation_failure_is_a_python_exception():
    result = run_python(
        """
import sys
from fivefury import _native_abi3 as native
try:
    native.awc_decode_adpcm(b'', sys.maxsize)
except (OverflowError, MemoryError):
    pass
else:
    raise AssertionError('unrepresentable allocation accepted')
assert native.awc_decode_adpcm(b'', 0) == b''
""",
    )
    assert result.returncode == 0, result.stderr


def test_failed_native_buffer_call_does_not_pin_exporter():
    data = bytearray(1)
    with pytest.raises(ValueError):
        native.skin_compose_matrices(data, b"", 1)
    data.extend(b"after failure")


def test_binary_document_owns_and_releases_buffer():
    data = bytearray(b"example")
    document = native.binary_document_new(data)
    with pytest.raises(BufferError):
        data.extend(b"blocked")
    del document
    data.extend(b"allowed")
