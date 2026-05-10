from __future__ import annotations

from enum import IntEnum, IntFlag

from ..meta import MetaEnumEntry, MetaEnumInfo, MetaStructInfo
from ..meta.defs import MetaDataType, meta_name
from ..meta.utils import meta_array_info as _arrayinfo
from ..meta.utils import meta_field_entry as _entry
from .enums import ManifestFlags, PackFileMetaDataAssetType, PackFileMetaDataImapGroupType


def _enum_info(name: str, enum_type: type[IntEnum] | type[IntFlag]) -> MetaEnumInfo:
    return MetaEnumInfo(
        name_hash=meta_name(name),
        key=meta_name(f"{name}_key"),
        entries=[MetaEnumEntry(meta_name(item.name), int(item)) for item in enum_type if int(item) != 0 or item.name == "AT_TXD"],
    )


YMF_ENUM_INFOS = [
    _enum_info("ePackFileMetaDataAssetType", PackFileMetaDataAssetType),
    _enum_info("ePackFileMetaDataImapGroupType", PackFileMetaDataImapGroupType),
    _enum_info("manifestFlags", ManifestFlags),
]

YMF_STRUCT_INFOS = [
    MetaStructInfo(
        name_hash=meta_name("CHDTxdAssetBinding"),
        key=meta_name("CHDTxdAssetBinding_key"),
        unknown=256,
        structure_size=132,
        entries=[
            _entry("assetType", 0, MetaDataType.INT_ENUM, ref_key="ePackFileMetaDataAssetType"),
            _entry("targetAsset", 4, MetaDataType.ARRAY_OF_CHARS, ref_key=64),
            _entry("HDTxd", 68, MetaDataType.ARRAY_OF_CHARS, ref_key=64),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CMapDataGroup"),
        key=meta_name("CMapDataGroup_key"),
        unknown=256,
        structure_size=56,
        entries=[
            _entry("Name", 0, MetaDataType.HASH),
            _arrayinfo(MetaDataType.HASH),
            _entry("Bounds", 8, MetaDataType.ARRAY, ref_index=1),
            _entry("Flags", 24, MetaDataType.INT_FLAGS_2, ref_key="ePackFileMetaDataImapGroupType"),
            _arrayinfo(MetaDataType.HASH),
            _entry("WeatherTypes", 32, MetaDataType.ARRAY, ref_index=4),
            _entry("HoursOnOff", 48, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CImapDependency"),
        key=meta_name("CImapDependency_key"),
        unknown=256,
        structure_size=12,
        entries=[
            _entry("imapName", 0, MetaDataType.HASH),
            _entry("itypName", 4, MetaDataType.HASH),
            _entry("packFileName", 8, MetaDataType.HASH),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CImapDependencies"),
        key=meta_name("CImapDependencies_key"),
        unknown=256,
        structure_size=24,
        entries=[
            _entry("imapName", 0, MetaDataType.HASH),
            _entry("manifestFlags", 4, MetaDataType.INT_FLAGS_2, ref_key="manifestFlags"),
            _arrayinfo(MetaDataType.HASH),
            _entry("itypDepArray", 8, MetaDataType.ARRAY, ref_index=2),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CItypDependencies"),
        key=meta_name("CItypDependencies_key"),
        unknown=256,
        structure_size=24,
        entries=[
            _entry("itypName", 0, MetaDataType.HASH),
            _entry("manifestFlags", 4, MetaDataType.INT_FLAGS_2, ref_key="manifestFlags"),
            _arrayinfo(MetaDataType.HASH),
            _entry("itypDepArray", 8, MetaDataType.ARRAY, ref_index=2),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CInteriorBoundsFiles"),
        key=meta_name("CInteriorBoundsFiles_key"),
        unknown=256,
        structure_size=24,
        entries=[
            _entry("Name", 0, MetaDataType.HASH),
            _arrayinfo(MetaDataType.HASH),
            _entry("Bounds", 8, MetaDataType.ARRAY, ref_index=1),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CPackFileMetaData"),
        key=meta_name("CPackFileMetaData_key"),
        unknown=256,
        structure_size=96,
        entries=[
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CMapDataGroup"),
            _entry("MapDataGroups", 0, MetaDataType.ARRAY, ref_index=0),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CHDTxdAssetBinding"),
            _entry("HDTxdBindingArray", 16, MetaDataType.ARRAY, ref_index=2),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CImapDependency"),
            _entry("imapDependencies", 32, MetaDataType.ARRAY, ref_index=4),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CImapDependencies"),
            _entry("imapDependencies_2", 48, MetaDataType.ARRAY, ref_index=6),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CItypDependencies"),
            _entry("itypDependencies_2", 64, MetaDataType.ARRAY, ref_index=8),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CInteriorBoundsFiles"),
            _entry("Interiors", 80, MetaDataType.ARRAY, ref_index=10),
        ],
    ),
]
