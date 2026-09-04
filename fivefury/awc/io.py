from __future__ import annotations

import struct
from collections.abc import Callable
from pathlib import Path

from ..common import atomic_write_bytes
from .constants import (
    AWC_CHUNK_FIELD_MASK,
    AWC_MAGIC_BE,
    AWC_MAGIC_LE,
    AWC_STREAM_ID_MASK,
    AwcChunkType,
    AwcCodecType,
)
from .crypto import decrypt_awc_rsxxtea, encrypt_awc_rsxxtea
from .structures import Awc, AwcChunk, AwcChunkInfo, AwcStream


def _read_source(
    source: bytes | bytearray | memoryview | str | Path,
    path: str | Path | None,
) -> tuple[bytes, str | Path | None]:
    if not isinstance(source, (str, Path)):
        return bytes(source), path
    source_path = Path(source)
    return source_path.read_bytes(), source_path if path is None else path


def _awc_endian(data: bytes) -> str | None:
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic == AWC_MAGIC_LE:
        return "<"
    if magic == AWC_MAGIC_BE:
        return ">"
    return None


def _open_awc_container(
    data: bytes,
    *,
    decrypt: bool,
    awc_key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None,
) -> tuple[bytes, str, bool]:
    endian = _awc_endian(data)
    if endian is not None:
        return data, endian, False
    magic = struct.unpack_from("<I", data, 0)[0]
    if not decrypt or len(data) % 4:
        raise ValueError(f"Invalid AWC magic 0x{magic:08X}")
    decrypted = decrypt_awc_rsxxtea(data, awc_key)
    endian = _awc_endian(decrypted)
    if endian is None:
        magic = struct.unpack_from("<I", decrypted, 0)[0]
        raise ValueError(f"Invalid AWC magic 0x{magic:08X} after whole-file decryption")
    return decrypted, endian, True


def _read_awc_tables(
    data: bytes,
    endian: str,
    flags: int,
    stream_count: int,
) -> tuple[list[int], list[tuple[int, int]], list[AwcChunkInfo]]:
    offset = 16
    chunk_indices: list[int] = []
    if flags & 1:
        table_size = stream_count * 2
        if offset + table_size > len(data):
            raise ValueError("AWC chunk index table is truncated")
        if stream_count:
            chunk_indices = list(struct.unpack_from(f"{endian}{stream_count}H", data, offset))
        offset += table_size

    if offset + stream_count * 4 > len(data):
        raise ValueError("AWC stream info table is truncated")
    stream_infos = [
        (raw & AWC_STREAM_ID_MASK, raw >> 29)
        for raw in struct.unpack_from(f"{endian}{stream_count}I", data, offset)
    ]
    offset += stream_count * 4

    total_chunks = sum(chunk_count for _, chunk_count in stream_infos)
    if offset + total_chunks * 8 > len(data):
        raise ValueError("AWC chunk info table is truncated")
    chunk_infos = [
        AwcChunkInfo.from_raw(raw)
        for raw in struct.unpack_from(f"{endian}{total_chunks}Q", data, offset)
    ]
    return chunk_indices, stream_infos, chunk_infos


def _transform_multichannel_data(
    data: bytes,
    *,
    block_count: int,
    block_size: int,
    transform: Callable[[bytes], bytes],
) -> bytes:
    if block_count < 0 or block_size <= 0:
        raise ValueError("Invalid encrypted AWC multichannel block layout")
    if block_count == 0:
        return data

    output = bytearray(data)
    for block_index in range(block_count):
        start = block_index * block_size
        if start >= len(data):
            raise ValueError("Encrypted AWC multichannel data is truncated")
        end = min(start + block_size, len(data))
        block = data[start:end]
        if len(block) % 4:
            raise ValueError(
                "Encrypted AWC multichannel block size must be divisible by 4"
            )
        output[start:end] = transform(block)
    return bytes(output)


