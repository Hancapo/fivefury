from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import GameFileCache, GameFileType, Ydd, YdrMeshInput, create_ydr, read_ydd


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
