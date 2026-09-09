import struct

import pytest

from fivefury import Quaternion, Vector3
from fivefury import _native_abi3 as native
from fivefury.hashing import jenk_hash
from fivefury.metahash import MetaHash


@pytest.mark.parametrize(
    "kind,fmt,value",
    [
        (1, "?", True),
        (0x10, "b", -128),
        (0x11, "B", 255),
        (0x12, "h", -32768),
        (0x13, "H", 65535),
        (0x14, "i", -2147483648),
        (0x15, "I", 4294967295),
        (0x21, "f", 1.25),
        (0x60, "B", 255),
        (0x64, "h", -32768),
        (0x62, "i", -7),
        (0x63, "i", -9),
        (0x65, "i", 17),
        (0x4A, "I", MetaHash("prop_test")),
    ],
)
def test_scalar_layout_and_alias(kind, fmt, value):
    size = struct.calcsize("<" + fmt)
    plan = native.meta_scalars_new(size + 2, [("testValue", "test_value", 1, kind)])
    expected = int(value) if isinstance(value, MetaHash) else value
    raw = native.meta_scalars_write(plan, {"test_value": value}, jenk_hash)
    assert raw == b"\0" + struct.pack("<" + fmt, expected) + b"\0"
    assert native.meta_scalars_read(plan, memoryview(raw)) == {"testValue": expected}
    assert native.meta_scalars_write(plan, {}, jenk_hash) == bytes(size + 2)


def test_vectors_hashes_and_numeric_conversion():
    plan = native.meta_scalars_new(
        36,
        [
            ("position", "position", 0, 0x33),
            ("rotation", "rotation", 12, 0x34),
            ("name", "name", 28, 0x4A),
            ("distance", "distance", 32, 0x21),
        ],
    )
    value = {
        "position": Vector3(1, 2, 3),
        "rotation": Quaternion(),
        "name": "prop_test",
        "distance": "1.5",
    }
    raw = native.meta_scalars_write(plan, value, jenk_hash)
    assert raw == struct.pack("<7fIf", 1, 2, 3, 0, 0, 0, 1, jenk_hash("prop_test"), 1.5)
    assert native.meta_scalars_read(plan, raw)["position"] == (1, 2, 3)
    with pytest.raises(ValueError):
        native.meta_scalars_write(plan, {"position": (1, 2)}, jenk_hash)
    with pytest.raises(TypeError):
        native.meta_scalars_write(plan, {"position": "123"}, jenk_hash)


def test_invalid_layout_buffers_and_overflow():
    with pytest.raises(ValueError):
        native.meta_scalars_new(1, [("value", "value", 0, 0x15)])
    with pytest.raises(ValueError):
        native.meta_scalars_new(4, [("value", "value", -1, 0x15)])
    with pytest.raises(ValueError):
        native.meta_scalars_new(4, [("value", "value", 0, 0xFF)])
    plan = native.meta_scalars_new(4, [("value", "value", 0, 0x15)])
    with pytest.raises(ValueError):
        native.meta_scalars_read(plan, b"\0")
    with pytest.raises(TypeError):
        native.meta_scalars_read(plan, "abcd")
    for value in (-1, 2**32):
        with pytest.raises(OverflowError):
            native.meta_scalars_write(plan, {"value": value}, jenk_hash)


def test_scalar_false_values_and_vector_negative_zero():
    plan = native.meta_scalars_new(
        16, [("scalar", "scalar", 0, 0x21), ("vector", "vector", 4, 0x33)]
    )
    raw = native.meta_scalars_write(
        plan, {"scalar": -0.0, "vector": (-0.0, 0, 0)}, jenk_hash
    )
    assert raw == struct.pack("<4f", 0, -0.0, 0, 0)
