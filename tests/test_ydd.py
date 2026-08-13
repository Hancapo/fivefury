from __future__ import annotations

import struct
from pathlib import Path

import pytest

from fivefury import (
    LEGACY_YDD_CUTSCENE_PED_RUNTIME_PROFILE,
    LEGACY_YDD_FULL_PED_RUNTIME_PROFILE,
    GameFileCache,
    GameFileType,
    GameTarget,
    Ydd,
    YddRuntimeContext,
    YdrGen9Shader,
    YdrMaterialInput,
    YdrMeshInput,
    YdrShader,
    YdrSkeleton,
    create_ydr,
    read_ydd,
)
from fivefury.resource import build_rsc7, split_rsc7_sections, virtual_to_offset
from fivefury.ydd import GEN9_YDD_RUNTIME_PROFILE, YDD_VERSION_GEN9
from tests.helpers import reference_root


def _reference_ydd_paths() -> list[Path]:
    return sorted(reference_root().rglob("*.ydd"))


def test_read_real_reference_ydd_drawable_dictionary() -> None:
    paths = _reference_ydd_paths()
    if not paths:
        pytest.skip("real YDD reference directory not available")

    ydd = read_ydd(paths[0])

    assert isinstance(ydd, Ydd)
    assert ydd.version == 165
    assert ydd.drawable_count > 0
    assert len(ydd.names) == ydd.drawable_count
    assert ydd.drawables[0].name_hash != 0
    assert ydd.drawables[0].drawable.model_count > 0
    assert ydd.drawables[0].drawable.materials


def test_read_real_reference_ydd_directory() -> None:
    paths = _reference_ydd_paths()
    if not paths:
        pytest.skip("real YDD reference directory not available")

    for path in paths:
        ydd = read_ydd(path)
        assert ydd.drawable_count > 0, path.name
        assert sum(
            entry.drawable.model_count for entry in ydd.drawables
        ) > 0, path.name
        assert sum(
            len(entry.drawable.materials) for entry in ydd.drawables
        ) > 0, path.name


def test_gamefilecache_parses_loose_ydd(tmp_path: Path) -> None:
    paths = _reference_ydd_paths()
    if not paths:
        pytest.skip("real YDD reference directory not available")

    stream_dir = tmp_path / "stream"
    stream_dir.mkdir()
    target = stream_dir / paths[0].name
    target.write_bytes(paths[0].read_bytes())

    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)

    game_file = cache.get_file(f"stream/{paths[0].name}")
    assert game_file is not None
    assert game_file.kind == GameFileType.YDD
    assert isinstance(game_file.parsed, Ydd)
    assert game_file.parsed.drawable_count > 0


def test_build_and_read_ydd_from_created_drawable(tmp_path: Path) -> None:
    mesh = YdrMeshInput(
        positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        indices=[0, 1, 2],
        texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
    )
    drawable = create_ydr(
        meshes=[mesh],
        material_textures={"DiffuseSampler": "test_diffuse"},
        name="test_drawable",
    )
    ydd = Ydd.from_drawables({"test_drawable": drawable}, version=165)

    out_path = tmp_path / "test.ydd"
    ydd.save(out_path)
    rebuilt = read_ydd(out_path)

    assert rebuilt.drawable_count == 1
    assert rebuilt.get("test_drawable") is not None
    assert rebuilt.drawables[0].drawable.model_count == 1
    assert len(rebuilt.drawables[0].drawable.materials) == 1


def test_roundtrip_real_reference_ydd(tmp_path: Path) -> None:
    paths = _reference_ydd_paths()
    if not paths:
        pytest.skip("real YDD reference directory not available")

    source = read_ydd(paths[0])
    out_path = tmp_path / paths[0].name
    source.save(out_path)
    rebuilt = read_ydd(out_path)

    assert rebuilt.drawable_count == source.drawable_count
    assert [entry.name_hash for entry in rebuilt.drawables] == [
        entry.name_hash for entry in source.drawables
    ]
    assert sum(
        entry.drawable.model_count for entry in rebuilt.drawables
    ) == sum(entry.drawable.model_count for entry in source.drawables)
    assert sum(
        len(entry.drawable.materials) for entry in rebuilt.drawables
    ) == sum(len(entry.drawable.materials) for entry in source.drawables)


