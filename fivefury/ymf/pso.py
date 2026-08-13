from __future__ import annotations

import dataclasses
import struct
from collections.abc import Iterable, Mapping
from typing import Any

from ..meta.defs import META_NAME_REVERSE
from ..metahash import HashLike, MetaHash
from ..pso.codec import (
    decode_array_header,
    parse_pmap,
    parse_psch_enums,
    parse_sections,
)
from ..pso.model import (
    CHKS,
    PMAP,
    PSCH,
    PSIG,
    PSIN,
    PsoDataTypeArray,
    PsoDataTypeEnum,
    PsoDataTypeFlags,
    PsoDataTypeString,
    PsoDataTypeStructure,
    PsoDataTypeUInt,
    PsoEntry,
    PsoEnum,
    PsoEnumEntry,
    PsoStruct,
)
from ..pso.schema import serialize_psch
from ..pso.writer import (
    PsoBlockBuilder,
    build_chks_section,
    build_pmap_section,
    build_psin_section,
    encode_pointer_word,
    finalize_sections_with_checksum,
)
from .model import (
    HdTxdAssetBinding,
    ImapDependencies,
    ImapDependency,
    InteriorBoundsFile,
    ItypDependencies,
    MapDataGroup,
    PackFileMetaData,
)
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

YMF_PSO_ENUMS = {
    0x471BCA5B: PsoEnum(
        0x471BCA5B,
        [PsoEnumEntry(0xB493A9DC, 0), PsoEnumEntry(0x0C968CFB, 1)],
    ),
    0xC9E9A69A: PsoEnum(
        0xC9E9A69A,
        [
            PsoEnumEntry(0xE6B7EB79, 0),
            PsoEnumEntry(0x74980D3B, 1),
            PsoEnumEntry(0x1C43E8EC, 2),
            PsoEnumEntry(0xAB34CAAD, 3),
        ],
    ),
    0x6452A05B: PsoEnum(
        0x6452A05B,
        [PsoEnumEntry(0x21569096, 0)],
    ),
}


def resolve_ymf_pso_name(hash_value: int) -> str:
    return YMF_PSO_NAMES.get(hash_value) or META_NAME_REVERSE.get(
        hash_value, f"hash_{hash_value:08X}"
    )


@dataclasses.dataclass(slots=True)
class _PsoPayload:
    data: bytearray
    hash_arrays: list[tuple[int, list[MetaHash | HashLike]]] = dataclasses.field(
        default_factory=list
    )


