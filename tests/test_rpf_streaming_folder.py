import os
from pathlib import Path

import pytest

from fivefury import GameFileCache, RpfArchive
from fivefury.rpf.entries import RpfBinaryFileEntry, RpfResourceFileEntry
from fivefury.rpf.utils import _build_rsc7


def test_from_folder_keeps_payloads_path_backed_until_save(tmp_path: Path) -> None:
    source = tmp_path / "stream"
    asset = source / "region" / "asset.bin"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"path-backed payload")

    archive = RpfArchive.from_folder(source, name="resource")
    entry = archive.find_entry("region/asset.bin")

    assert entry is not None
    assert entry._source_path == asset.resolve()
    assert getattr(entry, "_data", None) is None
    assert entry.read() == b"path-backed payload"

    destination = tmp_path / "resource.rpf"
    archive.save(destination)
    with RpfArchive.from_path(destination) as written:
        stored = written.find_entry("region/asset.bin")
        assert stored is not None
        assert written.read_entry_standalone(stored) == b"path-backed payload"


def test_from_folder_resolves_sources_before_working_directory_changes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    asset = source / "asset.bin"
    asset.write_bytes(b"stable source")
    destination_dir = tmp_path / "destination"
    destination_dir.mkdir()

    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        archive = RpfArchive.from_folder("source")
        os.chdir(destination_dir)
        destination = destination_dir / "archive.rpf"
        archive.save(destination)
    finally:
        os.chdir(previous)

    with RpfArchive.from_path(destination) as written:
        stored = written.find_entry("asset.bin")
        assert stored is not None
        assert written.read_entry_standalone(stored) == b"stable source"


def test_from_folder_ignores_dot_directories(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / ".git" / "objects").mkdir(parents=True)
    (source / "visible" / ".cache").mkdir(parents=True)
    (source / "visible").mkdir(exist_ok=True)
    (source / ".git" / "objects" / "secret.bin").write_bytes(b"git")
    (source / "visible" / ".cache" / "secret.bin").write_bytes(b"cache")
    (source / "visible" / "asset.bin").write_bytes(b"asset")

    archive = RpfArchive.from_folder(source)

    assert archive.find_entry("visible/asset.bin") is not None
    assert archive.find_entry(".git") is None
    assert archive.find_entry("visible/.cache") is None


def test_from_folder_roundtrips_resource_and_raw_ymap_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    resource = _build_rsc7(b"resource payload")
    (source / "asset.ydr").write_bytes(resource)
    (source / "map.ymap").write_bytes(b"meta payload")

    archive = RpfArchive.from_folder(source)
    resource_entry = archive.find_entry("asset.ydr")
    ymap_entry = archive.find_entry("map.ymap")

    assert isinstance(resource_entry, RpfResourceFileEntry)
    assert resource_entry._source_path == (source / "asset.ydr").resolve()
    assert resource_entry.read() == b"resource payload"
    assert archive.read_entry_standalone(resource_entry) == resource
    assert isinstance(ymap_entry, RpfResourceFileEntry)

    destination = tmp_path / "archive.rpf"
    archive.save(destination)
    with RpfArchive.from_path(destination) as written:
        stored_resource = written.find_entry("asset.ydr")
        stored_ymap = written.find_entry("map.ymap")
        assert stored_resource is not None
        assert stored_ymap is not None
        assert written.read_entry_standalone(stored_resource) == resource
        assert stored_ymap.read() == b"meta payload"


def test_rpf_writer_rejects_offsets_that_would_be_truncated() -> None:
    archive = RpfArchive.empty("resource")

    with pytest.raises(ValueError, match="resource entry block offset exceeds 23 bits"):
        archive._encode_resource_entry(
            RpfResourceFileEntry(name="asset.ydr"),
            b"",
            0x800000,
        )
    with pytest.raises(ValueError, match="binary entry block offset exceeds 24 bits"):
        archive._encode_binary_entry(
            RpfBinaryFileEntry(name="asset.bin"),
            b"",
            0x1000000,
        )


def test_rpf_writer_rejects_name_offsets_that_would_be_truncated() -> None:
    archive = RpfArchive.empty("resource")
    entry = RpfResourceFileEntry(name="asset.ydr", name_offset=0x10000)

    with pytest.raises(ValueError, match="name offset exceeds 16 bits"):
        archive._encode_resource_entry(entry, b"", 0)


def _write_test_archive(path: Path, payload: bytes) -> None:
    source = path.parent / f"{path.stem}_source"
    source.mkdir()
    (source / "asset.bin").write_bytes(payload)
    RpfArchive.from_folder(source, name=path.name).save(path)


def test_game_file_cache_clear_closes_registered_archive_handles(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "registered.rpf"
    _write_test_archive(archive_path, b"registered")
    archive = RpfArchive.from_path(archive_path)
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.register_archive(archive, source_prefix=archive_path.name)

    entry = archive.find_entry("asset.bin")
    assert entry is not None
    assert entry.read() == b"registered"
    assert archive._source_handle is not None

    cache.clear()

    assert archive._source_handle is None
    archive_path.unlink()


def test_game_file_cache_context_closes_lru_archive_handles(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.rpf"
    second_path = tmp_path / "second.rpf"
    _write_test_archive(first_path, b"first")
    _write_test_archive(second_path, b"second")

    with GameFileCache(
        tmp_path,
        max_open_archives=1,
        use_index_cache=False,
    ) as cache:
        cache.scan(use_index_cache=False)
        first_entry = cache.get_entry("first.rpf/asset.bin")
        assert first_entry is not None
        assert first_entry.read() == b"first"
        first_archive = first_entry._archive
        assert first_archive is not None
        assert first_archive._source_handle is not None

        second_entry = cache.get_entry("second.rpf/asset.bin")
        assert second_entry is not None
        assert second_entry.read() == b"second"
        second_archive = second_entry._archive
        assert second_archive is not None

        assert first_archive._source_handle is None
        assert second_archive._source_handle is not None

    assert second_archive._source_handle is None
    first_path.unlink()
    second_path.unlink()
