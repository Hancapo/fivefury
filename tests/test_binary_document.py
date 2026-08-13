from __future__ import annotations

import struct

import pytest

from fivefury.binary import BinaryDocument, BinaryEndian, BinaryScalarType


def test_binary_document_reads_checked_slices_and_strings() -> None:
    document = BinaryDocument(b"header\x00payload")

    assert len(document) == 14
    assert document.c_string(0) == "header"
    assert document.slice(7, 7) == b"payload"

    with pytest.raises(ValueError, match="outside the document"):
        document.slice(10, 5)


def test_binary_document_reads_endian_scalar_and_strided_vector_arrays() -> None:
    integers = struct.pack(">3I", 1, 0x10203040, 0xFFFFFFFF)
    vectors = struct.pack("<4f4f", 1.0, 2.0, 3.0, 99.0, -1.0, -2.0, -3.0, 99.0)
    document = BinaryDocument(integers + vectors)

    assert document.read_array(
        0,
        3,
        BinaryScalarType.UNSIGNED_INT,
        endian=BinaryEndian.BIG,
    ) == [1, 0x10203040, 0xFFFFFFFF]
    assert document.read_array(
        len(integers),
        2,
        BinaryScalarType.FLOAT,
        stride=16,
        components=3,
    ) == [(1.0, 2.0, 3.0), (-1.0, -2.0, -3.0)]


def test_binary_document_rejects_truncated_arrays() -> None:
    document = BinaryDocument(b"\x00" * 7)

    with pytest.raises(ValueError, match="truncated"):
        document.read_array(0, 2, BinaryScalarType.UNSIGNED_INT)
