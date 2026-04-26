from __future__ import annotations

import struct
from pathlib import Path

from .constants import (
    AWC_CHUNK_FIELD_MASK,
    AWC_MAGIC_BE,
    AWC_MAGIC_LE,
    AWC_STREAM_ID_MASK,
    AwcChunkType,
)
from .crypto import decrypt_awc_rsxxtea, encrypt_awc_rsxxtea
from .structures import Awc, AwcChunk, AwcChunkInfo, AwcStream


def read_awc(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    path: str | Path | None = None,
    decrypt: bool = True,
    awc_key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None = None,
) -> Awc:
    if isinstance(source, (str, Path)):
        source_path = Path(source)
        data = source_path.read_bytes()
        if path is None:
            path = source_path
    else:
        data = bytes(source)

    if len(data) < 16:
        raise ValueError("AWC data is too small")

    whole_file_encrypted = False
    magic_le = struct.unpack_from("<I", data, 0)[0]
    if magic_le == AWC_MAGIC_LE:
        endian = "<"
    elif magic_le == AWC_MAGIC_BE:
        endian = ">"
    else:
        if not decrypt or len(data) % 4:
            raise ValueError(f"Invalid AWC magic 0x{magic_le:08X}")
        data = decrypt_awc_rsxxtea(data, awc_key)
        whole_file_encrypted = True
        magic_le = struct.unpack_from("<I", data, 0)[0]
        if magic_le == AWC_MAGIC_LE:
            endian = "<"
        elif magic_le == AWC_MAGIC_BE:
            endian = ">"
        else:
            raise ValueError(f"Invalid AWC magic 0x{magic_le:08X} after whole-file decryption")

    magic, version, flags, stream_count, data_offset = struct.unpack_from(f"{endian}IHHii", data, 0)
    if stream_count < 0:
        raise ValueError("AWC stream count is negative")

    offset = 16
    chunk_indices: list[int] = []
    if flags & 1:
        table_size = stream_count * 2
        if offset + table_size > len(data):
            raise ValueError("AWC chunk index table is truncated")
        chunk_indices = list(struct.unpack_from(f"{endian}{stream_count}H", data, offset)) if stream_count else []
        offset += table_size

    stream_infos: list[tuple[int, int]] = []
    if offset + (stream_count * 4) > len(data):
        raise ValueError("AWC stream info table is truncated")
    for _ in range(stream_count):
        raw = struct.unpack_from(f"{endian}I", data, offset)[0]
        stream_infos.append((raw & AWC_STREAM_ID_MASK, raw >> 29))
        offset += 4

    total_chunks = sum(chunk_count for _, chunk_count in stream_infos)
    if offset + (total_chunks * 8) > len(data):
        raise ValueError("AWC chunk info table is truncated")

    chunk_infos: list[AwcChunkInfo] = []
    for _ in range(total_chunks):
        raw = struct.unpack_from(f"{endian}Q", data, offset)[0]
        chunk_infos.append(AwcChunkInfo.from_raw(raw))
        offset += 8

    if data_offset > len(data):
        raise ValueError("AWC data offset points outside the file")

    streams: list[AwcStream] = []
    chunk_cursor = 0
    for stream_id, chunk_count in stream_infos:
        chunks: list[AwcChunk] = []
        for info in chunk_infos[chunk_cursor : chunk_cursor + chunk_count]:
            chunk = AwcChunk.from_info(info, data, endian)
            if (
                decrypt
                and not whole_file_encrypted
                and (flags & 2)
                and chunk.type_value == int(AwcChunkType.DATA)
                and len(chunk.data) % 4 == 0
            ):
                chunk.data = decrypt_awc_rsxxtea(chunk.data, awc_key)
            chunks.append(chunk)
        chunk_cursor += chunk_count
        streams.append(AwcStream(stream_id, chunks))

    awc = Awc(streams, version=version, flags=flags, path=path, endian=endian, whole_file_encrypted=whole_file_encrypted)
    if chunk_indices:
        expected = []
        cursor = 0
        for _, chunk_count in stream_infos:
            expected.append(cursor)
            cursor += chunk_count
        if chunk_indices != expected:
            # Preserve validity signal without rejecting files that differ from the common pattern.
            awc.chunk_indices_flag = True
    return awc


def build_awc_bytes(awc: Awc) -> bytes:
    endian = "<"
    streams = list(awc.streams)
    stream_count = len(streams)
    chunk_indices_flag = bool(awc.flags & 1)
    info_start = 16 + (stream_count * 2 if chunk_indices_flag else 0)
    data_offset = info_start + (stream_count * 4) + sum(len(stream.chunks) * 8 for stream in streams)

    all_chunks: list[AwcChunk] = [chunk for stream in streams for chunk in stream.chunks]
    should_sort_chunks = bool(awc.multi_channel_flag or not awc.single_channel_encrypt_flag)
    write_chunks = sorted(all_chunks, key=lambda chunk: chunk.sort_order) if should_sort_chunks else all_chunks

    cursor = data_offset
    payload_by_chunk: dict[int, bytes] = {}
    info_by_chunk: dict[int, AwcChunkInfo] = {}
    for chunk in write_chunks:
        alignment = chunk.alignment
        if alignment:
            cursor += (-cursor) % alignment
        payload = chunk.to_payload(endian)
        if not awc.whole_file_encrypted and awc.single_channel_encrypt_flag and chunk.type_value == int(AwcChunkType.DATA):
            payload += b"\x00" * ((-len(payload)) % 4)
            payload = encrypt_awc_rsxxtea(payload)
        if len(payload) > AWC_CHUNK_FIELD_MASK:
            raise ValueError("AWC chunk is too large")
        info = AwcChunkInfo(chunk.type, size=len(payload), offset=cursor)
        chunk.info = info
        payload_by_chunk[id(chunk)] = payload
        info_by_chunk[id(chunk)] = info
        cursor += len(payload)

    out = bytearray()
    out += struct.pack(f"{endian}IHHii", AWC_MAGIC_LE, int(awc.version) & 0xFFFF, int(awc.flags) & 0xFFFF, stream_count, data_offset)

    if chunk_indices_flag:
        chunk_cursor = 0
        for stream in streams:
            out += struct.pack(f"{endian}H", chunk_cursor & 0xFFFF)
            chunk_cursor += len(stream.chunks)

    for stream in streams:
        raw = (stream.hash & AWC_STREAM_ID_MASK) | ((len(stream.chunks) & 0x7) << 29)
        out += struct.pack(f"{endian}I", raw)

    for stream in streams:
        for chunk in stream.chunks:
            out += struct.pack(f"{endian}Q", info_by_chunk[id(chunk)].to_raw())

    for chunk in write_chunks:
        info = info_by_chunk[id(chunk)]
        if len(out) < info.offset:
            out += b"\x00" * (info.offset - len(out))
        out += payload_by_chunk[id(chunk)]

    data = bytes(out)
    if awc.whole_file_encrypted:
        data += b"\x00" * ((-len(data)) % 4)
        data = encrypt_awc_rsxxtea(data)
    return data


def save_awc(awc: Awc, path: str | Path) -> None:
    Path(path).write_bytes(build_awc_bytes(awc))


__all__ = [
    "build_awc_bytes",
    "read_awc",
    "save_awc",
]
