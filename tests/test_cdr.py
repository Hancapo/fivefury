from __future__ import annotations

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from fivefury import Cdr, CdrGeometryType, CdrLod, GameFileCache, GameFileType, read_cdr
from fivefury.cdr.resource import get_ps3_resource_size_from_flags, split_ps3_rsc7_sections
from fivefury.cdr.shaders import get_cdr_parameter_definition, get_cdr_shader_definition
from fivefury.cdr.vertices import decompress_edge_indices
from fivefury.gamefile import guess_game_file_type
from fivefury.resource import RSC7_MAGIC

_PS3_REFERENCE = Path(
    r"C:\Users\vicho\OneDrive\Desktop\USRDIR_ps3_rpfs_extracted\part0\levels\gta5\_citye\downtown_01\dt1_00.rpf"
)


def _ptr(offset: int) -> int:
    return 0x50000000 + offset


def _physical(offset: int) -> int:
    return 0x60000000 + offset


def _build_minimal_cdr() -> bytes:
    system_flags = 0xA0020000
    graphics_flags = 0x40020000
    system = bytearray(get_ps3_resource_size_from_flags(system_flags, 4096))
    graphics = bytearray(get_ps3_resource_size_from_flags(graphics_flags, 5504))

    struct.pack_into(">I", system, 0x40, _ptr(0x100))
    struct.pack_into(">3f", system, 0x10, 0.5, 0.5, 0.0)
    struct.pack_into(">f", system, 0x1C, 1.0)
    struct.pack_into(">3f", system, 0x20, 0.0, 0.0, 0.0)
    struct.pack_into(">3f", system, 0x30, 1.0, 1.0, 0.0)
    struct.pack_into(">f", system, 0x50, 100.0)
    struct.pack_into(">IHH", system, 0x100, _ptr(0x120), 1, 1)
    struct.pack_into(">I", system, 0x120, _ptr(0x140))

    struct.pack_into(">I", system, 0x140, 0x12345678)
    struct.pack_into(">IHH", system, 0x144, _ptr(0x160), 1, 1)
    struct.pack_into(">I", system, 0x14C, _ptr(0x180))
    struct.pack_into(">I", system, 0x150, _ptr(0x170))
    struct.pack_into(">6B", system, 0x154, 0, 0, 0, 0, 0xFF, 0)
    struct.pack_into(">H", system, 0x15A, 1)
    struct.pack_into(">I", system, 0x160, _ptr(0x1A0))
    struct.pack_into(">H", system, 0x170, 0)
    struct.pack_into(">4f4f", system, 0x180, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0)

    struct.pack_into(">III", system, 0x1A0, 0x11111111, 0, 0)
    struct.pack_into(">I", system, 0x1AC, _ptr(0x1F0))
    struct.pack_into(">I", system, 0x1BC, _ptr(0x230))
    struct.pack_into(">II", system, 0x1CC, 3, 1)
    struct.pack_into(">HBB", system, 0x1D4, 3, 3, 0)
    struct.pack_into(">BBH", system, 0x1DC, 12, 0, 0)

    struct.pack_into(">I", system, 0x1F0, 0x22222222)
    struct.pack_into(">HBB", system, 0x1F4, 12, 0, 0)
    struct.pack_into(">I", system, 0x1F8, _physical(0))
    struct.pack_into(">I", system, 0x1FC, 3)
    struct.pack_into(">I", system, 0x208, _ptr(0x220))
    struct.pack_into(">I", system, 0x20C, _physical(0))
    struct.pack_into(">IBBBBQ", system, 0x220, 1, 12, 0, 0, 1, 6)
    struct.pack_into(">III", system, 0x230, 0x33333333, 3, _physical(36))

    struct.pack_into(">9f", graphics, 0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    struct.pack_into(">3H", graphics, 36, 0, 1, 2)
    payload = bytes(system + graphics)
    compressed = zlib.compress(payload, level=9, wbits=-15)
    return struct.pack("<4I", RSC7_MAGIC, 164, system_flags, graphics_flags) + compressed


class CdrTests(unittest.TestCase):
    def test_ps3_resource_uses_console_leaf_sizes(self) -> None:
        data = _build_minimal_cdr()
        header, system, graphics = split_ps3_rsc7_sections(data)

        self.assertEqual(header.version, 164)
        self.assertEqual(len(system), 4096)
        self.assertEqual(len(graphics), 5504)

    def test_read_minimal_quick_buffer_drawable(self) -> None:
        drawable = read_cdr(_build_minimal_cdr(), path="triangle.cdr")
        mesh = drawable.lods[CdrLod.HIGH][0].meshes[0]

        self.assertEqual(drawable.platform, "ps3")
        self.assertEqual(mesh.geometry_type, CdrGeometryType.QUICK_BUFFER)
        self.assertEqual(mesh.positions, [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
        self.assertEqual(mesh.indices, [0, 1, 2])

    def test_decompress_edge_triangle_reuse_stream(self) -> None:
        raw = struct.pack(">3HBB", 0, 0, 1, 0, 0) + b"\x00\xC0"

        self.assertEqual(decompress_edge_indices(raw, 6), [0, 1, 2, 0, 2, 3])

    def test_cdr_extension_is_registered(self) -> None:
        self.assertEqual(guess_game_file_type("example.cdr"), GameFileType.CDR)

    def test_ps3_only_shader_catalog(self) -> None:
        shader = get_cdr_shader_definition(0xA1CF7B67)

        self.assertIsNotNone(shader)
        assert shader is not None
        self.assertEqual(shader.name, "trees_lod2d")
        self.assertEqual(shader.pick_file_name(3), "trees_lod2d.sps")
        self.assertEqual(shader.get_parameter(0x744E7500).name, "treeLod2Params")
        self.assertEqual(get_cdr_parameter_definition(0xD545098C).name, "RESERVE_VS_CONST_c255")

    def test_gamefilecache_loads_loose_cdr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "triangle.cdr"
            source.write_bytes(_build_minimal_cdr())
            cache = GameFileCache(tmpdir, use_index_cache=False)
            cache.scan(use_index_cache=False, scan_workers=1)

            loaded = cache.load_asset("triangle.cdr")

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.kind, GameFileType.CDR)
            self.assertIsInstance(loaded.parsed, Cdr)
            self.assertEqual(len(cache.CdrDict), 1)

    def test_real_edge_drawable_when_available(self) -> None:
        source = _PS3_REFERENCE / "dt1_00_3.cdr"
        if not source.exists():
            self.skipTest("PS3 CDR fixture is not available")

        drawable = read_cdr(source)

        self.assertEqual(len(drawable.materials), 5)
        self.assertEqual(len(drawable.meshes), 5)
        self.assertTrue(all(mesh.geometry_type is CdrGeometryType.EDGE for mesh in drawable.meshes))
        self.assertTrue(all(mesh.indices and max(mesh.indices) < mesh.vertex_count for mesh in drawable.meshes))

    def test_real_quick_buffer_drawable_when_available(self) -> None:
        source = _PS3_REFERENCE / "dt1_00_telegraph_cables_01.cdr"
        if not source.exists():
            self.skipTest("PS3 CDR fixture is not available")

        drawable = read_cdr(source)
        mesh = drawable.meshes[0]

        self.assertEqual(mesh.geometry_type, CdrGeometryType.QUICK_BUFFER)
        self.assertEqual(mesh.vertex_count, 112)
        self.assertEqual(mesh.index_count, 288)

    def test_real_ps3_only_tree_shader_when_available(self) -> None:
        source = (
            _PS3_REFERENCE.parents[2]
            / "props"
            / "vegetation"
            / "v_bush.rpf"
            / "prop_bush_med_01.cdr"
        )
        if not source.exists():
            self.skipTest("PS3 vegetation CDR fixture is not available")

        drawable = read_cdr(source)
        material = next(item for item in drawable.materials if item.shader_hash == 0xA1CF7B67)

        self.assertEqual(material.shader_name, "trees_lod2d")
        self.assertEqual(material.shader_file_name, "trees_lod2d.sps")
        self.assertEqual(
            [parameter.name for parameter in material.parameters],
            [
                "DiffuseSampler",
                "UseTreeNormals",
                "treeLod2Normal",
                "treeLod2Params",
                "RESERVE_VS_CONST_c255",
                "RESERVE_VS_CONST_c254",
                "RESERVE_VS_CONST_c253",
            ],
        )


if __name__ == "__main__":
    unittest.main()
