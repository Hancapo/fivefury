from pathlib import Path

import pytest

from fivefury import (
    AssetRef,
    AssetSet,
    GameFile,
    GameFileType,
    Gxt2,
    build_gxt2_bytes,
)


def test_asset_set_loads_a_loose_file_with_a_logical_path(tmp_path: Path) -> None:
    source = tmp_path / "labels.gxt2"
    source.write_bytes(build_gxt2_bytes(Gxt2({0x12345678: "Hello"})))
    assets = AssetSet()

    loaded = assets.file(source, path="data/lang/labels.gxt2")

    assert isinstance(loaded, GameFile)
    assert loaded.kind is GameFileType.GXT2
    assert loaded.path == "data/lang/labels.gxt2"
    assert isinstance(loaded.parsed, Gxt2)
    assert loaded.parsed.get(0x12345678) == "Hello"
    assert assets.require("labels", Gxt2) is loaded.parsed


def test_asset_set_loads_a_loose_directory_recursively(tmp_path: Path) -> None:
    nested = tmp_path / "stream" / "lang"
    nested.mkdir(parents=True)
    (nested / "first.gxt2").write_bytes(build_gxt2_bytes(Gxt2({1: "First"})))
    (tmp_path / "stream" / "payload.bin").write_bytes(b"payload")

    assets = AssetSet.from_directory(tmp_path / "stream")

    assert set(assets) == {"lang/first.gxt2", "payload.bin"}
    assert assets.require("first", Gxt2).get(1) == "First"
    payload = assets["payload.bin"]
    assert isinstance(payload, GameFile)
    assert payload.kind is GameFileType.UNKNOWN
    assert payload.parsed == b"payload"


def test_asset_set_rejects_duplicate_logical_loose_paths(tmp_path: Path) -> None:
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    assets = AssetSet()
    assets.file(first, path="same.bin")

    with pytest.raises(KeyError, match="already registered"):
        assets.file(second, path="same.bin")


def test_asset_ref_path_unwraps_a_loose_game_file(tmp_path: Path) -> None:
    source = tmp_path / "labels.gxt2"
    source.write_bytes(build_gxt2_bytes(Gxt2({7: "Seven"})))
    assets = AssetSet()
    assets.file(source, path="lang/labels.gxt2")

    resolved = AssetRef(
        "labels",
        asset_type=Gxt2,
        path="lang/labels.gxt2",
    ).resolve(assets)

    assert isinstance(resolved, Gxt2)
    assert resolved.get(7) == "Seven"