def _read_streams(
    data: bytes,
    endian: str,
    stream_infos: list[tuple[int, int]],
    chunk_infos: list[AwcChunkInfo],
    *,
    decrypt: bool,
    encrypted_chunks: bool,
    awc_key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None,
) -> list[AwcStream]:
    streams: list[AwcStream] = []
    chunk_cursor = 0
    for stream_id, chunk_count in stream_infos:
        chunks: list[AwcChunk] = []
        stream_codec: AwcCodecType | None = None
        for info in chunk_infos[chunk_cursor : chunk_cursor + chunk_count]:
            chunk = AwcChunk.from_info(
                info,
                data,
                endian,
                seek_table_entry_size=2 if stream_codec is AwcCodecType.MP3 else 4,
            )
            if chunk.format is not None:
                stream_codec = chunk.format.codec
            if decrypt and encrypted_chunks and chunk.type_value == int(AwcChunkType.DATA) and len(chunk.data) % 4 == 0:
                chunk.data = decrypt_awc_rsxxtea(chunk.data, awc_key)
            chunks.append(chunk)
        chunk_cursor += chunk_count
        streams.append(AwcStream(stream_id, chunks))
    return streams


def _apply_multichannel_layout(
    awc: Awc,
    *,
    decrypt: bool,
    awc_key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None,
) -> None:
    if not awc.multi_channel_flag:
        return
    source_stream = next((stream for stream in awc.streams if stream.stream_format_chunk is not None), None)
    if source_stream is None or source_stream.stream_format_chunk is None:
        return
    stream_format = source_stream.stream_format_chunk
    if decrypt and not awc.whole_file_encrypted and awc.multi_channel_encrypt_flag and source_stream.data_chunk is not None:
        source_stream.data_chunk.data = _transform_multichannel_data(
            source_stream.data_chunk.data,
            block_count=int(stream_format.block_count),
            block_size=int(stream_format.block_size),
            transform=lambda block: decrypt_awc_rsxxtea(block, awc_key),
        )
    channels_by_id = {channel.id & AWC_STREAM_ID_MASK: channel for channel in stream_format.channels}
    for stream in awc.streams:
        stream.stream_format = channels_by_id.get(stream.hash)


def read_awc(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    path: str | Path | None = None,
    decrypt: bool = True,
    awc_key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None = None,
) -> Awc:
    data, path = _read_source(source, path)
    if len(data) < 16:
        raise ValueError("AWC data is too small")
    data, endian, whole_file_encrypted = _open_awc_container(data, decrypt=decrypt, awc_key=awc_key)

    _magic, version, flags, stream_count, data_offset = struct.unpack_from(
        f"{endian}IHHii", data, 0
    )
    if stream_count < 0:
        raise ValueError("AWC stream count is negative")

    chunk_indices, stream_infos, chunk_infos = _read_awc_tables(data, endian, flags, stream_count)
    if data_offset > len(data):
        raise ValueError("AWC data offset points outside the file")
    streams = _read_streams(
        data,
        endian,
        stream_infos,
        chunk_infos,
        decrypt=decrypt,
        encrypted_chunks=not whole_file_encrypted and bool(flags & 2) and not bool(flags & 4),
        awc_key=awc_key,
    )

    awc = Awc(
        streams,
        version=version,
        flags=flags,
        path=path,
        endian=endian,
        whole_file_encrypted=whole_file_encrypted,
    )
    _apply_multichannel_layout(awc, decrypt=decrypt, awc_key=awc_key)
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


def _encode_chunk_payload(awc: Awc, chunk: AwcChunk, owner: AwcStream, endian: str) -> bytes:
    payload = chunk.to_payload(endian)
    if awc.whole_file_encrypted or chunk.type_value != int(AwcChunkType.DATA):
        return payload
    if awc.multi_channel_flag and awc.multi_channel_encrypt_flag:
        stream_format = owner.stream_format_chunk
        if stream_format is None:
            raise ValueError("Encrypted AWC multichannel data requires a stream-format chunk")
        return _transform_multichannel_data(
            payload,
            block_count=int(stream_format.block_count),
            block_size=int(stream_format.block_size),
            transform=encrypt_awc_rsxxtea,
        )
    if not awc.single_channel_encrypt_flag:
        return payload
    payload += b"\x00" * (-len(payload) % 4)
    return encrypt_awc_rsxxtea(payload)