def test_build_enhanced_ydd_uses_gen9_runtime_headers(tmp_path: Path) -> None:
    mesh = YdrMeshInput(
        positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        indices=[0, 1, 2],
        material="native_gen9",
        texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
    )
    drawable = create_ydr(
        meshes=[mesh],
        materials=[
            YdrMaterialInput(
                name="native_gen9",
                shader=YdrGen9Shader.SILHOUETTELAYER,
                layout_shader=YdrShader.DEFAULT,
            )
        ],
        name="test_drawable",
    )
    ydd = Ydd.from_drawables(
        {"test_drawable": drawable},
        game=GameTarget.GTA5_ENHANCED,
    )

    out_path = ydd.save(tmp_path / "test_enhanced.ydd")
    header, system_data, _graphics_data = split_rsc7_sections(
        out_path.read_bytes()
    )
    drawable_array = virtual_to_offset(
        struct.unpack_from("<Q", system_data, 0x30)[0]
    )
    drawable_root = virtual_to_offset(
        struct.unpack_from("<Q", system_data, drawable_array)[0]
    )

    assert header.version == YDD_VERSION_GEN9
    assert struct.unpack_from("<I", system_data, 0x00)[0] == 0x4068E798
    assert struct.unpack_from("<I", system_data, drawable_root)[0] == 0x4068C7F0

    rebuilt = read_ydd(out_path)
    assert rebuilt.game is GameTarget.GTA5_ENHANCED
    assert rebuilt.drawable_count == 1
    assert rebuilt.drawables[0].drawable.model_count == 1


def test_ydd_rejects_mismatched_game_and_version() -> None:
    with pytest.raises(ValueError, match="does not match target"):
        Ydd.from_drawables(
            [],
            game=GameTarget.GTA5_ENHANCED,
            version=165,
        )


