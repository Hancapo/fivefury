from __future__ import annotations

import struct

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
from fivefury.resource import (
    get_resource_chunks,
    get_resource_total_page_count,
    split_rsc7_sections,
)
from fivefury.texture import total_mip_data_size
from fivefury.ytd.catalog import _read_texture_descriptors
from fivefury.ytd.defs import DAT_VIRTUAL_BASE


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


def _bc1_texture(width: int, height: int, mip_count: int) -> Texture:
    size = total_mip_data_size(width, height, TextureFormat.BC1, mip_count)
    return Texture.from_raw(
        bytes((index * 37) & 0xFF for index in range(size)),
        width,
        height,
        TextureFormat.BC1,
        mip_count,
        name="head_diff_000_a_whi",
        usage=TextureUsage.DIFFUSE,
    )


def _enhanced_texture_descriptor(payload: bytes) -> tuple[bytes, int]:
    _, system_data, _ = split_rsc7_sections(payload)
    items_pointer = struct.unpack_from("<Q", system_data, 0x30)[0]
    texture_pointer = struct.unpack_from(
        "<Q",
        system_data,
        items_pointer - DAT_VIRTUAL_BASE,
    )[0]
    return system_data, texture_pointer - DAT_VIRTUAL_BASE


def test_enhanced_multimip_descriptor_matches_retail_runtime_fields() -> None:
    payload = Ytd([_bc1_texture(512, 512, 8)], game="gta5_enhanced").to_bytes()
    system_data, offset = _enhanced_texture_descriptor(payload)

    assert struct.unpack_from("<Q", system_data, offset)[0] == 0x00000001406B7940
    assert struct.unpack_from("<I", system_data, offset + 0x10)[0] == 0x00260208
    assert system_data[offset + 0x1F] == 0x47
    assert system_data[offset + 0x20] == 0xFF
    assert system_data[offset + 0x22] == 8
    assert system_data[offset + 0x23] == 0
    assert struct.unpack_from("<Q", system_data, offset + 0x58)[0] == 0x00000001406B77D8


def test_enhanced_multimip_payload_round_trips_without_reordering() -> None:
    texture = _bc1_texture(512, 512, 8)

    rebuilt = Ytd.from_bytes(Ytd([texture], game="gta5_enhanced").to_bytes()).textures[0]

    assert (rebuilt.width, rebuilt.height, rebuilt.mip_count) == (512, 512, 8)
    assert rebuilt.mip_offsets == texture.mip_offsets
    assert rebuilt.mip_sizes == texture.mip_sizes
    assert rebuilt.data == texture.data


def test_enhanced_single_level_authoring_still_round_trips() -> None:
    texture = _bc1_texture(4, 4, 1)

    rebuilt = Ytd.from_bytes(Ytd([texture], game="gta5_enhanced").to_bytes()).textures[0]

    assert rebuilt.data == texture.data
    assert rebuilt.mip_count == 1


def test_enhanced_large_dictionary_packs_texture_blocks_within_page_limit() -> None:
    width = 256
    height = 256
    mip_count = 7
    texture_data = bytes(
        total_mip_data_size(width, height, TextureFormat.BC1, mip_count)
    )
    textures = [
        Texture.from_raw(
            texture_data,
            width,
            height,
            TextureFormat.BC1,
            mip_count,
            name=f"texture_{index:03d}",
        )
        for index in range(129)
    ]

    payload = Ytd(textures, game="gta5_enhanced").to_bytes()
    header, system_data, _ = split_rsc7_sections(payload)
    assert (
        get_resource_total_page_count(header.system_flags)
        + get_resource_total_page_count(header.graphics_flags)
        <= 128
    )

    graphics_chunks = [
        chunk for chunk in get_resource_chunks(header) if chunk.section == "graphics"
    ]
    descriptors = _read_texture_descriptors(system_data, version=header.version)
    for descriptor in descriptors:
        address = 0x60000000 + descriptor.data_offset
        assert any(
            chunk.contains(address, descriptor.descriptor.data_size)
            for chunk in graphics_chunks
        )

    rebuilt = Ytd.from_bytes(payload)
    assert {texture.name: texture.data for texture in rebuilt.textures} == {
        texture.name: texture.data for texture in textures
    }


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
    ytyp.archetypes.append(
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

    assert index.bind_many([0x10, 0x10, 0x20], 7) == 0
    assert index.bind(0x10, 8) == 3
    assert index.find_texture(0x10) == [0, 1, 3]
    assert index.find_dictionary(7) == [0, 1, 2]
    assert index.find_dictionary(8) == [3]

    index.clear()
    assert len(index) == 0
    assert index.find_texture(0x10) == []
