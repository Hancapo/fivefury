from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..hashing import jenk_hash
from .model import CutFile, CutHashedString, CutNode
from .names import CUT_HASH_NAMES, CUT_NAME_VALUES
from .pso import (
    ARRAY_INFO_HASH,
    CHKS,
    PMAP,
    PSCH,
    PSIG,
    PSIN,
    STRE,
    PsoDataTypeArray,
    PsoDataTypeBool,
    PsoDataTypeEnum,
    PsoDataTypeFlags,
    PsoDataTypeFloat,
    PsoDataTypeFloat2,
    PsoDataTypeFloat3,
    PsoDataTypeFloat3a,
    PsoDataTypeFloat4,
    PsoDataTypeFloat4a,
    PsoDataTypeHFloat,
    PsoDataTypeLong,
    PsoDataTypeSByte,
    PsoDataTypeSInt,
    PsoDataTypeSShort,
    PsoDataTypeString,
    PsoDataTypeStructure,
    PsoDataTypeUByte,
    PsoDataTypeUInt,
    PsoDataTypeUShort,
    _PsoEntry,
    _PsoPointer,
    _PsoStruct,
)
from .schema import builtin_cut_template


def _u16(value: int) -> bytes:
    return int(value).to_bytes(2, "big", signed=False)


def _u32(value: int) -> bytes:
    return int(value & 0xFFFFFFFF).to_bytes(4, "big", signed=False)


def _i32(value: int) -> bytes:
    return int(value).to_bytes(4, "big", signed=True)


def _i64(value: int) -> bytes:
    return int(value).to_bytes(8, "big", signed=True)


def _f32(value: float) -> bytes:
    import struct

    return struct.pack(">f", float(value))


def _resolve_hash(value: int | str | CutHashedString | None) -> int:
    if value is None:
        return 0
    if isinstance(value, CutHashedString):
        return value.hash
    if isinstance(value, int):
        return value
    if value.startswith("hash_") and len(value) == 13:
        return int(value[5:], 16)
    if value in CUT_NAME_VALUES:
        return CUT_NAME_VALUES[value]
    return jenk_hash(value)


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, CutHashedString):
        return value.text or str(value)
    return str(value)


def _ensure_vector(value: Any, size: int) -> tuple[float, ...]:
    if isinstance(value, tuple) and len(value) == size:
        return tuple(float(v) for v in value)
    if isinstance(value, list) and len(value) == size:
        return tuple(float(v) for v in value)
    return tuple(0.0 for _ in range(size))


