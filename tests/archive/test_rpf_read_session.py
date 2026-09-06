import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from fivefury import GameFileCache, RpfArchive
from fivefury._native import RpfReader
from fivefury.crypto import GameCrypto
from fivefury.hashing import _get_lut
from fivefury.rpf import RpfEncryption


@pytest.mark.parametrize("encryption", (RpfEncryption.OPEN, RpfEncryption.AES, RpfEncryption.NG))
def test_read_session_reuses_nested_tables_and_supports_concurrent_reads(tmp_path, encryption):
    crypto = GameCrypto.from_aes_key(bytes(range(32)))
    archive = RpfArchive.empty("test.rpf", encryption=encryption, crypto=crypto)
    _, nested = archive.nested_archive("nested.rpf")
    for i in range(80):
        nested.file(f"file{i}.bin", bytes([i]) * 64)
    path = tmp_path / "test.rpf"
    archive.save(path)
    reader = RpfReader(path, _get_lut(), crypto.native_context())
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(reader.read, (f"nested.rpf/file{i}.bin" for i in range(80))))
    assert results == [bytes([i]) * 64 for i in range(80)]
    assert reader.cached_table_count == 2
    assert reader.read_variants("nested.rpf/file0.bin") == (bytes(64), bytes(64))


def test_read_session_invalidates_tables_after_same_size_replacement(tmp_path):
    path = tmp_path / "archive.rpf"
    original = RpfArchive.empty()
    original.file("old.bin", b"old")
    original.save(path)
    reader = RpfReader(path, _get_lut())
    assert reader.read("old.bin") == b"old"
    previous = path.stat()
    replacement = RpfArchive.empty()
    replacement.file("new.bin", b"new")
    replacement.save(path)
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns + 2_000_000_000))
    assert reader.read("new.bin") == b"new"
    with pytest.raises(RuntimeError, match="entry not found"):
        reader.read("old.bin")


def test_game_cache_bounds_and_clears_native_sessions(tmp_path):
    for i in range(3):
        archive = RpfArchive.empty(f"archive{i}.rpf")
        archive.file("data.bin", bytes([i]))
        archive.save(tmp_path / archive.name)
    with GameFileCache(max_open_archives=1, use_index_cache=False) as cache:
        cache.scan(tmp_path, load_keys=False)
        for i in range(3):
            assert cache.read_bytes(f"archive{i}.rpf/data.bin") == bytes([i])
            assert len(cache._native_readers) == 1
        cache.clear_runtime_cache()
        assert not cache._native_readers
