from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import RpfArchive, RpfEncryption, RpfPlatform, ValidationError


def test_rpf_authoring_requires_typed_encryption() -> None:
    with pytest.raises(TypeError, match="RpfEncryption"):
        RpfArchive(encryption=0x4E45504F)  # type: ignore[arg-type]


def test_rpf_validation_reports_invalid_nested_archive() -> None:
    archive = RpfArchive.empty("outer.rpf")
    archive.file("broken.rpf", b"not an rpf")

    report = archive.validate()

    assert not report.valid
    assert report.errors[0].code == "rpf.nested.magic"


def test_rpf_save_is_atomic_when_validation_fails(tmp_path: Path) -> None:
    destination = tmp_path / "archive.rpf"
    destination.write_bytes(b"existing")
    archive = RpfArchive.empty("archive.rpf")
    archive.file("bad\0name.bin", b"payload")

    with pytest.raises(ValidationError, match="rpf.name.nul"):
        archive.save(destination)

    assert destination.read_bytes() == b"existing"
    assert not list(tmp_path.glob("*.tmp"))


def test_ps3_validation_rejects_pc_encryption() -> None:
    archive = RpfArchive.empty(
        "archive.rpf",
        platform=RpfPlatform.PS3,
        encryption=RpfEncryption.NG,
    )

    report = archive.validate()

    assert not report.valid
    assert report.errors[0].code == "rpf.encryption.platform"


def test_rpf_validation_accepts_minimal_pc_archive() -> None:
    archive = RpfArchive.empty("archive.rpf")
    archive.file("data/value.meta", b"<value />")

    assert archive.validate().valid
