"""Compile immutable META field descriptions for the shared native scalar codec."""

from functools import lru_cache
import struct

from .. import _native_abi3
from .defs import META_TYPE_NAME_ARRAYINFO, MetaDataType
from .utils import _array_info_for_entries

_INLINE_SCALARS = frozenset((MetaDataType.FLOAT, MetaDataType.HASH,
    MetaDataType.SIGNED_BYTE, MetaDataType.UNSIGNED_BYTE, MetaDataType.SIGNED_SHORT,
    MetaDataType.UNSIGNED_SHORT, MetaDataType.SIGNED_INT, MetaDataType.UNSIGNED_INT))

_SCALARS = frozenset(
    (
        MetaDataType.BOOLEAN,
        MetaDataType.SIGNED_BYTE,
        MetaDataType.UNSIGNED_BYTE,
        MetaDataType.SIGNED_SHORT,
        MetaDataType.UNSIGNED_SHORT,
        MetaDataType.SIGNED_INT,
        MetaDataType.UNSIGNED_INT,
        MetaDataType.FLOAT,
        MetaDataType.FLOAT_XYZ,
        MetaDataType.FLOAT_XYZW,
        MetaDataType.HASH,
        MetaDataType.BYTE_ENUM,
        MetaDataType.SHORT_FLAGS,
        MetaDataType.INT_ENUM,
        MetaDataType.INT_FLAGS_1,
        MetaDataType.INT_FLAGS_2,
    )
)


@lru_cache(maxsize=256)
def camel_to_snake(value: str) -> str:
    return "".join(
        ("_" if char.isupper() and index and not value[index - 1].isupper() else "")
        + char.lower()
        for index, char in enumerate(value)
    )


@lru_cache(maxsize=256)
def scalar_plan(size, entries):
    scalars, complex_fields = [], []
    for index, entry in enumerate(entries):
        if entry.name_hash == META_TYPE_NAME_ARRAYINFO:
            continue
        name = entry.name
        if entry.data_type in _SCALARS:
            scalars.append(
                (name, camel_to_snake(name), entry.data_offset, int(entry.data_type))
            )
        elif (entry.data_type is MetaDataType.ARRAY_OF_BYTES
              and (array_info := _array_info_for_entries(entries, index)) is not None
              and array_info.data_type in _INLINE_SCALARS):
            scalars.append((name, camel_to_snake(name), entry.data_offset,
                            int(array_info.data_type), entry.reference_key & 0xFFFF))
        else:
            complex_fields.append((index, entry, name))
    return _native_abi3.meta_scalars_new(size, scalars), tuple(complex_fields)


@lru_cache(maxsize=256)
def schema_field_bytes(entries):
    """Encode an immutable field snapshot; owner headers and pointers remain per-file."""
    return b"".join(struct.pack("<IIBBHI", entry.name_hash, entry.data_offset,
        int(entry.data_type), entry.unknown_9h, entry.reference_type_index, entry.reference_key)
        for entry in entries)


@lru_cache(maxsize=256)
def schema_enum_bytes(entries):
    return b"".join(struct.pack("<Ii", name_hash, value) for name_hash, value in entries)
