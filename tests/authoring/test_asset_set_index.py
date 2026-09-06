import pytest

from fivefury.authoring import AssetRef, AssetSet
from fivefury.gamefile import GameFile


def test_asset_name_index_tracks_mutations_and_ambiguity():
    assets = AssetSet()
    assets["a/MODEL.ydr"] = "drawable"
    assets["a/model.ybn"] = 42
    assert assets.require("model", str) == "drawable"
    assert assets.require("model", int) == 42
    assets["b/model.ydr"] = "other"
    with pytest.raises(KeyError, match="Ambiguous"):
        assets.require("model", str)
    assert assets.require("model", str, path="b/model.ydr") == "other"
    del assets["a/model.ydr"]
    assert assets.require("model", str) == "other"
    assets.replace("b/model.ydr", 100)
    assert assets.resolve(AssetRef("model", str)) is None
    assets.clear()
    assert assets.resolve(AssetRef("model")) is None


def test_asset_index_observes_current_game_file_parse():
    assets = AssetSet()
    source = GameFile("model.ydr", parsed="first")
    assets[source.path] = source
    assert assets.require("model", str) == "first"
    source.parsed = 9
    assert assets.require("model", int) == 9
    assert assets.resolve(AssetRef("model", str)) is None


def test_name_resolution_does_not_inspect_unrelated_payloads(monkeypatch):
    assets = AssetSet()
    for i in range(1000):
        assets[f"item{i}.ydr"] = i
    examined = []
    original = AssetSet._target

    def inspect(candidate):
        examined.append(candidate)
        return original(candidate)

    monkeypatch.setattr(AssetSet, "_target", staticmethod(inspect))
    assert assets.require("item500", int) == 500
    assert examined == [500]
