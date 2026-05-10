from __future__ import annotations

import dataclasses
import struct
from collections.abc import Iterable

from ..meta.defs import META_NAME_REVERSE
from ..metahash import HashLike, MetaHash
from ..pso.model import (
    PsoDataTypeArray,
    PsoDataTypeEnum,
    PsoDataTypeFlags,
    PsoDataTypeString,
    PsoDataTypeStructure,
    PsoDataTypeUInt,
    PsoEntry,
    PsoStruct,
)
from ..pso.schema import serialize_psch
from ..pso.writer import PsoBlockBuilder, build_pmap_section, build_psin_section, encode_pointer_word
from .model import HdTxdAssetBinding, ImapDependencies, ImapDependency, InteriorBoundsFile, ItypDependencies, MapDataGroup, PackFileMetaData
from .utils import _hash_text


YMF_PSO_ROOT = 0x93A68A2F
YMF_PSO_MAP_DATA_GROUP = 0xC25B3923
YMF_PSO_HD_TXD_BINDING = 0x59869C63
YMF_PSO_IMAP_DEPENDENCY = 0xD0AD6E62
YMF_PSO_IMAP_DEPENDENCIES = 0xC11F3EE1
YMF_PSO_ITYP_DEPENDENCIES = 0x5A564E50
YMF_PSO_INTERIOR_BOUNDS = 0x2C325290

YMF_PSO_NAMES = {
    YMF_PSO_ROOT: "CPackFileMetaData",
    YMF_PSO_MAP_DATA_GROUP: "CMapDataGroup",
    YMF_PSO_HD_TXD_BINDING: "CHDTxdAssetBinding",
    YMF_PSO_IMAP_DEPENDENCY: "CImapDependency",
    YMF_PSO_IMAP_DEPENDENCIES: "CImapDependencies",
    YMF_PSO_ITYP_DEPENDENCIES: "CItypDependencies",
    YMF_PSO_INTERIOR_BOUNDS: "CInteriorBoundsFiles",
    0xB52CAE23: "MapDataGroups",
    0xF78AFB23: "HDTxdBindingArray",
    0x2BDA143F: "imapDependencies",
    0xDD4C5CCC: "imapDependencies_2",
    0xD2611C99: "itypDependencies_2",
    0x38767A8F: "Interiors",
    0x069004B2: "assetType",
    0x277DCAE0: "targetAsset",
    0x64DD3030: "HDTxd",
    0xACEC22BE: "Name",
    0xC496E4A8: "Bounds",
    0x4B621302: "Flags",
    0x977C7282: "WeatherTypes",
    0xF9CAC411: "HoursOnOff",
    0x31AF439F: "imapName",
    0xAC445064: "itypName",
    0xFB5297F9: "packFileName",
    0x6452A05B: "manifestFlags",
    0x8FB42AE6: "itypDepArray",
}

YMF_PSIG_SECTION = bytes.fromhex("50 53 49 47 00 00 00 14 A5 84 C5 93 2D F5 40 13 F5 EE C3 D0")