def build_ymf_pso(
    manifest: PackFileMetaData,
    template: Mapping[str, Any] | None = None,
) -> bytes:
    array_blocks: list[tuple[int, int, PsoBlockBuilder, int]] = []
    pending_hash_arrays: list[
        tuple[PsoBlockBuilder, int, list[MetaHash | HashLike]]
    ] = []

    def struct_array(
        root_offset: int, type_hash: int, payloads: Iterable[_PsoPayload]
    ) -> None:
        items = list(payloads)
        if not items:
            return
        block = PsoBlockBuilder(type_hash)
        for payload in items:
            relative_offset = block.append(payload.data)
            for field_offset, values in payload.hash_arrays:
                pending_hash_arrays.append(
                    (block, relative_offset + field_offset, values)
                )
        array_blocks.append((root_offset, type_hash, block, len(items)))

    struct_array(
        0,
        YMF_PSO_MAP_DATA_GROUP,
        (_pack_pso_map_data_group(item) for item in manifest.map_data_groups),
    )
    struct_array(
        16,
        YMF_PSO_HD_TXD_BINDING,
        (_pack_pso_hd_txd_binding(item) for item in manifest.hd_txd_bindings),
    )
    struct_array(
        32,
        YMF_PSO_IMAP_DEPENDENCY,
        (_pack_pso_imap_dependency(item) for item in manifest.imap_dependencies),
    )
    struct_array(
        48,
        YMF_PSO_IMAP_DEPENDENCIES,
        (
            _pack_pso_imap_dependencies(item, imap=True)
            for item in manifest.imap_dependencies_2
        ),
    )
    struct_array(
        64,
        YMF_PSO_ITYP_DEPENDENCIES,
        (
            _pack_pso_imap_dependencies(item, imap=False)
            for item in manifest.ityp_dependencies_2
        ),
    )
    struct_array(
        80,
        YMF_PSO_INTERIOR_BOUNDS,
        (_pack_pso_interior_bounds(item) for item in manifest.interiors),
    )

    hash_block = PsoBlockBuilder(PsoDataTypeUInt)
    hash_array_offsets: list[tuple[PsoBlockBuilder, int, int, int]] = []
    for owner, owner_offset, values in pending_hash_arrays:
        relative_offset = hash_block.append(_pso_hash_array(values))
        hash_array_offsets.append((owner, owner_offset, relative_offset, len(values)))

    root_block = PsoBlockBuilder(YMF_PSO_ROOT, bytearray(96))
    blocks = [
        *([hash_block] if hash_block.data else []),
        *(block for _, _, block, _ in array_blocks),
        root_block,
    ]
    block_ids = {block.name_hash: index + 1 for index, block in enumerate(blocks)}
    for root_offset, type_hash, _block, count in array_blocks:
        root_block.data[root_offset : root_offset + 16] = _pso_array_header(
            block_ids[type_hash], count
        )
    for owner, owner_offset, relative_offset, count in hash_array_offsets:
        owner.data[owner_offset : owner_offset + 16] = _pso_array_header(
            block_ids[PsoDataTypeUInt],
            count,
            relative_offset=relative_offset,
        )

    used_structs: dict[int, PsoStruct] = {}
    for _root_offset, type_hash, _block, _count in array_blocks:
        used_structs[type_hash] = YMF_PSO_STRUCTS[type_hash]
    used_structs[YMF_PSO_ROOT] = YMF_PSO_STRUCTS[YMF_PSO_ROOT]
    used_enum_hashes = {
        entry.reference_key
        for struct_info in used_structs.values()
        for entry in struct_info.entries
        if entry.type_id == PsoDataTypeEnum and entry.reference_key in YMF_PSO_ENUMS
    }
    used_enums = {
        enum_hash: enum_info
        for enum_hash, enum_info in YMF_PSO_ENUMS.items()
        if enum_hash in used_enum_hashes
    }
    if template is not None:
        for type_hash, struct_info in template.get("structs", {}).items():
            if type_hash not in YMF_PSO_STRUCTS:
                used_structs.setdefault(type_hash, struct_info)
        for enum_hash, enum_info in template.get("enums", {}).items():
            if enum_hash not in YMF_PSO_ENUMS:
                used_enums.setdefault(enum_hash, enum_info)
    root_block_id = block_ids[YMF_PSO_ROOT]

    sections = [
        build_psin_section(blocks, prefix=b"\x00" * 8, block_alignment=1),
        build_pmap_section(blocks, root_block_id=root_block_id, block_alignment=1),
        serialize_psch(used_structs, used_enums),
    ]
    template_sections: Mapping[int, bytes] = (
        template.get("sections", {}) if template is not None else {}
    )
    for ident, section in template_sections.items():
        if ident not in {PSIN, PMAP, PSCH, PSIG, CHKS}:
            sections.append(bytes(section))
    if CHKS in template_sections:
        sections.append(build_chks_section(template_sections[CHKS]))
        output = finalize_sections_with_checksum(sections)
    else:
        output = b"".join(sections)

    issues = validate_ymf_pso_layout(output)
    if issues:
        raise ValueError("Invalid generated YMF PSO:\n- " + "\n- ".join(issues))
    return output


_ROOT_ARRAY_FIELDS = (
    (0, YMF_PSO_MAP_DATA_GROUP),
    (16, YMF_PSO_HD_TXD_BINDING),
    (32, YMF_PSO_IMAP_DEPENDENCY),
    (48, YMF_PSO_IMAP_DEPENDENCIES),
    (64, YMF_PSO_ITYP_DEPENDENCIES),
    (80, YMF_PSO_INTERIOR_BOUNDS),
)

_HASH_ARRAY_FIELDS = {
    YMF_PSO_MAP_DATA_GROUP: (8, 32),
    YMF_PSO_IMAP_DEPENDENCIES: (8,),
    YMF_PSO_ITYP_DEPENDENCIES: (8,),
    YMF_PSO_INTERIOR_BOUNDS: (8,),
}


