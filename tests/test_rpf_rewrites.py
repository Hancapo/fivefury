import io

import pytest

from fivefury.crypto import GameCrypto
from fivefury.rpf import RpfArchive, RpfEncryption, RpfFileSource


def source_archive():
    archive = RpfArchive.empty()
    archive.file("b.bin", b"B" * 512)
    archive.file("c.bin", b"C" * 512)
    return archive.to_bytes()


@pytest.mark.parametrize("backing", ("memory", "file", "inplace"))
def test_rewriting_preserves_source_reads_and_repeated_saves(tmp_path, backing):
    path = tmp_path / "archive.rpf"
    path.write_bytes(source_archive())
    archive = (
        RpfArchive.from_bytes(path.read_bytes())
        if backing == "memory"
        else RpfArchive.from_path(path)
    )
    with archive:
        entry = archive.find_entry("b.bin")
        archive.file("a.bin", b"A" * 512)
        for _ in range(3):
            if backing == "inplace":
                archive.save(path)
                result = path.read_bytes()
            else:
                result = archive.to_bytes()
            assert entry.read() == b"B" * 512
            reread = RpfArchive.from_bytes(result)
            assert reread.find_entry("b.bin").read() == b"B" * 512
            assert reread.find_entry("c.bin").read() == b"C" * 512


def test_interrupted_write_does_not_change_source_reads():
    class InterruptedOutput(io.BytesIO):
        def write(self, data):
            if self.tell() >= 1024:
                raise OSError("interrupted")
            return super().write(data)

    archive = RpfArchive.from_bytes(source_archive())
    archive.file("a.bin", b"A" * 512)
    with pytest.raises(OSError, match="interrupted"):
        archive.write_to(InterruptedOutput())
    assert archive.find_entry("b.bin").read() == b"B" * 512
    assert RpfArchive.from_bytes(archive.to_bytes()).find_entry("c.bin").read() == b"C" * 512


@pytest.mark.parametrize("backing", ("bytes", "file", "parsed"))
def test_nested_archive_edits_take_precedence_over_original_payload(tmp_path, backing):
    child = RpfArchive.empty("child.rpf")
    child.file("payload.bin", b"old")
    path = tmp_path / "child.rpf"
    child.save(path)
    parent = RpfArchive.empty()
    if backing == "file":
        entry = parent.file_path("child.rpf", RpfFileSource.archive(path))
        parent.load_nested_archive(entry, strict=True)
    else:
        entry = parent.file("child.rpf", path.read_bytes())
        if backing == "parsed":
            parent = RpfArchive.from_bytes(parent.to_bytes(), load_nested=True)
            entry = parent.root.files[0]
    entry.child_archive.file("payload.bin", b"new" * 1024)
    for _ in range(2):
        reread = RpfArchive.from_bytes(parent.to_bytes(), load_nested=True)
        assert reread.children[0].root.files[0].read() == b"new" * 1024


@pytest.mark.parametrize("source_mode", (RpfEncryption.OPEN, RpfEncryption.AES, RpfEncryption.NG))
@pytest.mark.parametrize("target_mode", (RpfEncryption.NONE, RpfEncryption.OPEN, RpfEncryption.AES, RpfEncryption.NG))
def test_encryption_transition_preserves_source_reads(tmp_path, source_mode, target_mode):
    original_crypto = GameCrypto.from_aes_key(bytes(range(32)))
    target_crypto = GameCrypto.from_aes_key(bytes(reversed(range(32))))
    archive = RpfArchive.empty("transition.rpf", encryption=source_mode, crypto=original_crypto)
    payload = b"compressed payload" * 1024
    archive.file("payload.bin", payload, compress_binary=True)
    path = tmp_path / "transition.rpf"
    archive.save(path)
    with RpfArchive.from_path(path, crypto=original_crypto) as parsed:
        entry = parsed.find_entry("payload.bin")
        parsed.encryption = target_mode
        parsed.crypto = target_crypto
        entry.name = "renamed.bin"
        assert entry.read() == payload
        for _ in range(2):
            result = parsed.to_bytes()
            assert entry.read() == payload
            rebuilt = RpfArchive.from_bytes(result, name=parsed.name, crypto=target_crypto)
            assert rebuilt.find_entry("renamed.bin").read() == payload
        parsed.save(path)
        assert entry.read() == payload