YMF_PSO_STRUCTS = {
    YMF_PSO_ROOT: PsoStruct(
        YMF_PSO_ROOT,
        96,
        [
            PsoEntry(0x100, PsoDataTypeStructure, 0, 0, YMF_PSO_MAP_DATA_GROUP),
            PsoEntry(0xB52CAE23, PsoDataTypeArray, 0, 0, 0),
            PsoEntry(0x100, PsoDataTypeStructure, 0, 0, YMF_PSO_HD_TXD_BINDING),
            PsoEntry(0xF78AFB23, PsoDataTypeArray, 0, 16, 2),
            PsoEntry(0x100, PsoDataTypeStructure, 0, 0, YMF_PSO_IMAP_DEPENDENCY),
            PsoEntry(0x2BDA143F, PsoDataTypeArray, 0, 32, 4),
            PsoEntry(0x100, PsoDataTypeStructure, 0, 0, YMF_PSO_IMAP_DEPENDENCIES),
            PsoEntry(0xDD4C5CCC, PsoDataTypeArray, 0, 48, 6),
            PsoEntry(0x100, PsoDataTypeStructure, 0, 0, YMF_PSO_ITYP_DEPENDENCIES),
            PsoEntry(0xD2611C99, PsoDataTypeArray, 0, 64, 8),
            PsoEntry(0x100, PsoDataTypeStructure, 0, 0, YMF_PSO_INTERIOR_BOUNDS),
            PsoEntry(0x38767A8F, PsoDataTypeArray, 0, 80, 10),
        ],
    ),
    YMF_PSO_MAP_DATA_GROUP: PsoStruct(
        YMF_PSO_MAP_DATA_GROUP,
        56,
        [
            PsoEntry(0xACEC22BE, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0x100, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0xC496E4A8, PsoDataTypeArray, 0, 8, 1),
            PsoEntry(0x100, PsoDataTypeEnum, 0, 0, 0x471BCA5B),
            PsoEntry(0x4B621302, PsoDataTypeFlags, 0, 24, 0x00200003),
            PsoEntry(0x100, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0x977C7282, PsoDataTypeArray, 0, 32, 5),
            PsoEntry(0xF9CAC411, PsoDataTypeUInt, 0, 48, 0),
        ],
    ),
    YMF_PSO_HD_TXD_BINDING: PsoStruct(
        YMF_PSO_HD_TXD_BINDING,
        132,
        [
            PsoEntry(0x069004B2, PsoDataTypeEnum, 0, 0, 0xC9E9A69A),
            PsoEntry(0x277DCAE0, PsoDataTypeString, 0, 4, 0x00400000),
            PsoEntry(0x64DD3030, PsoDataTypeString, 0, 68, 0x00400000),
        ],
    ),
    YMF_PSO_IMAP_DEPENDENCY: PsoStruct(
        YMF_PSO_IMAP_DEPENDENCY,
        12,
        [
            PsoEntry(0x31AF439F, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0xAC445064, PsoDataTypeString, 7, 4, 0),
            PsoEntry(0xFB5297F9, PsoDataTypeString, 7, 8, 0),
        ],
    ),
    YMF_PSO_IMAP_DEPENDENCIES: PsoStruct(
        YMF_PSO_IMAP_DEPENDENCIES,
        24,
        [
            PsoEntry(0x31AF439F, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0x100, PsoDataTypeEnum, 0, 0, 0x6452A05B),
            PsoEntry(0x6452A05B, PsoDataTypeFlags, 0, 4, 0x00200001),
            PsoEntry(0x100, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0x8FB42AE6, PsoDataTypeArray, 0, 8, 3),
        ],
    ),
    YMF_PSO_ITYP_DEPENDENCIES: PsoStruct(
        YMF_PSO_ITYP_DEPENDENCIES,
        24,
        [
            PsoEntry(0xAC445064, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0x100, PsoDataTypeEnum, 0, 0, 0x6452A05B),
            PsoEntry(0x6452A05B, PsoDataTypeFlags, 0, 4, 0x00200001),
            PsoEntry(0x100, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0x8FB42AE6, PsoDataTypeArray, 0, 8, 3),
        ],
    ),
    YMF_PSO_INTERIOR_BOUNDS: PsoStruct(
        YMF_PSO_INTERIOR_BOUNDS,
        24,
        [
            PsoEntry(0xACEC22BE, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0x100, PsoDataTypeString, 7, 0, 0),
            PsoEntry(0xC496E4A8, PsoDataTypeArray, 0, 8, 1),
        ],
    ),
}


def resolve_ymf_pso_name(hash_value: int) -> str:
    return YMF_PSO_NAMES.get(hash_value) or META_NAME_REVERSE.get(hash_value, f"hash_{hash_value:08X}")


@dataclasses.dataclass(slots=True)
class _PsoPayload:
    data: bytearray
    hash_arrays: list[tuple[int, list[MetaHash | HashLike]]] = dataclasses.field(default_factory=list)