def _layout_chunks(
    awc: Awc,
    streams: list[AwcStream],
    data_offset: int,
    endian: str,
) -> tuple[list[AwcChunk], dict[int, bytes], dict[int, AwcChunkInfo]]:
    all_chunks = [chunk for stream in streams for chunk in stream.chunks]
    owners = {id(chunk): stream for stream in streams for chunk in stream.chunks}
    write_chunks = (
        sorted(all_chunks, key=lambda chunk: chunk.sort_order)
        if awc.multi_channel_flag or not awc.single_channel_encrypt_flag
        else all_chunks
    )
    cursor = data_offset
    payloads: dict[int, bytes] = {}
    infos: dict[int, AwcChunkInfo] = {}
    for chunk in write_chunks:
        if chunk.alignment:
            cursor += -cursor % chunk.alignment
        payload = _encode_chunk_payload(awc, chunk, owners[id(chunk)], endian)
        if len(payload) > AWC_CHUNK_FIELD_MASK:
            raise ValueError("AWC chunk is too large")
        info = AwcChunkInfo(chunk.type, size=len(payload), offset=cursor)
        chunk.info = info
        payloads[id(chunk)] = payload
        infos[id(chunk)] = info
        cursor += len(payload)
    return write_chunks, payloads, infos


def _write_awc_tables(
    awc: Awc,
    streams: list[AwcStream],
    infos: dict[int, AwcChunkInfo],
    data_offset: int,
    endian: str,
) -> bytearray:
    out = bytearray(struct.pack(
        f"{endian}IHHii",
        AWC_MAGIC_LE,
        int(awc.version) & 0xFFFF,
        int(awc.flags) & 0xFFFF,
        len(streams),
        data_offset,
    ))
    if awc.flags & 1:
        chunk_cursor = 0
        for stream in streams:
            out += struct.pack(f"{endian}H", chunk_cursor & 0xFFFF)
            chunk_cursor += len(stream.chunks)
    for stream in streams:
        raw = (stream.hash & AWC_STREAM_ID_MASK) | ((len(stream.chunks) & 0x7) << 29)
        out += struct.pack(f"{endian}I", raw)
    for stream in streams:
        for chunk in stream.chunks:
            out += struct.pack(f"{endian}Q", infos[id(chunk)].to_raw())
    return out


def build_awc_bytes(awc: Awc) -> bytes:
    from .validation import validate_awc_binary_fields

    validate_awc_binary_fields(awc).raise_for_errors()
    endian = "<"
    # Retail multichannel AWC files keep the stream-info table ordered by the
    # 29-bit stream hash, independently from the physical channel order stored
    # in the stream-format chunk.  RAGE looks these entries up as a sorted
    # table; emitting them in speaker/channel order can leave otherwise valid
    # five-channel mastered banks silent in GTA V Enhanced.
    streams = (
        sorted(awc.streams, key=lambda stream: stream.hash)
        if awc.multi_channel_flag
        else list(awc.streams)
    )
    stream_count = len(streams)
    chunk_indices_flag = bool(awc.flags & 1)
    info_start = 16 + (stream_count * 2 if chunk_indices_flag else 0)
    data_offset = (
        info_start
        + (stream_count * 4)
        + sum(len(stream.chunks) * 8 for stream in streams)
    )

    write_chunks, payload_by_chunk, info_by_chunk = _layout_chunks(awc, streams, data_offset, endian)
    out = _write_awc_tables(awc, streams, info_by_chunk, data_offset, endian)
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


def save_awc(awc: Awc, path: str | Path) -> Path:
    return atomic_write_bytes(path, build_awc_bytes(awc))


__all__ = [
    "build_awc_bytes",
    "read_awc",
    "save_awc",
]
