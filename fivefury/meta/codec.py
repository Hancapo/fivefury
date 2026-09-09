"""Compile immutable META field descriptions for the shared native scalar codec."""

from functools import lru_cache

from .. import _native_abi3
from .defs import META_TYPE_NAME_ARRAYINFO, MetaDataType

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
        else:
            complex_fields.append((index, entry, name))
    return _native_abi3.meta_scalars_new(size, scalars), tuple(complex_fields)
