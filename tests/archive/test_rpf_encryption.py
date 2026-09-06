from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fivefury.crypto import GameCrypto
from fivefury.rpf import RpfArchive, RpfEncryption, RpfFileSource


def _crypto() -> GameCrypto:
    return GameCrypto.from_aes_key(bytes(range(32)))


class RpfEncryptionTests(unittest.TestCase):
    def test_native_archive_crypto_roundtrips_aligned_prefixes(self) -> None:
        crypto = _crypto()
        for encryption in (
            RpfEncryption.AES,
            RpfEncryption.NG,
            RpfEncryption.PS3_AES,
        ):
            with self.subTest(encryption=encryption):
                source = bytes((index * 37 + 11) & 0xFF for index in range(513))
                encoded = crypto.encrypt_archive_table(
                    source,
                    encryption,
                    archive_name="crypto_test.rpf",
                    archive_size=123456,
                )
                decoded = crypto.decrypt_archive_table(
                    encoded,
                    encryption,
                    archive_name="crypto_test.rpf",
                    archive_size=123456,
                )
                self.assertEqual(decoded, source)

    def test_aes_and_ng_archives_roundtrip_binary_and_resource_entries(self) -> None:
        crypto = _crypto()
        expected = {
            "plain.bin": bytes(range(251)) * 3,
            "compressed.bin": b"compress me" * 1000,
            "asset.ymap": b"<CMapData><name>test</name></CMapData>",
        }
        for encryption in (RpfEncryption.AES, RpfEncryption.NG):
            with self.subTest(encryption=encryption):
                archive = RpfArchive.empty(
                    "writer_test.rpf",
                    encryption=encryption,
                    crypto=crypto,
                )
                archive.file("plain.bin", expected["plain.bin"])
                archive.file(
                    "compressed.bin",
                    expected["compressed.bin"],
                    compress_binary=True,
                )
                archive.file("asset.ymap", expected["asset.ymap"])

                reread = RpfArchive.from_bytes(
                    archive.to_bytes(),
                    name="writer_test.rpf",
                    crypto=crypto,
                )

                for name, payload in expected.items():
                    entry = reread.find_entry(name)
                    self.assertIsNotNone(entry)
                    assert entry is not None
                    self.assertEqual(entry.read(), payload)

    def test_encrypted_file_backed_compression_stays_streamed(self) -> None:
        crypto = _crypto()
        payload = (b"abc0123456789" * 100000) + b"end"
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "large.bin"
            source_path.write_bytes(payload)
            archive = RpfArchive.empty(
                "streamed.rpf",
                encryption=RpfEncryption.NG,
                crypto=crypto,
            )
            archive.file_path(
                "large.bin",
                RpfFileSource.compressed(source_path),
            )

            reread = RpfArchive.from_bytes(
                archive.to_bytes(),
                name="streamed.rpf",
                crypto=crypto,
            )
            entry = reread.find_entry("large.bin")
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertEqual(entry.read(), payload)

    def test_unchanged_archive_is_preserved_byte_for_byte(self) -> None:
        crypto = _crypto()
        archive = RpfArchive.empty(
            "preserved.rpf",
            encryption=RpfEncryption.NG,
            crypto=crypto,
        )
        archive.file("payload.bin", b"unchanged" * 100, compress_binary=True)
        original = archive.to_bytes()

        reread = RpfArchive.from_bytes(
            original,
            name="preserved.rpf",
            crypto=crypto,
        )
        self.assertEqual(reread.to_bytes(), original)

        original_entry = reread.find_entry("payload.bin")
        self.assertIsNotNone(original_entry)
        assert original_entry is not None
        original_stored = original_entry.read_raw()

        reread.file("added.bin", b"added")
        changed = reread.to_bytes()
        self.assertNotEqual(changed, original)

        changed_reread = RpfArchive.from_bytes(
            changed,
            name="preserved.rpf",
            crypto=crypto,
        )
        preserved = changed_reread.find_entry("payload.bin")
        self.assertIsNotNone(preserved)
        assert preserved is not None
        self.assertEqual(preserved.read(), b"unchanged" * 100)
        self.assertEqual(preserved.read_raw(), original_stored)
        added = changed_reread.find_entry("added.bin")
        self.assertIsNotNone(added)
        assert added is not None
        self.assertEqual(added.read(), b"added")

    def test_renamed_encrypted_entry_is_reencrypted_for_its_new_name(self) -> None:
        crypto = _crypto()
        payload = b"rename me" * 100
        archive = RpfArchive.empty(
            "renamed.rpf",
            encryption=RpfEncryption.NG,
            crypto=crypto,
        )
        archive.file("original.bin", payload, compress_binary=True)

        reread = RpfArchive.from_bytes(
            archive.to_bytes(),
            name="renamed.rpf",
            crypto=crypto,
        )
        entry = reread.find_entry("original.bin")
        self.assertIsNotNone(entry)
        assert entry is not None
        entry.name = "renamed.bin"
        entry.path = "renamed.bin"

        changed = RpfArchive.from_bytes(
            reread.to_bytes(),
            name="renamed.rpf",
            crypto=crypto,
        )
        renamed = changed.find_entry("renamed.bin")
        self.assertIsNotNone(renamed)
        assert renamed is not None
        self.assertEqual(renamed.read(), payload)


if __name__ == "__main__":
    unittest.main()
