from __future__ import annotations

from . import MetaFieldInfo, MetaStructInfo
from .defs import META_TYPE_NAME_ARRAYINFO, MetaDataType, meta_name


def array_info_for_field(struct_info: MetaStructInfo, field_index: int) -> MetaFieldInfo | None:
    return _array_info_for_entries(struct_info.entries, field_index)


def _array_info_for_entries(entries, field_index: int) -> MetaFieldInfo | None:
    if not (0 <= field_index < len(entries)):
        return None
    if field_index > 0 and entries[field_index - 1].name_hash == META_TYPE_NAME_ARRAYINFO:
        return entries[field_index - 1]
    ref_index = entries[field_index].reference_type_index
    if 0 <= ref_index < len(entries):
        candidate = entries[ref_index]
        if candidate.name_hash == META_TYPE_NAME_ARRAYINFO:
            return candidate
    return None


def meta_field_entry(
    name: str | int,
    offset: int,
    data_type: MetaDataType,
    unknown_9h: int = 0,
    ref_index: int = 0,
    ref_key: str | int = 0,
) -> MetaFieldInfo:
    name_hash = name if isinstance(name, int) else meta_name(name)
    ref_hash = meta_name(ref_key) if isinstance(ref_key, str) else ref_key
    return MetaFieldInfo(name_hash, offset, data_type, unknown_9h, ref_index, ref_hash)


def meta_array_info(data_type: MetaDataType, *, ref_key: str | int = 0, unknown_9h: int = 0) -> MetaFieldInfo:
    ref_hash = meta_name(ref_key) if isinstance(ref_key, str) else ref_key
    return MetaFieldInfo(META_TYPE_NAME_ARRAYINFO, 0, data_type, unknown_9h, 0, ref_hash)


__all__ = ["array_info_for_field", "meta_array_info", "meta_field_entry"]
