import gc
import struct

import numpy as np
import pytest

from fivefury.binary import BinaryDocument, BinaryEndian, BinaryScalarType


@pytest.mark.parametrize(
    "kind,format,values",
    [
        (BinaryScalarType.UNSIGNED_BYTE, "B", [0, 255]),
        (BinaryScalarType.SIGNED_BYTE, "b", [-128, 127]),
        (BinaryScalarType.UNSIGNED_SHORT, "H", [0, 65535]),
        (BinaryScalarType.SIGNED_SHORT, "h", [-32768, 32767]),
        (BinaryScalarType.UNSIGNED_INT, "I", [0, 2**32 - 1]),
        (BinaryScalarType.SIGNED_INT, "i", [-(2**31), 2**31 - 1]),
        (BinaryScalarType.UNSIGNED_LONG, "Q", [0, 2**64 - 1]),
        (BinaryScalarType.SIGNED_LONG, "q", [-(2**63), 2**63 - 1]),
        (BinaryScalarType.FLOAT, "f", [-1.25, 2.5]),
    ],
)
@pytest.mark.parametrize(
    "endian,prefix", [(BinaryEndian.LITTLE, "<"), (BinaryEndian.BIG, ">")]
)
def test_arrays_and_lists_agree_across_scalar_types(
    kind, format, values, endian, prefix
):
    raw = b"x" + struct.pack(prefix + "2" + format, *values)
    document = BinaryDocument(raw)
    view = document.array(1, 2, kind, endian=endian)
    assert view.tolist() == document.read_array(1, 2, kind, endian=endian) == values
    assert not view.flags.writeable
    assert np.shares_memory(view, np.frombuffer(raw, dtype=np.uint8))
    del document, raw
    gc.collect()
    assert view.tolist() == values


def test_strided_vectors_and_empty_arrays():
    document = BinaryDocument(struct.pack(">4f4f", 1, 2, 3, 99, 4, 5, 6, 99))
    view = document.array(
        0, 2, BinaryScalarType.FLOAT, endian=BinaryEndian.BIG, stride=16, components=3
    )
    assert view.strides == (16, 4)
    assert view.tolist() == [[1, 2, 3], [4, 5, 6]]
    assert document.read_array(
        0, 2, BinaryScalarType.FLOAT, endian=BinaryEndian.BIG, stride=16, components=3
    ) == [(1, 2, 3), (4, 5, 6)]
    assert document.array(len(document), 0, BinaryScalarType.FLOAT).shape == (0,)


@pytest.mark.parametrize("method", ["array", "read_array"])
@pytest.mark.parametrize(
    "offset,count,options",
    [
        (-1, 1, {}),
        (0, -1, {}),
        (0, 1, {"stride": -1}),
        (0, 1, {"stride": 1}),
        (0, 1, {"components": 5}),
        (0, 3, {}),
        (9, 0, {}),
        (0, 2**62, {"stride": 2**62}),
        (0, 1, {"endian": 2}),
    ],
)
def test_list_and_view_share_layout_validation(method, offset, count, options):
    document = BinaryDocument(bytes(8))
    with pytest.raises(ValueError):
        getattr(document, method)(
            offset, count, BinaryScalarType.UNSIGNED_INT, **options
        )
