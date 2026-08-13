from __future__ import annotations

from fivefury import (
    Archetype,
    GameFileCache,
    Gtxd,
    Texture,
    TextureFormat,
    TextureUsage,
    Ytd,
    Ytyp,
    read_ytd_catalog,
)
from fivefury._native import NativeTextureIndex


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


def test_contextual_resolver_prefers_declared_dictionary_before_gtxd_parent(
    tmp_path,
) -> None:
    stream = tmp_path / "stream"
    stream.mkdir()
    (stream / "prop.ydr").write_bytes(b"RSC7fake")
    (stream / "child.ytd").write_bytes(
        Ytd([_texture("shared"), _texture("child_only")]).to_bytes()
    )
    (stream / "parent.ytd").write_bytes(
        Ytd([_texture("shared"), _texture("inherited")]).to_bytes()
    )
    metadata = tmp_path / "common" / "data" / "gtxd.meta"
    metadata.parent.mkdir(parents=True)
    Gtxd.from_mapping({"child": "parent"}).save(metadata)
    ytyp = Ytyp(name="types")
    ytyp.add_archetype(
        Archetype(
            name="prop",
            asset_name="prop",
            texture_dictionary="child",
            asset_type=2,
        )
    )
    ytyp.save(stream / "types.ytyp")

    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)

    shared = cache.resolve_texture("shared", asset="prop.ydr")
    inherited = cache.resolve_texture("inherited", asset="prop.ydr")
    assert shared.found
    assert shared.selected is not None
    assert shared.selected.container_name == "child"
    assert shared.selected.origin == "ytd"
    assert inherited.selected is not None
    assert inherited.selected.container_name == "parent"
    assert inherited.selected.origin == "gtxd_parent"
    assert inherited.selected.parent_depth == 1


def test_contextual_resolver_controls_same_name_and_global_fallbacks(tmp_path) -> None:
    stream = tmp_path / "stream"
    stream.mkdir()
    (stream / "solo.ydr").write_bytes(b"RSC7fake")
    (stream / "solo.ytd").write_bytes(Ytd([_texture("local")]).to_bytes())
    (stream / "unrelated.ytd").write_bytes(Ytd([_texture("global_only")]).to_bytes())

    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)

    local = cache.resolve_texture("local", asset="solo.ydr", materialize=False)
    blocked = cache.resolve_texture("global_only", asset="solo.ydr")
    global_result = cache.resolve_texture(
        "global_only",
        asset="solo.ydr",
        allow_global=True,
    )
    assert local.selected is not None
    assert local.selected.origin == "same_name_fallback"
    assert local.texture is None
    assert not blocked.found
    assert global_result.selected is not None
    assert global_result.selected.origin == "global"
    assert global_result.texture is not None
    assert any(issue.code == "global_fallback" for issue in global_result.issues)


def test_contextual_resolver_reports_invalid_context(tmp_path) -> None:
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)

    result = cache.resolve_texture("missing", asset="missing.ydr")

    assert result.status.value == "invalid_context"
    assert [issue.code for issue in result.issues] == ["context_not_found"]


def test_native_texture_index_preserves_duplicates_and_dictionary_ids() -> None:
    index = NativeTextureIndex()

    assert index.add_many([0x10, 0x10, 0x20], 7) == 0
    assert index.add(0x10, 8) == 3
    assert index.find_texture(0x10) == [0, 1, 3]
    assert index.find_dictionary(7) == [0, 1, 2]
    assert index.find_dictionary(8) == [3]

    index.clear()
    assert len(index) == 0
    assert index.find_texture(0x10) == []
