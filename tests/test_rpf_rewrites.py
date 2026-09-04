import io

import pytest

from fivefury.rpf import RpfArchive


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