def _simple_drawable(name: str, *, skeleton=None):
    return create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="body",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[
            YdrMaterialInput(
                name="body",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        skeleton=skeleton,
        name=name,
    )


def _root_vfts(raw: bytes) -> tuple[int, set[int]]:
    _, system_data, _ = split_rsc7_sections(raw)
    dictionary_vft = struct.unpack_from("<I", system_data, 0)[0]
    drawables_pointer = struct.unpack_from("<Q", system_data, 0x30)[0]
    drawables_count = struct.unpack_from("<H", system_data, 0x38)[0]
    pointer_offset = virtual_to_offset(drawables_pointer)
    drawable_vfts = {
        struct.unpack_from(
            "<I",
            system_data,
            virtual_to_offset(
                struct.unpack_from("<Q", system_data, pointer_offset + index * 8)[0]
            ),
        )[0]
        for index in range(drawables_count)
    }
    return dictionary_vft, drawable_vfts


def _texture_reference_vfts(raw: bytes) -> set[int]:
    _, system_data, _ = split_rsc7_sections(raw)
    drawables_pointer = struct.unpack_from("<Q", system_data, 0x30)[0]
    drawable_pointer = struct.unpack_from(
        "<Q", system_data, virtual_to_offset(drawables_pointer)
    )[0]
    drawable_offset = virtual_to_offset(drawable_pointer)
    shader_group_pointer = struct.unpack_from(
        "<Q", system_data, drawable_offset + 0x10
    )[0]
    shader_group_offset = virtual_to_offset(shader_group_pointer)
    shaders_pointer = struct.unpack_from(
        "<Q", system_data, shader_group_offset + 0x10
    )[0]
    shader_pointer = struct.unpack_from(
        "<Q", system_data, virtual_to_offset(shaders_pointer)
    )[0]
    shader_offset = virtual_to_offset(shader_pointer)
    parameters_pointer = struct.unpack_from("<Q", system_data, shader_offset)[0]
    parameter_count = system_data[shader_offset + 0x10]
    parameters_offset = virtual_to_offset(parameters_pointer)
    result: set[int] = set()
    for index in range(parameter_count):
        entry_offset = parameters_offset + index * 16
        if system_data[entry_offset] != 0:
            continue
        texture_pointer = struct.unpack_from(
            "<Q", system_data, entry_offset + 0x08
        )[0]
        if texture_pointer:
            result.add(
                struct.unpack_from(
                    "<I", system_data, virtual_to_offset(texture_pointer)
                )[0]
            )
    return result


def test_cutscene_ped_profile_writes_and_roundtrips_root_classes() -> None:
    profile = LEGACY_YDD_CUTSCENE_PED_RUNTIME_PROFILE
    source = Ydd.from_drawables(
        {"head_000_r": _simple_drawable("head_000_r")},
        name="cutscene_ped",
        runtime_context=YddRuntimeContext.CUTSCENE_PED_COMPONENT,
    )

    raw = source.to_bytes()

    assert _root_vfts(raw) == (
        profile.dictionary_vft,
        {profile.drawable_headers.drawable},
    )
    assert _texture_reference_vfts(raw) == {
        profile.drawable_headers.texture_base
    }
    rebuilt = read_ydd(raw)
    assert rebuilt.runtime_profile is not None
    assert rebuilt.runtime_profile == profile
    assert _root_vfts(rebuilt.to_bytes()) == _root_vfts(raw)
    assert _texture_reference_vfts(rebuilt.to_bytes()) == (
        _texture_reference_vfts(raw)
    )


def test_full_ped_profile_writes_and_roundtrips_runtime_classes() -> None:
    profile = LEGACY_YDD_FULL_PED_RUNTIME_PROFILE
    skeleton = YdrSkeleton()
    skeleton.bone("root", tag=0)
    source = Ydd.from_drawables(
        {
            "head_000_r": _simple_drawable(
                "head_000_r",
                skeleton=skeleton.build(),
            )
        },
        name="full_ped",
        runtime_context=YddRuntimeContext.FULL_PED_DICTIONARY,
    )

    raw = source.to_bytes()

    assert _root_vfts(raw) == (
        profile.dictionary_vft,
        {profile.drawable_headers.drawable},
    )
    assert _texture_reference_vfts(raw) == {
        profile.drawable_headers.texture_base
    }
    rebuilt = read_ydd(raw)
    assert rebuilt.runtime_profile is not None
    assert rebuilt.runtime_profile == profile
    assert _root_vfts(rebuilt.to_bytes()) == _root_vfts(raw)
    assert _texture_reference_vfts(rebuilt.to_bytes()) == (
        _texture_reference_vfts(raw)
    )


def test_enhanced_ped_context_uses_gen9_runtime_profile() -> None:
    source = Ydd.from_drawables(
        {"head_000_r": _simple_drawable("head_000_r")},
        game=GameTarget.GTA5_ENHANCED,
        runtime_context=YddRuntimeContext.FULL_PED_DICTIONARY,
    )

    assert source.runtime_profile == GEN9_YDD_RUNTIME_PROFILE


def _replace_system_section(raw: bytes, system_data: bytes) -> bytes:
    header, _original_system, graphics_data = split_rsc7_sections(raw)
    return build_rsc7(
        system_data,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )


def _drawable_root_offsets(system_data: bytes) -> list[int]:
    drawables_pointer = struct.unpack_from("<Q", system_data, 0x30)[0]
    drawables_count = struct.unpack_from("<H", system_data, 0x38)[0]
    pointer_offset = virtual_to_offset(drawables_pointer)
    return [
        virtual_to_offset(
            struct.unpack_from("<Q", system_data, pointer_offset + index * 8)[0]
        )
        for index in range(drawables_count)
    ]


def test_reader_rejects_mixed_drawable_runtime_headers() -> None:
    raw = Ydd.from_drawables(
        {"first": _simple_drawable("first"), "second": _simple_drawable("second")}
    ).to_bytes()
    _header, system_data, _graphics_data = split_rsc7_sections(raw)
    mixed_system = bytearray(system_data)
    second_root = _drawable_root_offsets(system_data)[1]
    struct.pack_into("<I", mixed_system, second_root, 0x40573158)

    with pytest.raises(ValueError, match="mixed drawable runtime headers"):
        read_ydd(_replace_system_section(raw, mixed_system))


def test_reader_rejects_mixed_nested_runtime_headers() -> None:
    raw = Ydd.from_drawables(
        {"first": _simple_drawable("first"), "second": _simple_drawable("second")}
    ).to_bytes()
    _header, system_data, _graphics_data = split_rsc7_sections(raw)
    mixed_system = bytearray(system_data)
    second_root = _drawable_root_offsets(system_data)[1]
    second_shader_group = virtual_to_offset(
        struct.unpack_from("<Q", system_data, second_root + 0x10)[0]
    )
    struct.pack_into("<I", mixed_system, second_shader_group, 0x406138E0)

    with pytest.raises(ValueError, match="mixed runtime headers: shader_group="):
        read_ydd(_replace_system_section(raw, mixed_system))
