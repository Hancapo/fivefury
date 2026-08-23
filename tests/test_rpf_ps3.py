from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from fivefury import GameFileCache
from fivefury.crypto import GameCrypto
from fivefury.rpf import (
    RPF_BLOCK_SIZE,
    RPF_MAGIC,
    RpfArchive,
    RpfEncryption,
    RpfPlatform,
)
from tests.helpers import configured_path, reference_root


def _to_ps3_entry_bytes(pc_entry: bytes) -> bytes:
    return pc_entry[:8][::-1] + pc_entry[8:12][::-1] + pc_entry[12:16][::-1]


def _pack_ps3_directory(name_offset: int, entries_index: int, entries_count: int) -> bytes:
    return _to_ps3_entry_bytes(struct.pack("<IIII", name_offset, 0x7FFFFF00, entries_index, entries_count))


def _pack_ps3_binary(name_offset: int, file_size: int, file_offset: int, uncompressed_size: int, encryption: int) -> bytes:
    low = (name_offset & 0xFFFF) | ((file_size & 0xFFFFFF) << 16) | ((file_offset & 0xFFFFFF) << 40)
    return _to_ps3_entry_bytes(struct.pack("<QII", low, uncompressed_size, encryption))


def _build_minimal_ps3_rpf() -> bytes:
    names = b"\x00hello.bin\x00"
    payload = b"hello from ps3"
    entries = b"".join(
        (
            _pack_ps3_directory(0, 1, 1),
            _pack_ps3_binary(1, 0, 1, len(payload), 0),
        )
    )
    header = b"".join(
        (
            RPF_MAGIC.to_bytes(4, "big"),
            (2).to_bytes(4, "big"),
            len(names).to_bytes(4, "big"),
            (0).to_bytes(4, "big"),
        )
    )
    body_start = RPF_BLOCK_SIZE
    data = bytearray(header + entries + names)
    data.extend(bytes(body_start - len(data)))
    data.extend(payload)
    return bytes(data)


class RpfPs3Tests(unittest.TestCase):
    def test_rpf_reader_parses_big_endian_ps3_layout(self) -> None:
        archive = RpfArchive.from_bytes(_build_minimal_ps3_rpf(), name="ps3_test.rpf")
        entry = archive.find_entry("hello.bin")

        self.assertEqual(archive.platform, RpfPlatform.PS3)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.read(), b"hello from ps3")

    def test_standalone_export_decompresses_binary_entries(self) -> None:
        from fivefury import create_rpf

        archive = create_rpf("compressed_text.rpf")
        archive.file("data/readable.meta", b"<Meta>readable</Meta>", compress_binary=True)
        packed = archive.to_bytes()
        reread = RpfArchive.from_bytes(packed, name="compressed_text.rpf")
        entry = reread.find_entry("data/readable.meta")

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(reread.read_entry_standalone(entry), b"<Meta>readable</Meta>")

    def test_gamefilecache_indexes_big_endian_ps3_rpf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "ps3_test.rpf").write_bytes(_build_minimal_ps3_rpf())

            cache = GameFileCache(root, use_index_cache=False)
            cache.scan(use_index_cache=False, scan_workers=1)

            self.assertIsNotNone(cache.find_path("ps3_test.rpf/hello.bin"))

    def test_ps3_writer_roundtrips_open_and_encrypted_archives(self) -> None:
        crypto = GameCrypto.from_aes_key(bytes(range(32)))
        expected = b"compressed ps3 payload" * 1000
        for encryption in (RpfEncryption.OPEN, RpfEncryption.PS3_AES):
            with self.subTest(encryption=encryption):
                archive = RpfArchive.empty(
                    "ps3_writer.rpf",
                    platform=RpfPlatform.PS3,
                    encryption=encryption,
                    crypto=crypto,
                )
                archive.file("payload.bin", expected, compress_binary=True)
                packed = archive.to_bytes()

                self.assertEqual(len(packed) % 2048, 0)
                reread = RpfArchive.from_bytes(
                    packed,
                    name="ps3_writer.rpf",
                    crypto=crypto,
                )
                entry = reread.find_entry("payload.bin")
                self.assertIsNotNone(entry)
                assert entry is not None
                self.assertEqual(reread.platform, RpfPlatform.PS3)
                self.assertEqual(entry.read(), expected)

    def test_rpf_reader_opens_real_ps3_archive_when_available(self) -> None:
        usrdir = configured_path(
            "FIVEFURY_TEST_PS3_USRDIR",
            reference_root() / "ps3_usrdir",
        )
        source = usrdir / "audio_rel.rpf"
        if not source.exists():
            self.skipTest("PS3 GTA V fixture is not available")

        archive = RpfArchive.from_path(source)

        self.assertEqual(archive.platform, RpfPlatform.PS3)
        self.assertGreater(len(list(archive.iter_entries())), 0)


if __name__ == "__main__":
    unittest.main()
