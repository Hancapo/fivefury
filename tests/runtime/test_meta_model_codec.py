import dataclasses
import gc
import struct

import pytest

from fivefury import _native_abi3 as native
from fivefury.meta.backed import MetaBackedStruct
from fivefury.metahash import _NATIVE_HASH_BINDING, MetaHash, MetaHashFieldsMixin
from fivefury.vector import Vector3


@dataclasses.dataclass(slots=True)
class DecodedRecord(MetaHashFieldsMixin):
    _hash_fields = ("name",)
    name: MetaHash
    position: Vector3


def model_plan():
    scalars = native.meta_scalars_new(16, [("hash", "hash", 0, 0x4A), ("pos", "pos", 4, 0x33)])
    return native.meta_model_new(scalars, DecodedRecord,
        [("name", _NATIVE_HASH_BINDING), ("position", (Vector3, ("x", "y", "z")))])


def test_model_reader_owns_schema_and_materializes_nominal_values():
    plan = model_plan()
    gc.collect()
    raw = struct.pack("<I3f", 0xFFFFFFFF, -0.0, 2.5, 3)
    left = native.meta_model_read(plan, memoryview(raw))
    right = native.meta_model_read(plan, raw)
    assert left == DecodedRecord(MetaHash(0xFFFFFFFF), Vector3(-0.0, 2.5, 3))
    assert left is not right and left.position is not right.position
    assert struct.pack("<f", left.position.x) == struct.pack("<f", -0.0)
    left.name = "edited"
    assert isinstance(left.name, MetaHash) and right.name.uint == 0xFFFFFFFF


def test_model_reader_rejects_truncated_data_and_incompatible_bindings():
    plan = model_plan()
    with pytest.raises(ValueError, match="truncated"):
        native.meta_model_read(plan, bytes(15))
    scalars = native.meta_scalars_new(12, [("pos", "pos", 0, 0x33)])
    with pytest.raises(ValueError, match="binding count"):
        native.meta_model_new(scalars, DecodedRecord, [])
    with pytest.raises(ValueError, match="vector"):
        native.meta_model_new(scalars, DecodedRecord, [("position", (Vector3, ("x", "y")))])


def test_model_array_resolves_owned_hash_lists_text_and_empty_references():
    record = type("References", (), {"__slots__": ("number", "values", "text", "extensions")})
    scalars = native.meta_scalars_new(56, [("number", "number", 0, 0x15)])
    plan = native.meta_model_new(scalars, record, [("number", None)], [
        ("values", 8, 0x52, 0x4A, _NATIVE_HASH_BINDING), ("text", 24, 0x44, 0, None), ("extensions", 40, 0x52, 0, None)])
    raw = bytearray(56)
    struct.pack_into("<I", raw, 0, 7)
    struct.pack_into("<QHH", raw, 8, 1, 2, 2)
    struct.pack_into("<QHH", raw, 24, 2, 3, 3)
    blocks = (struct.pack("<2I", 10, 20), b"abc", bytes(raw) * 2)
    def complete(*args):
        raise AssertionError("Simple references should be resolved with their scalar fields")
    left, right = native.meta_models_read((None, None, (plan, complete, None)), blocks, [3, 3], None)
    assert left.number == 7 and left.text == "abc" and left.extensions == []
    assert left.values == [MetaHash(10), MetaHash(20)]
    assert left is not right and left.values is not right.values and left.values[0] is not right.values[0]
    inline = native.meta_model_array_read((plan, complete, None), blocks, 3, 56, 2, None)
    assert [value.number for value in inline] == [7, 7] and inline[0] is not inline[1]
    with pytest.raises(ValueError, match="truncated"):
        native.meta_model_array_read((plan, complete, None), blocks, 3, 56, 3, None)
    struct.pack_into("<H", raw, 16, 3)
    with pytest.raises(ValueError, match="truncated"):
        native.meta_model_read(plan, raw, blocks)


def test_record_bindings_honor_custom_allocation_descriptors_and_serialization():
    class Record:
        created = 0
        def __new__(cls):
            cls.created += 1
            return super().__new__(cls)
        @property
        def value(self):
            return self._value
        @value.setter
        def value(self, value):
            self._value = value + 1
    scalars = native.meta_scalars_new(4, [("value", "value", 0, 0x15)])
    plan = native.meta_model_new(scalars, Record, [("value", None)])
    assert native.meta_model_read(plan, struct.pack("<I", 7)).value == 8
    assert Record.created == 1

    @dataclasses.dataclass(slots=True)
    class Custom(MetaBackedStruct):
        META_NAME = "TestCustom"
        value: int = 2
        def _serialize_field(self, attr, value):
            return value * 3
    value = Custom()
    assert value.to_meta()["value"] == 6
    Custom.META_FIELD_MAP = {"value": "renamed"}
    assert value.to_meta()["renamed"] == 6
