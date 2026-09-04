from unittest.mock import patch

import pytest

from fivefury import GameFile, GameFileCache, GameFileType, RpfArchive, ValidationError
from fivefury.cache.io import decode_game_file_payload


def check_failed(file):
    assert file.kind is GameFileType.YDR
    assert not file.loaded
    assert file.parsed is None
    error = file.diagnostics.errors[0]
    assert error.code == "asset.decode.failed"
    assert error.asset == file.path
    assert error.path == "parsed"
    assert "ValueError" in error.message
    with pytest.raises(ValidationError, match="asset.decode.failed"):
        file.ensure_loaded()


def test_game_file_preserves_decode_failure_and_source(tmp_path):
    path = tmp_path / "broken.ydr"
    path.write_bytes(b"invalid")
    file = GameFile.from_path(path)
    check_failed(file)
    assert file.read_bytes(logical=False) == b"invalid"


@pytest.mark.parametrize("native", (True, False))
def test_cache_preserves_decode_diagnostics(tmp_path, native):
    archive = RpfArchive.empty("models.rpf")
    archive.file("broken.ydr", b"invalid")
    archive.save(tmp_path / "models.rpf")
    with GameFileCache(use_index_cache=False) as cache:
        cache.scan(tmp_path, load_keys=False)
        if native:
            file = cache.get_file("models.rpf/broken.ydr")
        else:
            with patch.object(GameFileCache, "_read_archive_asset_native_variants", return_value=None):
                file = cache.get_file("models.rpf/broken.ydr")
        check_failed(file)
        assert cache.get_file(file.path) is file


def test_direct_decode_raises_structured_error_and_keeps_cause():
    with pytest.raises(ValidationError) as raised:
        decode_game_file_payload("broken.ydr", b"invalid")
    assert isinstance(raised.value.__context__, ValueError)


def test_unknown_binary_is_not_reported_as_a_parse_failure():
    file = GameFile.from_bytes(b"opaque", path="data.bin")
    assert file.loaded
    assert file.parsed == b"opaque"
    assert file.diagnostics.valid


def test_decoder_import_failure_is_reported():
    with patch("fivefury.cache.io.importlib.import_module", side_effect=ImportError("missing decoder")):
        file = GameFile.from_bytes(b"unknown", path="map.ymap")
    assert "ImportError: missing decoder" in file.diagnostics.errors[0].message
    assert not file.loaded