def build_ymf_pso(manifest: PackFileMetaData) -> bytes:
    array_blocks: list[tuple[int, int, PsoBlockBuilder, int]] = []
    pending_hash_arrays: list[tuple[PsoBlockBuilder, int, list[MetaHash | HashLike]]] = []

    def add_struct_array(root_offset: int, type_hash: int, payloads: Iterable[_PsoPayload]) -> None:
        items = list(payloads)
        if not items:
            return
        block = PsoBlockBuilder(type_hash)
        for payload in items:
            relative_offset = block.append(payload.data)
            for field_offset, values in payload.hash_arrays:
                pending_hash_arrays.append((block, relative_offset + field_offset, values))
        array_blocks.append((root_offset, type_hash, block, len(items)))

    add_struct_array(0, YMF_PSO_MAP_DATA_GROUP, (_pack_pso_map_data_group(item) for item in manifest.map_data_groups))
    add_struct_array(16, YMF_PSO_HD_TXD_BINDING, (_pack_pso_hd_txd_binding(item) for item in manifest.hd_txd_bindings))
    add_struct_array(32, YMF_PSO_IMAP_DEPENDENCY, (_pack_pso_imap_dependency(item) for item in manifest.imap_dependencies))
    add_struct_array(48, YMF_PSO_IMAP_DEPENDENCIES, (_pack_pso_imap_dependencies(item, imap=True) for item in manifest.imap_dependencies_2))
    add_struct_array(64, YMF_PSO_ITYP_DEPENDENCIES, (_pack_pso_imap_dependencies(item, imap=False) for item in manifest.ityp_dependencies_2))
    add_struct_array(80, YMF_PSO_INTERIOR_BOUNDS, (_pack_pso_interior_bounds(item) for item in manifest.interiors))

    hash_array_blocks = [
        (owner, offset, PsoBlockBuilder(1, bytearray(_pso_hash_array(values))), len(values))
        for owner, offset, values in pending_hash_arrays
    ]

    root_block = PsoBlockBuilder(YMF_PSO_ROOT, bytearray(96))
    blocks = [root_block, *(block for _, _, block, _ in array_blocks), *(block for _, _, block, _ in hash_array_blocks)]
    block_ids_by_index = {id(block): index + 1 for index, block in enumerate(blocks)}
    block_ids = {block.name_hash: index + 1 for index, block in enumerate(blocks) if block.name_hash != 1}
    for root_offset, type_hash, _block, count in array_blocks:
        root_block.data[root_offset : root_offset + 16] = _pso_array_header(block_ids[type_hash], count)
    for owner, offset, block, count in hash_array_blocks:
        owner.data[offset : offset + 16] = _pso_array_header(block_ids_by_index[id(block)], count)

    used_structs = {YMF_PSO_ROOT: YMF_PSO_STRUCTS[YMF_PSO_ROOT]}
    for _root_offset, type_hash, _block, _count in array_blocks:
        if type_hash == 1:
            continue
        used_structs[type_hash] = YMF_PSO_STRUCTS[type_hash]

    return b"".join(
        [
            build_psin_section(blocks),
            build_pmap_section(blocks, root_block_id=1),
            serialize_psch(used_structs),
            YMF_PSIG_SECTION,
        ]
    )


def _pso_array_header(block_id: int, count: int) -> bytes:
    return struct.pack(">IIHHI", encode_pointer_word(block_id, 0), 0, count, count, 0)


def _pso_hash(value: MetaHash | HashLike) -> bytes:
    return struct.pack(">I", int(MetaHash.from_value(value)) & 0xFFFFFFFF)


def _pso_hash_array(values: Iterable[MetaHash | HashLike]) -> bytes:
    return b"".join(_pso_hash(value) for value in values)


def _pso_inline_string(value: MetaHash | HashLike, length: int = 64) -> bytes:
    text = _hash_text(value).encode("ascii", errors="ignore")[:length]
    return text + b"\x00" * (length - len(text))


def _pack_pso_map_data_group(item: MapDataGroup) -> _PsoPayload:
    output = bytearray(56)
    output[0:4] = _pso_hash(item.name)
    hash_arrays: list[tuple[int, list[MetaHash | HashLike]]] = []
    if item.bounds:
        hash_arrays.append((8, list(item.bounds)))
    output[24:28] = struct.pack(">i", int(item.flags))
    if item.weather_types:
        hash_arrays.append((32, list(item.weather_types)))
    output[48:52] = struct.pack(">I", int(item.hours_on_off) & 0xFFFFFFFF)
    return _PsoPayload(output, hash_arrays)


def _pack_pso_hd_txd_binding(item: HdTxdAssetBinding) -> _PsoPayload:
    output = bytearray(132)
    output[0:4] = struct.pack(">i", int(item.asset_type))
    output[4:68] = _pso_inline_string(item.target_asset)
    output[68:132] = _pso_inline_string(item.hd_txd)
    return _PsoPayload(output)


def _pack_pso_imap_dependency(item: ImapDependency) -> _PsoPayload:
    return _PsoPayload(bytearray(_pso_hash(item.imap_name) + _pso_hash(item.ityp_name) + _pso_hash(item.pack_file_name)))


def _pack_pso_imap_dependencies(item: ImapDependencies | ItypDependencies, *, imap: bool) -> _PsoPayload:
    output = bytearray(24)
    output[0:4] = _pso_hash(item.imap_name if imap else item.ityp_name)
    output[4:8] = struct.pack(">i", int(item.flags))
    hash_arrays: list[tuple[int, list[MetaHash | HashLike]]] = []
    if item.ityp_dependencies:
        hash_arrays.append((8, list(item.ityp_dependencies)))
    return _PsoPayload(output, hash_arrays)


def _pack_pso_interior_bounds(item: InteriorBoundsFile) -> _PsoPayload:
    output = bytearray(24)
    output[0:4] = _pso_hash(item.name)
    hash_arrays: list[tuple[int, list[MetaHash | HashLike]]] = []
    if item.bounds:
        hash_arrays.append((8, list(item.bounds)))
    return _PsoPayload(output, hash_arrays)
