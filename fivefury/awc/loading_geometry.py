"""Inspect physical mono stream spans without decoding audio or assuming a pool.

The caller supplies alignment and capacity for its qualified loading path.
This is not a prediction of total GPU/RAM consumption or streaming block use.
"""
import struct
from .constants import chunk_alignment


def compact_mono_payloads(data: bytes) -> bytes:
    """Relocate opaque mono chunks without parsing/re-encoding codec payloads.

    This is useful for retail codec variants not supported by the authoring
    validator. It certifies byte preservation, not codec validity or a budget.
    Whole-file encryption and streaming banks are intentionally unsupported.
    """
    geometry = inspect_loading_geometry(data, len(data), alignment=1)
    if geometry['multichannel']:
        raise ValueError('Opaque compaction supports only mono banks')
    endian = '<' if data[:4] == b'ADAT' else '>'
    _, _, flags, count, end = struct.unpack_from(endian+'4sHHII', data)
    first = 16 + (2*count if flags & 1 else 0)
    cursor = first + 4*count
    result = bytearray(data[:end])
    for index in range(count):
        info = struct.unpack_from(endian+'I',data,first+index*4)[0]
        for _ in range(info >> 29):
            packed = struct.unpack_from(endian+'Q',data,cursor)[0]
            old, size, tag = packed & 0xfffffff, (packed >> 28) & 0xfffffff, packed >> 56
            alignment = chunk_alignment(tag)
            if alignment:
                result.extend(bytes(-len(result) % alignment))
            offset = len(result)
            if offset > 0xfffffff:
                raise ValueError('Compacted offset exceeds AWC field')
            result.extend(data[old:old+size])
            struct.pack_into(endian+'Q',result,cursor,offset | (size << 28) | (tag << 56))
            cursor += 8
    return bytes(result)


def inspect_loading_geometry(header: bytes, file_size: int, *, alignment: int,
                             budget_bytes: int | None = None) -> dict:
    if type(file_size) is not int or file_size < 16:
        raise ValueError('File size must be an integer containing an AWC header')
    if type(alignment) is not int or alignment <= 0:
        raise ValueError('Alignment must be a positive integer')
    if budget_bytes is not None and (type(budget_bytes) is not int or budget_bytes <= 0):
        raise ValueError('Budget must be a positive integer or None')
    if len(header) < 16:
        raise ValueError('Truncated AWC header')
    endian = {b'ADAT': '<', b'TADA': '>'}.get(bytes(header[:4]))
    if endian is None:
        raise ValueError('Encrypted or unknown header; decrypt before inspection')
    _, version, flags, count, end = struct.unpack_from(endian + '4sHHII', header)
    if version != 1 or not 16 <= end <= file_size or end > len(header):
        raise ValueError('Invalid or incomplete header')
    first = 16 + (2 * count if flags & 1 else 0)
    cursor = first + count * 4
    if cursor > end:
        raise ValueError('Truncated stream table')
    overhead = end + (-end % alignment)
    rows = []
    for index in range(count):
        info = struct.unpack_from(endian + 'I', header, first + index * 4)[0]
        chunks = []
        for _ in range(info >> 29):
            if cursor + 8 > end:
                raise ValueError('Truncated chunk table')
            raw = struct.unpack_from(endian + 'Q', header, cursor)[0]
            cursor += 8
            offset, size = raw & 0xfffffff, (raw >> 28) & 0xfffffff
            if offset + size > file_size or (size and offset < end):
                raise ValueError('Chunk outside payload')
            if size:
                chunks.append((offset, offset + size))
        span = max(b for _, b in chunks) - min(a for a, _ in chunks) if chunks else 0
        # Formula is intentionally explicit. Streaming banks are not judged
        # against a mono-entry budget even when their tables can be parsed.
        required = overhead + span if chunks and not flags & 4 else None
        rows.append(dict(index=index, stream_id=f'{info & 0x1fffffff:08X}',
                         span_bytes=span, required_bytes=required,
                         exceeds_budget=(required > budget_bytes
                             if required is not None and budget_bytes is not None else None)))
    if cursor != end:
        raise ValueError('Header size differs from parsed tables')
    return dict(flags=flags, multichannel=bool(flags & 4), header_bytes=end,
                aligned_header_bytes=overhead, alignment=alignment,
                budget_bytes=budget_bytes, streams=rows,
                budget_qualified=budget_bytes is not None and not flags & 4)
