from __future__ import annotations

import hashlib
import struct
from unittest.mock import patch

import pytest

from fivefury import (
    Vector2,
    Vector3,
    Ydd,
    YdrMeshInput,
    create_ydr,
    read_ydd,
    read_ydr,
    resource,
)
from fivefury.authoring import ValidationError
from fivefury.texture import total_mip_data_size
from fivefury.ydr import builder as ydr_builder
from fivefury.ydr.write_buffers import GraphicsWriter
from fivefury.yft import build_yft_bytes, create_yft, read_yft
from fivefury.ytd import (
    Texture,
    TextureFormat,
    TextureUsage,
    Ytd,
    read_embedded_texture_dictionary,
)


def _textures(prefix: str = "texture") -> Ytd:
    textures = []
    for index, size in enumerate((4, 16, 256)):
        length = total_mip_data_size(size, size, TextureFormat.BC1, 3)
        # Pointer-shaped pixels must never be treated as relocations.
        data = struct.pack("<QQ", 0x50000020, 0x60000010)
        textures.append(
            Texture.from_raw(
                (data * ((length + len(data) - 1) // len(data)))[:length],
                size,
                size,
                TextureFormat.BC1,
                3,
                name=f"{prefix}_{index}",
                usage=TextureUsage.DIFFUSE,
                usage_flags=index + 1,
            )
        )
    return Ytd(textures)


def _drawable(textures: Ytd | None, *, enhanced: bool):
    return create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[Vector3(), Vector3(1, 0, 0), Vector3(0, 1, 0)],
                indices=[0, 1, 2],
                texcoords=[[Vector2(), Vector2(1, 0), Vector2(0, 1)]],
            )
        ],
        material_textures={
            "DiffuseSampler": textures.textures[0].name
            if textures and textures.textures
            else "external"
        },
        embedded_textures=textures,
        version=159 if enhanced else 165,
        name="texture_sections",
    )


def _fingerprint(raw: bytes) -> str:
    header, system, graphics = resource.split_rsc7_sections(raw)
    return hashlib.sha256(header.pack() + system + graphics).hexdigest()


@pytest.mark.parametrize("enhanced", [False, True])
def test_ytd_sections_roundtrip_and_relocation(enhanced):
    source = _textures()
    game = "gta5_enhanced" if enhanced else "gta5"
    with (
        patch.object(
            resource,
            "compress_resource_stream",
            side_effect=AssertionError("compressed"),
        ),
        patch.object(
            resource,
            "decompress_resource_stream",
            side_effect=AssertionError("decompressed"),
        ),
    ):
        sections = source.prepare_sections(game=game)
    assert len(sections.system_data) == sections.header.system_size
    assert len(sections.graphics_data) == sections.header.graphics_size
    assert resource.split_rsc7_sections(source.to_bytes(game=game)) == (
        sections.header,
        sections.system_data,
        sections.graphics_data,
    )
    assert (
        sorted(Ytd.from_bytes(sections.to_bytes()).textures, key=lambda t: t.name)
        == source.textures
    )

    original_system = sections.system_data
    original_graphics = sections.graphics_data
    for system_prefix, graphics_prefix in ((0x130, 0x90), (0x2710, 0x4020)):
        system = resource.ResourceWriter(initial_size=system_prefix)
        graphics = GraphicsWriter()
        graphics.alloc(bytes(graphics_prefix), 16, relocate_pointers=False)
        offset = ydr_builder._write_embedded_texture_dictionary(
            system, graphics, sections
        )
        rebuilt = read_embedded_texture_dictionary(
            system.finish(),
            graphics.finish(),
            version=sections.header.version,
            offset=offset,
        )
        assert sorted(rebuilt.textures, key=lambda t: t.name) == source.textures
        assert system.finish()[offset + 8 : offset + 16] == bytes(8)
    assert sections.system_data == original_system
    assert sections.graphics_data == original_graphics


@pytest.mark.parametrize("enhanced", [False, True])
@pytest.mark.parametrize("kind", ["ydr", "ydd", "yft"])
@pytest.mark.parametrize("texture_state", ["present", "absent", "empty"])
def test_drawable_prepares_textures_once_per_build(enhanced, kind, texture_state):
    textures = (
        _textures()
        if texture_state == "present"
        else Ytd()
        if texture_state == "empty"
        else None
    )
    drawable = _drawable(textures, enhanced=enhanced)
    if kind == "ydr":
        build = drawable.to_bytes
    elif kind == "ydd":
        dictionary = Ydd.from_drawables(
            {"first": drawable, "second": drawable},
            game="gta5_enhanced" if enhanced else "gta5",
        )
        build = dictionary.to_bytes
    else:
        fragment = create_yft(drawable, version=171 if enhanced else 162)
        build = lambda: build_yft_bytes(fragment)

    preparation_count = (2 if kind == "ydd" else 1) if texture_state == "present" else 0
    with (
        patch.object(
            Ytd, "prepare_sections", autospec=True, side_effect=Ytd.prepare_sections
        ) as prepare,
        patch.object(Ytd, "to_bytes", side_effect=AssertionError("intermediate YTD")),
        patch.object(
            resource,
            "compress_resource_stream",
            wraps=resource.compress_resource_stream,
        ) as compress,
        patch.object(
            resource,
            "decompress_resource_stream",
            wraps=resource.decompress_resource_stream,
        ) as decompress,
        patch.object(
            ydr_builder,
            "_write_embedded_texture_dictionary",
            wraps=ydr_builder._write_embedded_texture_dictionary,
        ) as write,
    ):
        raw = build()
        assert prepare.call_count == preparation_count
        assert compress.call_count == 1
        # YFT validates its final resource; embedding itself never inflates a stream.
        assert decompress.call_count == (1 if kind == "yft" else 0)
        assert write.call_count >= 2 * (2 if kind == "ydd" else 1)
        dictionaries_per_pass = 2 if kind == "ydd" else 1
        for index, call in enumerate(write.call_args_list):
            assert (
                call.args[2]
                is write.call_args_list[index % dictionaries_per_pass].args[2]
            )
        if texture_state == "present":
            textures.textures[0].data = b"\x42" * len(textures.textures[0].data)
        rebuilt_raw = build()
        assert prepare.call_count == 2 * preparation_count
        assert (rebuilt_raw != raw) == (texture_state == "present")

    if kind == "ydr":
        drawables = [read_ydr(rebuilt_raw)]
    elif kind == "ydd":
        drawables = [item.drawable for item in read_ydd(rebuilt_raw).drawables]
    else:
        drawables = [read_yft(rebuilt_raw).main_drawable]
    for result in drawables:
        if texture_state == "present":
            assert (
                sorted(result.embedded_textures.textures, key=lambda t: t.name)
                == textures.textures
            )
            assert result.embedded_textures.game == (
                "gta5_enhanced" if enhanced else "gta5"
            )
        else:
            assert result.embedded_textures is None


