from __future__ import annotations

from xml.etree.ElementTree import ParseError

import pytest

from fivefury import (
    AssetRegistration,
    DlcDataFileType,
    GameFile,
    GameFileCache,
    GameFileType,
    MetaHash,
    YmtPedMetadata,
    read_ped_metadata,
)
from fivefury.cut.resolution.expressions import _ped_init_data_by_model


def metadata_xml(model="actor", dictionary="face"):
    return (
        "<CPedModelInfo__InitDataList><InitDatas><Item>"
        f"<Name>{model}</Name><ExpressionDictionaryName>{dictionary}</ExpressionDictionaryName>"
        "<ExpressionName>face</ExpressionName></Item></InitDatas></CPedModelInfo__InitDataList>"
    ).encode()


def test_registered_ped_metadata_preserves_path_and_exact_model(tmp_path):
    path = tmp_path / "named.meta"
    path.write_bytes(metadata_xml())
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(load_keys=False)
    assert cache.find_path("named.meta").kind is GameFileType.UNKNOWN
    cache.register_metadata(
        AssetRegistration("named.meta", DlcDataFileType.PED_METADATA)
    )
    asset = cache.find_path("named.meta")
    assert asset.kind is GameFileType.PEDS
    loaded = cache.load_asset(asset)
    assert loaded.path == "named.meta"
    assert isinstance(loaded.parsed, YmtPedMetadata)
    matches = _ped_init_data_by_model(cache, [], None, {int(MetaHash("actor"))})
    assert matches[int(MetaHash("actor"))][1][0][
        2
    ].expression_dictionary_name == MetaHash("face")
    assert int(MetaHash("named")) not in matches


def test_named_peds_meta_decodes_without_explicit_registration():
    file = GameFile.from_bytes(metadata_xml(), path="peds.meta")
    assert file.loaded
    assert isinstance(file.parsed, YmtPedMetadata)


@pytest.mark.parametrize("payload", [b"<broken", b"<Other/>", metadata_xml(model="")])
def test_malformed_metadata_has_diagnostics(payload):
    with pytest.raises((ValueError, ParseError)):
        read_ped_metadata(payload)
    file = GameFile.from_bytes(payload, path="named.meta", kind=GameFileType.PEDS)
    assert not file.loaded
    assert file.kind is GameFileType.PEDS
    assert not file.diagnostics.valid


def test_missing_registration_fails_without_mutating_index(tmp_path):
    cache = GameFileCache(tmp_path, use_index_cache=False)
    with pytest.raises(FileNotFoundError):
        cache.register_metadata(
            AssetRegistration("missing.meta", DlcDataFileType.PED_METADATA)
        )
    assert cache.asset_count == 0


def test_registered_metadata_invalidates_primed_index(tmp_path):
    (tmp_path / "peds.meta").write_bytes(metadata_xml("old"))
    (tmp_path / "new.meta").write_bytes(metadata_xml("new"))
    cache = GameFileCache(tmp_path, index_cache_path=tmp_path / "index")
    cache.scan(load_keys=False)
    old_hash, new_hash = (int(MetaHash(name)) for name in ("old", "new"))
    _ped_init_data_by_model(cache, [], None, {old_hash})
    assert new_hash not in cache._ped_init_asset_index
    cache.register_metadata(AssetRegistration("new.meta", DlcDataFileType.PED_METADATA))
    assert cache._ped_init_asset_index is None
    matches = _ped_init_data_by_model(cache, [], None, {new_hash})
    assert new_hash in matches
