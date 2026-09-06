import hashlib
import os
import tracemalloc
from pathlib import Path

import pytest

from fivefury import (
    DlcPack,
    GameFileCache,
    RpfArchive,
    RpfFileSource,
    read_dlc_pack,
)
from fivefury.resource import ResourceHeader, get_resource_flags_from_size
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
    assert entry._source is not None
    assert entry._source.path == asset.resolve()
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
    assert resource_entry._source is not None
    assert resource_entry._source.path == (source / "asset.ydr").resolve()
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


def test_rpf_writer_does_not_inflate_existing_rsc7(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "asset.ydr"
    payload = _build_rsc7(b"resource payload")
    source.write_bytes(payload)
    archive = RpfArchive.empty("resource.rpf")
    archive.file_path("asset.ydr", RpfFileSource.resource(source))

    def reject_decompression(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("RPF insertion must not inflate RSC7 payloads")

    monkeypatch.setattr(
        "fivefury.resource.decompress_resource_stream", reject_decompression
    )
    destination = tmp_path / "resource.rpf"
    archive.save(destination)

    with RpfArchive.from_path(destination) as written:
        entry = written.find_entry("asset.ydr")
        assert entry is not None
        assert written.read_entry_standalone(entry) == payload


def test_file_backed_large_resource_roundtrips_sentinel_header(
    tmp_path: Path,
) -> None:
    source = tmp_path / "large.ydr"
    header = ResourceHeader(
        version=165,
        system_flags=get_resource_flags_from_size(512, 0xA),
        graphics_flags=get_resource_flags_from_size(512, 0x5),
    ).pack()
    with source.open("wb") as stream:
        stream.write(header)
        stream.seek(0x1000000)
        stream.write(b"\0")
    expected_hash = hashlib.sha256(source.read_bytes()).digest()

    archive = RpfArchive.empty("large.rpf")
    archive.file_path("large.ydr", RpfFileSource.resource(source))
    destination = tmp_path / "large.rpf"
    archive.save(destination)

    with RpfArchive.from_path(destination) as written:
        entry = written.find_entry("large.ydr")
        assert entry is not None
        assert entry.file_size == source.stat().st_size
        actual_hash = hashlib.sha256(written.read_entry_standalone(entry)).digest()
    assert actual_hash == expected_hash


def test_dlc_streams_existing_nested_rpf_without_reserializing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"x" * (8 * 1024 * 1024))
    inner = RpfArchive.empty("maps.rpf")
    inner.file_path("payload.bin", RpfFileSource.raw(payload))
    inner_path = tmp_path / "maps.rpf"
    inner.save(inner_path)
    expected_hash = hashlib.sha256(inner_path.read_bytes()).digest()

    pack = DlcPack("streamed_maps")
    pack.rpf(
        "x64/levels/gta5/maps.rpf",
        RpfFileSource.archive(inner_path),
        map_data=True,
    )

    def reject_parse(*args: object, **kwargs: object) -> RpfArchive:
        raise AssertionError("file-backed nested RPFs must not be parsed while writing")

    def reject_serialize(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("file-backed nested RPFs must not be reserialized")

    monkeypatch.setattr(RpfArchive, "from_path", reject_parse)
    monkeypatch.setattr(RpfArchive, "to_bytes", reject_serialize)
    destination = tmp_path / "dlc.rpf"
    tracemalloc.start()
    pack.save_dlc_rpf(destination)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert peak < 4 * 1024 * 1024
    with RpfArchive.from_bytes(destination.read_bytes(), name="dlc.rpf") as written:
        entry = written.find_entry("x64/levels/gta5/maps.rpf")
        assert entry is not None
        actual_hash = hashlib.sha256(written.read_entry_standalone(entry)).digest()
    assert actual_hash == expected_hash
    assert read_dlc_pack(destination.read_bytes(), load_files=False).files == {}


def test_file_backed_binary_compression_streams_and_roundtrips(
    tmp_path: Path,
) -> None:
    source = tmp_path / "large.meta"
    source.write_bytes(b"streamed metadata\n" * (1024 * 1024))
    archive = RpfArchive.empty("compressed.rpf")
    archive.file_path(
        "data/large.meta",
        RpfFileSource.compressed(source),
    )

    destination = tmp_path / "compressed.rpf"
    tracemalloc.start()
    archive.save(destination)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert peak < 4 * 1024 * 1024
    with RpfArchive.from_path(destination) as written:
        entry = written.find_entry("data/large.meta")
        assert isinstance(entry, RpfBinaryFileEntry)
        assert entry.file_size > 0
        assert entry.file_uncompressed_size == source.stat().st_size
        assert written.read_entry_standalone(entry) == source.read_bytes()


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


def test_rpf_directory_child_indexes_follow_add_replace_and_roundtrip() -> None:
    archive = RpfArchive.empty("indexed.rpf")
    for index in range(2_000):
        archive.file(f"stream/asset_{index:04d}.bin", bytes([index & 0xFF]))

    stream = archive.root.find_directory("STREAM")
    assert stream is not None
    assert len(stream.files) == 2_000
    assert stream.find_file("ASSET_1999.BIN") is stream.files[-1]

    replacement = archive.file("stream/asset_1000.bin", b"replacement")
    assert len(stream.files) == 2_000
    assert stream.find_file("asset_1000.bin") is replacement

    loaded = RpfArchive.from_bytes(archive.to_bytes(), name="indexed.rpf")
    loaded_stream = loaded.root.find_directory("stream")
    assert loaded_stream is not None
    assert len(loaded_stream.files) == 2_000
    assert loaded_stream.find_file("asset_1000.bin") is not None