def _validate_array_pointer(
    *,
    psin: bytes,
    blocks: Mapping[int, Any],
    owner_offset: int,
    field_offset: int,
    expected_type: int,
    stride: int,
    label: str,
) -> list[str]:
    header = decode_array_header(psin, owner_offset + field_offset)
    if header.count == 0:
        return [] if header.pointer.is_null else [f"{label} has a pointer with a zero count"]
    target = blocks.get(header.pointer.block_id)
    if target is None:
        return [f"{label} references missing block {header.pointer.block_id}"]
    issues: list[str] = []
    if target.name_hash != expected_type:
        issues.append(
            f"{label} references block type 0x{target.name_hash:08X}, expected 0x{expected_type:08X}"
        )
    end = header.pointer.offset + header.count * stride
    if header.pointer.offset < 0 or end > target.length:
        issues.append(
            f"{label} range {header.pointer.offset}:{end} exceeds block length {target.length}"
        )
    return issues


def validate_ymf_pso_layout(data: bytes) -> list[str]:
    try:
        sections = parse_sections(data)
        psin = sections[PSIN]
        blocks, root_block_id = parse_pmap(sections[PMAP])
        psch = sections[PSCH]
    except (KeyError, ValueError, IndexError, struct.error) as exc:
        return [f"invalid PSO structure: {exc}"]

    issues: list[str] = []
    if psin[8:16] != b"\x00" * 8:
        issues.append("PSIN must use the eight-byte zero prefix")
    if PSIG in sections:
        issues.append("PSIG is not valid for the runtime YMF profile")
    root_block = blocks.get(root_block_id)
    if root_block is None:
        issues.append(f"PMAP root block {root_block_id} does not exist")
        return issues
    if root_block.name_hash != YMF_PSO_ROOT:
        issues.append(f"PMAP root type is 0x{root_block.name_hash:08X}, expected 0x{YMF_PSO_ROOT:08X}")
    if root_block_id != len(blocks):
        issues.append("the YMF root must be the final PMAP block")
    if root_block.length != YMF_PSO_STRUCTS[YMF_PSO_ROOT].length:
        issues.append(f"YMF root length is {root_block.length}, expected 96")
    if any(block.name_hash == 1 for block in blocks.values()):
        issues.append("anonymous PSO blocks are not valid for YMF hash arrays")
    hash_blocks = [block for block in blocks.values() if block.name_hash == PsoDataTypeUInt]
    if len(hash_blocks) > 1:
        issues.append("YMF hash arrays must share one UInt block")

    for field_offset, expected_type in _ROOT_ARRAY_FIELDS:
        issues.extend(
            _validate_array_pointer(
                psin=psin,
                blocks=blocks,
                owner_offset=root_block.offset,
                field_offset=field_offset,
                expected_type=expected_type,
                stride=YMF_PSO_STRUCTS[expected_type].length,
                label=f"root array at 0x{field_offset:X}",
            )
        )

    present_types = {block.name_hash for block in blocks.values()}
    for block_id, block in blocks.items():
        field_offsets = _HASH_ARRAY_FIELDS.get(block.name_hash)
        if field_offsets is None:
            continue
        stride = YMF_PSO_STRUCTS[block.name_hash].length
        if block.length % stride:
            issues.append(
                f"block {block_id} length {block.length} is not aligned to structure size {stride}"
            )
            continue
        for item_offset in range(0, block.length, stride):
            for field_offset in field_offsets:
                issues.extend(
                    _validate_array_pointer(
                        psin=psin,
                        blocks=blocks,
                        owner_offset=block.offset + item_offset,
                        field_offset=field_offset,
                        expected_type=PsoDataTypeUInt,
                        stride=4,
                        label=f"block {block_id} item {item_offset // stride} hash array at 0x{field_offset:X}",
                    )
                )

    enums = parse_psch_enums(psch)
    required_enums = {
        entry.reference_key
        for type_hash in present_types
        for entry in YMF_PSO_STRUCTS.get(type_hash, PsoStruct(0, 0, [])).entries
        if entry.type_id == PsoDataTypeEnum and entry.reference_key in YMF_PSO_ENUMS
    }
    missing_enums = required_enums.difference(enums)
    for enum_hash in sorted(missing_enums):
        issues.append(f"PSCH is missing enum 0x{enum_hash:08X}")
    return issues


def _pso_array_header(block_id: int, count: int, *, relative_offset: int = 0) -> bytes:
    return struct.pack(
        ">IIHHI", encode_pointer_word(block_id, relative_offset), 0, count, count, 0
    )


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
    return _PsoPayload(
        bytearray(
            _pso_hash(item.imap_name)
            + _pso_hash(item.ityp_name)
            + _pso_hash(item.pack_file_name)
        )
    )


def _pack_pso_imap_dependencies(
    item: ImapDependencies | ItypDependencies, *, imap: bool
) -> _PsoPayload:
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