def _joaat_checksum(data: bytes) -> int:
    hash_value = 0x3FAC7125
    for byte in data:
        signed = byte if byte < 128 else byte - 256
        hash_value = (hash_value + signed) & 0xFFFFFFFF
        hash_value = (hash_value + ((hash_value << 10) & 0xFFFFFFFF)) & 0xFFFFFFFF
        hash_value ^= (hash_value >> 6)
    hash_value = (hash_value + ((hash_value << 3) & 0xFFFFFFFF)) & 0xFFFFFFFF
    hash_value ^= (hash_value >> 11)
    hash_value = (hash_value + ((hash_value << 15) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return hash_value


@dataclass(slots=True)
class _BlockBuilder:
    name_hash: int
    data: bytearray = field(default_factory=bytearray)

    def append(self, payload: bytes) -> int:
        offset = len(self.data)
        self.data.extend(payload)
        return offset


@dataclass(slots=True)
class _Patch:
    buffer: bytearray
    offset: int
    block_hash: int
    relative_offset: int


class _CutWriter:
    def __init__(self, cut: CutFile, template: dict[str, Any]):
        self.cut = cut
        self.template = template
        self.structs: dict[int, _PsoStruct] = template["structs"]
        self.root_type_hash: int = template["root_type_hash"]
        self.blocks: dict[int, _BlockBuilder] = {}
        self.patches: list[_Patch] = []

    def _get_block(self, name_hash: int) -> _BlockBuilder:
        block = self.blocks.get(name_hash)
        if block is None:
            block = _BlockBuilder(name_hash=name_hash)
            self.blocks[name_hash] = block
        return block

    def _encode_pointer_word(self, block_id: int, relative_offset: int) -> int:
        return ((relative_offset & 0xFFFFFFFF) << 12) | (block_id & 0xFFF)

    def _record_pointer_patch(self, buffer: bytearray, offset: int, block_hash: int, relative_offset: int) -> None:
        self.patches.append(_Patch(buffer=buffer, offset=offset, block_hash=block_hash, relative_offset=relative_offset))

    def _alloc_string(self, value: str) -> tuple[int, int]:
        payload = value.encode("utf-8") + b"\x00"
        block = self._get_block(PsoDataTypeSByte)
        return block.name_hash, block.append(payload)

    def _alloc_primitive_array(self, type_id: int, values: list[Any]) -> tuple[int, int]:
        payload = bytearray()
        if type_id == PsoDataTypeSInt:
            for value in values:
                payload.extend(_i32(int(value)))
        elif type_id == PsoDataTypeUInt:
            for value in values:
                payload.extend(_u32(int(value)))
        elif type_id == PsoDataTypeUShort:
            for value in values:
                payload.extend(_u16(int(value)))
        elif type_id == PsoDataTypeUByte:
            payload.extend(int(value) & 0xFF for value in values)
        elif type_id == PsoDataTypeBool:
            payload.extend(1 if value else 0 for value in values)
        elif type_id == PsoDataTypeFloat:
            for value in values:
                payload.extend(_f32(float(value)))
        elif type_id == PsoDataTypeFloat2:
            for value in values:
                x, y = _ensure_vector(value, 2)
                payload.extend(_f32(x))
                payload.extend(_f32(y))
        elif type_id in {PsoDataTypeFloat3, PsoDataTypeFloat3a}:
            for value in values:
                x, y, z = _ensure_vector(value, 3)
                payload.extend(_f32(x))
                payload.extend(_f32(y))
                payload.extend(_f32(z))
                if type_id == PsoDataTypeFloat3:
                    payload.extend(b"\x00\x00\x00\x00")
        elif type_id in {PsoDataTypeFloat4, PsoDataTypeFloat4a}:
            for value in values:
                x, y, z, w = _ensure_vector(value, 4)
                payload.extend(_f32(x))
                payload.extend(_f32(y))
                payload.extend(_f32(z))
                payload.extend(_f32(w))
        else:
            raise ValueError(f"unsupported primitive array type {type_id}")
        block = self._get_block(type_id)
        return block.name_hash, block.append(bytes(payload))

    def _write_scalar(self, buffer: bytearray, offset: int, type_id: int, value: Any) -> None:
        if type_id == PsoDataTypeBool:
            buffer[offset] = 1 if bool(value) else 0
        elif type_id == PsoDataTypeSByte:
            buffer[offset : offset + 1] = int(value or 0).to_bytes(1, "big", signed=True)
        elif type_id == PsoDataTypeUByte:
            buffer[offset] = int(value or 0) & 0xFF
        elif type_id == PsoDataTypeSShort:
            buffer[offset : offset + 2] = int(value or 0).to_bytes(2, "big", signed=True)
        elif type_id == PsoDataTypeUShort:
            buffer[offset : offset + 2] = _u16(int(value or 0))
        elif type_id in {PsoDataTypeSInt, PsoDataTypeEnum, PsoDataTypeFlags}:
            buffer[offset : offset + 4] = _i32(int(value or 0))
        elif type_id == PsoDataTypeUInt:
            buffer[offset : offset + 4] = _u32(int(value or 0))
        elif type_id == PsoDataTypeFloat:
            buffer[offset : offset + 4] = _f32(float(value or 0.0))
        elif type_id == PsoDataTypeFloat2:
            x, y = _ensure_vector(value, 2)
            buffer[offset : offset + 8] = _f32(x) + _f32(y)
        elif type_id in {PsoDataTypeFloat3, PsoDataTypeFloat3a}:
            x, y, z = _ensure_vector(value, 3)
            payload = _f32(x) + _f32(y) + _f32(z)
            if type_id == PsoDataTypeFloat3:
                payload += b"\x00\x00\x00\x00"
            buffer[offset : offset + len(payload)] = payload
        elif type_id in {PsoDataTypeFloat4, PsoDataTypeFloat4a}:
            x, y, z, w = _ensure_vector(value, 4)
            buffer[offset : offset + 16] = _f32(x) + _f32(y) + _f32(z) + _f32(w)
        elif type_id == PsoDataTypeHFloat:
            buffer[offset : offset + 2] = _u16(int(value or 0))
        elif type_id == PsoDataTypeLong:
            buffer[offset : offset + 8] = _i64(int(value or 0))
        else:
            raise ValueError(f"unsupported scalar type {type_id}")

    def _write_string(self, buffer: bytearray, offset: int, entry: _PsoEntry, value: Any) -> None:
        if entry.subtype == 0:
            length = (entry.reference_key >> 16) & 0xFFFF
            text = "" if value is None else str(value)
            payload = text.encode("utf-8")[: max(0, length - 1)] + b"\x00"
            payload = payload.ljust(length, b"\x00")
            buffer[offset : offset + length] = payload
            return
        if entry.subtype in {1, 2}:
            if value is None or value == "":
                return
            _, rel = self._alloc_string(_string_value(value))
            self._record_pointer_patch(buffer, offset, PsoDataTypeSByte, rel)
            return
        if entry.subtype == 3:
            if value is None or value == "":
                return
            text_value = _string_value(value)
            block_hash, rel = self._alloc_string(text_value)
            self._record_pointer_patch(buffer, offset, block_hash, rel)
            count = len(text_value.encode("utf-8")) + 1
            buffer[offset + 8 : offset + 10] = _u16(count)
            buffer[offset + 10 : offset + 12] = _u16(count)
            return
        if entry.subtype in {7, 8}:
            buffer[offset : offset + 4] = _u32(_resolve_hash(value))
            return
        raise ValueError(f"unsupported string subtype {entry.subtype}")

    def _coerce_node(self, value: Any, fallback_type_hash: int) -> CutNode:
        if isinstance(value, CutNode):
            return value
        if isinstance(value, dict):
            return CutNode(type_name=f"hash_{fallback_type_hash:08X}", type_hash=fallback_type_hash, fields=dict(value))
        raise TypeError(f"expected CutNode or dict, got {type(value)!r}")

    def _write_inline_structure(self, struct_hash: int, value: Any) -> bytes:
        node = self._coerce_node(value or {}, struct_hash)
        return self._serialize_structure(struct_hash, node)

    def _alloc_structure(self, struct_hash: int, value: Any) -> tuple[int, int]:
        node = self._coerce_node(value or {}, struct_hash)
        patch_start = len(self.patches)
        payload = self._serialize_structure(struct_hash, node)
        block = self._get_block(struct_hash)
        rel = block.append(payload)
        for patch in self.patches[patch_start:]:
            if patch.buffer is payload:
                patch.buffer = block.data
                patch.offset += rel
        return block.name_hash, rel

    def _write_external_array_header(self, buffer: bytearray, offset: int, block_hash: int, relative_offset: int, count: int) -> None:
        self._record_pointer_patch(buffer, offset, block_hash, relative_offset)
        buffer[offset + 8 : offset + 10] = _u16(count)
        buffer[offset + 10 : offset + 12] = _u16(count)

    def _write_array(self, buffer: bytearray, offset: int, entry: _PsoEntry, array_info: _PsoEntry | None, value: Any) -> None:
        values = list(value or [])
        if array_info is None:
            return
        if entry.subtype in {1, 2}:
            capacity = (entry.reference_key >> 16) & 0xFFFF
            values = values[:capacity]
            if array_info.type_id == PsoDataTypeStructure and array_info.reference_key != 0:
                struct_info = self.structs[array_info.reference_key]
                stride = struct_info.length
                for index in range(capacity):
                    chunk = self._write_inline_structure(array_info.reference_key, values[index] if index < len(values) else {})
                    start = offset + index * stride
                    buffer[start : start + stride] = chunk
                return
            raise ValueError("unsupported inline array shape")

        if not values:
            return

        if array_info.type_id == PsoDataTypeStructure:
            if array_info.reference_key != 0:
                block_hash = array_info.reference_key
                first_rel: int | None = None
                for item in values:
                    _, rel = self._alloc_structure(block_hash, item)
                    if first_rel is None:
                        first_rel = rel
                self._write_external_array_header(buffer, offset, block_hash, first_rel or 0, len(values))
                return

            pointer_payload = bytearray()
            pointer_patch_specs: list[tuple[int, int, int]] = []
            for item in values:
                node = self._coerce_node(item, 0)
                type_hash = node.type_hash or CUT_NAME_VALUES.get(node.type_name)
                if type_hash is None:
                    raise ValueError(f"missing type hash for cut node {node.type_name!r}")
                _, rel = self._alloc_structure(type_hash, node)
                pointer_payload.extend(_u32(0))
                pointer_payload.extend(b"\x00\x00\x00\x00")
                pointer_patch_specs.append((len(pointer_payload) - 8, type_hash, rel))
            pointer_block = self._get_block(PsoDataTypeStructure)
            pointer_rel = pointer_block.append(bytes(pointer_payload))
            for patch_offset, type_hash, rel in pointer_patch_specs:
                self.patches.append(_Patch(pointer_block.data, pointer_rel + patch_offset, type_hash, rel))
            self._write_external_array_header(buffer, offset, PsoDataTypeStructure, pointer_rel, len(values))
            return

        if array_info.type_id == PsoDataTypeString:
            if array_info.subtype in {7, 8}:
                block_hash, rel = self._alloc_primitive_array(PsoDataTypeUInt, [_resolve_hash(item) for item in values])
                self._write_external_array_header(buffer, offset, block_hash, rel, len(values))
                return
            raise ValueError("unsupported string array subtype")

        block_hash, rel = self._alloc_primitive_array(array_info.type_id, values)
        self._write_external_array_header(buffer, offset, block_hash, rel, len(values))

    def _serialize_structure(self, type_hash: int, node: CutNode) -> bytearray:
        struct_info = self.structs[type_hash]
        buffer = bytearray(struct_info.length)
        array_info: _PsoEntry | None = None
        for entry in struct_info.entries:
            if entry.name_hash == ARRAY_INFO_HASH:
                array_info = entry
                continue
            value = node.fields.get(CUT_HASH_NAMES.get(entry.name_hash, f"hash_{entry.name_hash:08X}"))
            if value is None:
                value = node.fields.get(f"hash_{entry.name_hash:08X}")
            offset = entry.data_offset
            if entry.type_id == PsoDataTypeString:
                self._write_string(buffer, offset, entry, value)
            elif entry.type_id == PsoDataTypeStructure:
                if entry.subtype == 0:
                    child = self._write_inline_structure(entry.reference_key, value)
                    buffer[offset : offset + len(child)] = child
                elif entry.subtype in {3, 4}:
                    if value is None:
                        continue
                    block_hash, rel = self._alloc_structure(entry.reference_key, value)
                    self._record_pointer_patch(buffer, offset, block_hash, rel)
                else:
                    raise ValueError(f"unsupported structure subtype {entry.subtype}")
            elif entry.type_id == PsoDataTypeArray:
                self._write_array(buffer, offset, entry, array_info, value)
            else:
                self._write_scalar(buffer, offset, entry.type_id, value)
        return buffer

    def _ordered_blocks(self) -> list[_BlockBuilder]:
        preferred = list(self.template.get("block_order_hashes", []))
        ordered_hashes: list[int] = []
        for name_hash in preferred:
            if name_hash in self.blocks and name_hash not in ordered_hashes:
                ordered_hashes.append(name_hash)
        for name_hash in self.blocks:
            if name_hash not in ordered_hashes:
                ordered_hashes.append(name_hash)
        return [self.blocks[name_hash] for name_hash in ordered_hashes]

    def build(self) -> bytes:
        _, root_rel = self._alloc_structure(self.root_type_hash, self.cut.root)
        ordered_blocks = self._ordered_blocks()
        block_ids = {block.name_hash: index + 1 for index, block in enumerate(ordered_blocks)}

        psin_body = bytearray(self.template.get("psin_prefix", b"\x70" * 8))
        while len(psin_body) < 8:
            psin_body.append(0x70)

        pmap_entries: list[tuple[int, int, int, int]] = []
        current_offset = 16
        for block in ordered_blocks:
            pmap_entries.append((block.name_hash, current_offset, 0, len(block.data)))
            current_offset += len(block.data)

        for patch in self.patches:
            block_id = block_ids[patch.block_hash]
            patch.buffer[patch.offset : patch.offset + 4] = _u32(self._encode_pointer_word(block_id, patch.relative_offset))

        psin = bytearray()
        psin.extend(b"PSIN")
        psin.extend(_u32(16 + sum(len(block.data) for block in ordered_blocks)))
        psin.extend(psin_body[:8])
        for block in ordered_blocks:
            psin.extend(block.data)

        root_block_id = block_ids[self.root_type_hash]
        pmap = bytearray()
        pmap.extend(b"PMAP")
        pmap.extend(_u32(16 + len(pmap_entries) * 16))
        pmap.extend(_i32(root_block_id))
        pmap.extend(_u16(len(pmap_entries)))
        pmap.extend(_u16(int(self.template.get("pmap_unknown", 0x7070))))
        for name_hash, offset, unknown, length in pmap_entries:
            pmap.extend(_u32(name_hash))
            pmap.extend(_i32(offset))
            pmap.extend(_i32(unknown))
            pmap.extend(_i32(length))

        sections = [bytes(psin), bytes(pmap)]
        template_sections: dict[int, bytes] = self.template["sections"]
        for ident in (PSCH, PSIG, STRE):
            section = template_sections.get(ident)
            if section is not None:
                sections.append(section)

        chks = bytearray()
        chks.extend(b"CHKS")
        chks.extend(_u32(20))
        chks.extend(b"\x00\x00\x00\x00")
        chks.extend(b"\x00\x00\x00\x00")
        template_chks = template_sections.get(CHKS)
        chks.extend(template_chks[16:20] if template_chks is not None and len(template_chks) >= 20 else _u32(0x79707070))
        sections.append(bytes(chks))

        file_data = bytearray().join(sections)
        file_size = len(file_data)
        file_data[-12:-8] = _u32(0)
        file_data[-8:-4] = _u32(0)
        checksum = _joaat_checksum(file_data)
        file_data[-12:-8] = _u32(file_size)
        file_data[-8:-4] = _u32(checksum)
        return bytes(file_data)


def _resolve_template(template: CutFile | bytes | str | Path | None, cut: CutFile) -> dict[str, Any]:
    if template is None:
        resolved = cut.metadata.get("pso_template")
        if resolved is not None:
            return resolved
        return builtin_cut_template()
    if isinstance(template, CutFile):
        resolved = template.metadata.get("pso_template")
        if resolved is None:
            raise ValueError("template CutFile has no PSO metadata; load it from a .cut first")
        return resolved
    from .pso import read_cut

    return _resolve_template(read_cut(template), cut)


def build_cut_bytes(cut: CutFile, *, template: CutFile | bytes | str | Path | None = None) -> bytes:
    resolved_template = _resolve_template(template, cut)
    return _CutWriter(cut, resolved_template).build()


def save_cut(
    cut: CutFile,
    destination: str | Path,
    *,
    template: CutFile | bytes | str | Path | None = None,
) -> Path:
    target = Path(destination)
    target.write_bytes(build_cut_bytes(cut, template=template))
    return target
