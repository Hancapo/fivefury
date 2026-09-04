import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from fivefury import GameFileCache, GameTarget, RpfArchive, _native_abi3
from fivefury._native import RpfReader
from fivefury.hashing import _get_lut


def test_native_reader_byte_input_and_tuple_output(tmp_path: Path) -> None:
    path = tmp_path / "native.rpf"
    archive = RpfArchive.empty(path.name)
    payload = b"\x00native\xffpayload\x00"
    archive.file("payload.bin", payload)
    archive.save(path)
    reader = RpfReader(path, _get_lut())
    assert reader.read("payload.bin") == payload
    assert reader.read_variants("payload.bin") == (payload, payload)
    with pytest.raises(ValueError, match="256"):
        RpfReader(path, b"short")
    with pytest.raises(TypeError):
        _native_abi3.rpf_reader_new(str(path), "not bytes", None)


def test_native_metadata_byte_input_reports_format_error() -> None:
    with pytest.raises(ValueError, match="META root block"):
        _native_abi3.meta_extract_ytyp_texture_relationships(bytes(80))


def test_built_extension_on_abi_floor_interpreter(tmp_path: Path) -> None:
    interpreter = os.environ.get("FIVEFURY_ABI_TEST_PYTHON")
    if interpreter is None:
        pytest.skip("Set FIVEFURY_ABI_TEST_PYTHON to the minimum supported Python")
    archive = RpfArchive.empty("abi.rpf")
    archive.file("payload.bin", b"\x00binary\xff")
    path = tmp_path / "abi.rpf"
    archive.save(path)
    script = """
import importlib.util
import sys
assert sys.version_info[:2] == (3, 11)
spec = importlib.util.spec_from_file_location('_native_abi3', sys.argv[1])
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
reader = native.rpf_reader_new(sys.argv[2], bytes(range(256)), None)
assert native.rpf_reader_read(reader, 'payload.bin', 2) == (b'\\x00binary\\xff',) * 2
wav = native.awc_build_pcm_wav(bytes(64), 48000, 1, 16)
assert native.awc_parse_pcm_wav(wav) == (bytes(64), 48000, 1, 16)
assert native.awc_extract_multichannel_blocks(b'', 0, 2048, 1) == [[]]
try:
    native.meta_extract_ytyp_texture_relationships(bytes(80))
except ValueError:
    pass
else:
    raise AssertionError('Invalid META accepted')
"""
    subprocess.run(
        [interpreter, "-I", "-c", script, str(_native_abi3.__file__), str(path)],
        check=True, capture_output=True, text=True, timeout=30,
    )


def test_enhanced_native_reader_integration() -> None:
    root = os.environ.get("FIVEFURY_GTA5_ENHANCED_PATH")
    if root is None:
        pytest.skip("Set FIVEFURY_GTA5_ENHANCED_PATH to run the retail integration test")
    with GameFileCache(root, game=GameTarget.GTA5_ENHANCED, load_audio=False) as cache:
        cache.scan(load_keys=True, gen9=True)
        record = cache.get_asset("prop_streetlight_01.yft")
        assert record is not None
        with patch.object(GameFileCache, "_get_entry_for_asset", side_effect=AssertionError("native read fell back")):
            logical = cache.read_bytes(record, logical=True)
            assert logical
            file = cache.get_file(record)
            assert file is not None
            file.diagnostics.raise_for_errors()
            assert file.loaded
        cache.get_archive(record)
        assert cache.get_archive(record.path.rsplit("/", 1)[0]) is not None