@pytest.mark.parametrize("enhanced", [False, True])
def test_yft_prepares_after_merging_shared_shader_textures(enhanced):
    main = _drawable(_textures("main"), enhanced=enhanced)
    extra = _drawable(_textures("extra"), enhanced=enhanced)
    cloth = _drawable(_textures("cloth"), enhanced=enhanced)
    fragment = create_yft(
        main,
        extra_drawables=[extra],
        cloth_drawable=cloth,
        version=171 if enhanced else 162,
    )
    with patch.object(
        Ytd, "prepare_sections", autospec=True, side_effect=Ytd.prepare_sections
    ) as prepare:
        raw = build_yft_bytes(fragment)
    assert prepare.call_count == 2
    rebuilt = read_yft(raw)
    expected = main.embedded_textures.textures + extra.embedded_textures.textures
    assert sorted(
        rebuilt.main_drawable.embedded_textures.textures, key=lambda t: t.name
    ) == sorted(expected, key=lambda t: t.name)
    assert (
        sorted(rebuilt.cloth_drawable.embedded_textures.textures, key=lambda t: t.name)
        == cloth.embedded_textures.textures
    )


@pytest.mark.parametrize("enhanced", [False, True])
def test_preparing_ytd_sections_keeps_validation(enhanced):
    source = _textures()
    source.textures[0].data = b"invalid"
    with pytest.raises(ValidationError):
        source.prepare_sections(game="gta5_enhanced" if enhanced else "gta5")


@pytest.mark.parametrize("enhanced", [False, True])
def test_ytd_sections_match_pre_optimization_bytes(enhanced):
    sections = _textures().prepare_sections(
        game="gta5_enhanced" if enhanced else "gta5"
    )
    # Header + inflated sections from f0bf838, independent of zlib version.
    expected = (
        "4a90134f506f2a2014225dd22dc5e866983f723cdd82022bf9bdd210037c388e"
        if enhanced
        else "ee47192c6f91da63ec485d198c8d9fcedb367518c35070fe3aec098ed16c56f1"
    )
    assert _fingerprint(sections.to_bytes()) == expected


@pytest.mark.parametrize(
    ("kind", "enhanced", "expected"),
    [
        (
            "ydr",
            False,
            "2d08b3ba228fc6fb4a4eef7aa18dd09a4489c5a936613f833129b3fb0e558102",
        ),
        (
            "ydd",
            False,
            "a9599010029ef6944681d935c8289319393ba19d048910c040fbbfe88a3f476b",
        ),
        (
            "yft",
            False,
            "a7b2609ba8070d0609e9848419b79bce35de5ce308699a3f7772da45ff557f53",
        ),
        (
            "ydr",
            True,
            "3d39e39be2771a471e548b57c63f06dacb068d97f75a6ff071284f29497aa6a4",
        ),
        (
            "ydd",
            True,
            "805aef0e4b6ed6ac2312c3fa06c270783da3c27306972edb2648ee5aa3283e75",
        ),
        (
            "yft",
            True,
            "887031517150b3aaedca91790204ebcc6f1e83f05c78bf680af4b3dedbd4b7f7",
        ),
    ],
)
def test_drawable_sections_match_pre_optimization_bytes(kind, enhanced, expected):
    # Fingerprints from f0bf838 include page padding and relocated texture/SRV pointers.
    main = _drawable(_textures("main"), enhanced=enhanced)
    extra = _drawable(_textures("extra"), enhanced=enhanced)
    if kind == "ydr":
        raw = main.to_bytes()
    elif kind == "ydd":
        raw = Ydd.from_drawables(
            {"first": main, "second": extra},
            game="gta5_enhanced" if enhanced else "gta5",
        ).to_bytes()
    else:
        cloth = _drawable(_textures("cloth"), enhanced=enhanced)
        raw = build_yft_bytes(
            create_yft(
                main,
                extra_drawables=[extra],
                cloth_drawable=cloth,
                version=171 if enhanced else 162,
            )
        )
    assert _fingerprint(raw) == expected
