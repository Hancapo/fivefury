from __future__ import annotations

import math
import struct
import tempfile
from pathlib import Path

from fivefury import BoundSphere, GameFileCache, GameFileType, Ybn, build_rsc7, read_ybn

_RESOURCE_FILE_BASE_SIZE = 0x10


def _build_sphere_bound_block(
    *,
    center: tuple[float, float, float] = (1.0, 2.0, 3.0),
    radius: float = 2.5,
    material_index: int = 7,
) -> bytes:
    data = bytearray(_RESOURCE_FILE_BASE_SIZE + 0x70)
    offset = _RESOURCE_FILE_BASE_SIZE
    cx, cy, cz = center
    minimum = (cx - radius, cy - radius, cz - radius)
    maximum = (cx + radius, cy + radius, cz + radius)
    struct.pack_into("<I", data, 0x04, 1)
    struct.pack_into("<B", data, offset + 0x00, 0)
    struct.pack_into("<f", data, offset + 0x04, radius)
    struct.pack_into("<3f", data, offset + 0x20, *maximum)
    struct.pack_into("<f", data, offset + 0x2C, 0.0)
    struct.pack_into("<3f", data, offset + 0x30, *minimum)
    struct.pack_into("<I", data, offset + 0x3C, 1)
    struct.pack_into("<3f", data, offset + 0x40, cx, cy, cz)
    data[offset + 0x4C] = material_index & 0xFF
    struct.pack_into("<3f", data, offset + 0x50, *center)
    struct.pack_into("<3f", data, offset + 0x60, 0.0, 0.0, 0.0)
    struct.pack_into("<f", data, offset + 0x6C, (4.0 / 3.0) * math.pi * (radius**3))
    return bytes(data)


def _build_test_ybn_bytes() -> bytes:
    return build_rsc7(_build_sphere_bound_block(), version=43, system_alignment=0x200)


def test_read_ybn_reads_sphere_bound() -> None:
    ybn = read_ybn(_build_test_ybn_bytes(), path="sphere.ybn")

    assert isinstance(ybn, Ybn)
    assert ybn.version == 43
    assert isinstance(ybn.bound, BoundSphere)
    assert ybn.bound.bound_type.value == 0
    assert ybn.bound.sphere_center == (1.0, 2.0, 3.0)
    assert ybn.bound.sphere_radius == 2.5
    assert ybn.bound.material_index == 7


def test_gamefilecache_parses_loose_ybn() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        path = root / "physics" / "sphere.ybn"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_build_test_ybn_bytes())

        cache = GameFileCache(root, use_index_cache=False)
        cache.scan(use_index_cache=False)

        game_file = cache.get_file("physics/sphere.ybn")
        assert game_file is not None
        assert game_file.kind == GameFileType.YBN
        assert isinstance(game_file.parsed, Ybn)
        assert isinstance(game_file.parsed.bound, BoundSphere)
        assert game_file.parsed.bound.sphere_radius == 2.5


def test_read_real_reference_ybn() -> None:
    path = Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\apa_ch2_04_12.ybn")

    ybn = read_ybn(path)

    assert ybn.bound.bound_type.name == "COMPOSITE"
    assert getattr(ybn.bound, "children", None)
