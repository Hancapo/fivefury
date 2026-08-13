from __future__ import annotations

from fivefury import (
    GameFileCache,
    Texture,
    TextureFormat,
    TextureUsage,
    Ytd,
    read_ytd_catalog,
)


def _texture(name: str, *, usage: TextureUsage = TextureUsage.DEFAULT) -> Texture:
    return Texture.from_raw(
        b"\x11" * 8,
        4,
        4,
        TextureFormat.BC1,
        1,
        name=name,
        usage=usage,
        usage_flags=3,
    )


def test_ytd_catalog_reads_legacy_and_enhanced_metadata_without_pixel_payloads() -> None:
    for game in ("gta5", "gta5_enhanced"):
        payload = Ytd([_texture("test_diffuse")], game=game).to_bytes()
        catalog = read_ytd_catalog(payload)

        descriptor = catalog.get("test_diffuse")
        assert catalog.game == game
        assert descriptor.width == 4
        assert descriptor.height == 4
        assert descriptor.format is TextureFormat.BC1
        assert descriptor.data_size == 8
        assert descriptor.usage_flags == 3
        assert not hasattr(descriptor, "data")


def test_gamefilecache_texture_catalog_is_lazy_and_materializes_on_request(tmp_path) -> None:
    stream = tmp_path / "stream"
    stream.mkdir()
    (stream / "first.ytd").write_bytes(Ytd([_texture("shared")]).to_bytes())
    (stream / "second.ytd").write_bytes(Ytd([_texture("unique")]).to_bytes())

    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)
    catalog = cache.texture_catalog

    first = catalog.dictionary("first")
    assert first is not None
    assert first.names() == ("shared",)
    assert next(catalog.iter_entries("first")).dictionary_name == "first"

    matches = catalog.find("unique")
    assert len(matches) == 1
    assert matches[0].dictionary_name == "second"
    loaded = catalog.load(matches[0])
    assert loaded is not None
    assert loaded.data == b"\x11" * 8


def test_texture_catalog_tracks_invalid_dictionaries_without_stopping_build(tmp_path) -> None:
    stream = tmp_path / "stream"
    stream.mkdir()
    (stream / "good.ytd").write_bytes(Ytd([_texture("good_texture")]).to_bytes())
    (stream / "broken.ytd").write_bytes(b"not a resource")

    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)
    catalog = cache.build_texture_catalog()

    assert [entry.name for entry in catalog.find("good_texture")] == ["good_texture"]
    assert "stream/broken.ytd" in catalog.errors
