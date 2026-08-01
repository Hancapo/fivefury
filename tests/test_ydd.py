from __future__ import annotations

import struct
from pathlib import Path

import pytest

from fivefury import (
    GameFileCache,
    GameFileType,
    GameTarget,
    Ydd,
    YdrGen9Shader,
    YdrMaterialInput,
    YdrMeshInput,
    YdrShader,
    create_ydr,
    read_ydd,
)
from fivefury.resource import split_rsc7_sections, virtual_to_offset
from fivefury.ydd import YDD_VERSION_GEN9

_REFERENCE_DIR = Path(__file__).resolve().parents[1] / "references"


def _reference_ydd_paths() -> list[Path]:
    return sorted(_REFERENCE_DIR.rglob("*.ydd"))


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
        assert sum(entry.drawable.model_count for entry in ydd.drawables) > 0, path.name
        assert sum(len(entry.drawable.materials) for entry in ydd.drawables) > 0, path.name


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
    assert [entry.name_hash for entry in rebuilt.drawables] == [entry.name_hash for entry in source.drawables]
    assert sum(entry.drawable.model_count for entry in rebuilt.drawables) == sum(entry.drawable.model_count for entry in source.drawables)
    assert sum(len(entry.drawable.materials) for entry in rebuilt.drawables) == sum(len(entry.drawable.materials) for entry in source.drawables)


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
    header, system_data, _graphics_data = split_rsc7_sections(out_path.read_bytes())
    drawable_array = virtual_to_offset(struct.unpack_from("<Q", system_data, 0x30)[0])
    drawable_root = virtual_to_offset(struct.unpack_from("<Q", system_data, drawable_array)[0])

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
