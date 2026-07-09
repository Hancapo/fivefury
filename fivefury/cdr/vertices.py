from __future__ import annotations

import math
import struct

from .model import CdrEdgeStream, CdrEdgeStreamAttribute, CdrVertexFormat, CdrVertexSemantic

_FVF_TYPE_SIZES = (2, 4, 6, 8, 4, 8, 12, 16, 4, 4, 4, 0, 0, 0, 4, 8)
_DYNAMIC_ORDER = (
    CdrVertexSemantic.POSITION,
    CdrVertexSemantic.NORMAL,
    CdrVertexSemantic.TANGENT0,
    CdrVertexSemantic.TANGENT1,
    CdrVertexSemantic.TEXCOORD0,
    CdrVertexSemantic.TEXCOORD1,
    CdrVertexSemantic.TEXCOORD2,
    CdrVertexSemantic.TEXCOORD3,
    CdrVertexSemantic.TEXCOORD4,
    CdrVertexSemantic.TEXCOORD5,
    CdrVertexSemantic.TEXCOORD6,
    CdrVertexSemantic.TEXCOORD7,
    CdrVertexSemantic.WEIGHT,
    CdrVertexSemantic.BINORMAL0,
    CdrVertexSemantic.BINORMAL1,
    CdrVertexSemantic.BINDING,
    CdrVertexSemantic.DIFFUSE,
    CdrVertexSemantic.SPECULAR,
)

EDGE_FORMAT_I16N = 0x01
EDGE_FORMAT_F32 = 0x02
EDGE_FORMAT_F16 = 0x03
EDGE_FORMAT_U8N = 0x04
EDGE_FORMAT_I16 = 0x05
EDGE_FORMAT_X11Y11Z10N = 0x06
EDGE_FORMAT_U8 = 0x07
EDGE_FORMAT_FIXED_POINT = 0x08
EDGE_FORMAT_UNIT_VECTOR = 0x09


def parse_fvf(data: bytes) -> CdrVertexFormat:
    if len(data) < 16:
        raise ValueError("PS3 FVF is truncated")
    channels, stride, flags, dynamic_order, channel_count, channel_types = struct.unpack_from(">IBBBBQ", data, 0)
    return CdrVertexFormat(
        channels=channels,
        stride=stride,
        flags=flags,
        dynamic_order=bool(dynamic_order),
        channel_count=channel_count,
        channel_types=channel_types,
    )


def _fvf_offsets(vertex_format: CdrVertexFormat) -> dict[CdrVertexSemantic, int]:
    semantics = _DYNAMIC_ORDER if vertex_format.dynamic_order else tuple(CdrVertexSemantic)
    offsets: dict[CdrVertexSemantic, int] = {}
    offset = 0
    for semantic in semantics:
        if not vertex_format.has(semantic):
            continue
        offsets[semantic] = offset
        data_type = vertex_format.type_of(semantic)
        if data_type >= len(_FVF_TYPE_SIZES) or _FVF_TYPE_SIZES[data_type] <= 0:
            raise ValueError(f"unsupported PS3 FVF data type {data_type} for {semantic.name}")
        offset += _FVF_TYPE_SIZES[data_type]
    return offsets


def _snorm8(value: int) -> float:
    return max(-1.0, int(value) / 127.0)


def _decode_fvf_value(data: bytes, offset: int, data_type: int) -> tuple[float | int, ...]:
    if data_type == 0:
        return (struct.unpack_from(">e", data, offset)[0],)
    if data_type in {1, 2, 3}:
        return struct.unpack_from(">" + "e" * (data_type + 1), data, offset)
    if data_type == 4:
        return (struct.unpack_from(">f", data, offset)[0],)
    if data_type in {5, 6, 7}:
        return struct.unpack_from(">" + "f" * (data_type - 3), data, offset)
    if data_type == 8:
        return struct.unpack_from("4B", data, offset)
    if data_type == 9:
        return tuple(component / 255.0 for component in struct.unpack_from("4B", data, offset))
    if data_type == 10:
        return tuple(_snorm8(component) for component in struct.unpack_from("4b", data, offset))
    if data_type == 14:
        return struct.unpack_from(">2h", data, offset)
    if data_type == 15:
        return struct.unpack_from(">4h", data, offset)
    raise ValueError(f"unsupported PS3 FVF data type {data_type}")


def decode_fvf_vertices(data: bytes, count: int, vertex_format: CdrVertexFormat) -> dict[str, object]:
    stride = int(vertex_format.stride)
    if stride <= 0 or len(data) < count * stride:
        raise ValueError("PS3 vertex buffer is truncated")
    offsets = _fvf_offsets(vertex_format)
    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    tangents: list[tuple[float, float, float, float]] = []
    texcoords: list[list[tuple[float, float]]] = [[] for _ in range(8)]
    colours0: list[tuple[float, float, float, float]] = []
    colours1: list[tuple[float, float, float, float]] = []
    weights: list[tuple[float, float, float, float]] = []
    bindings: list[tuple[int, int, int, int]] = []

    for vertex_index in range(count):
        base = vertex_index * stride
        for semantic, relative_offset in offsets.items():
            value = _decode_fvf_value(data, base + relative_offset, vertex_format.type_of(semantic))
            if semantic is CdrVertexSemantic.POSITION:
                positions.append(tuple(float(component) for component in value[:3]))
            elif semantic is CdrVertexSemantic.NORMAL:
                normals.append(tuple(float(component) for component in value[:3]))
            elif semantic is CdrVertexSemantic.TANGENT0:
                padded = tuple(float(component) for component in value) + (1.0,) * (4 - len(value))
                tangents.append(padded[:4])
            elif semantic is CdrVertexSemantic.DIFFUSE:
                colours0.append(tuple(float(component) for component in value[:4]))
            elif semantic is CdrVertexSemantic.SPECULAR:
                colours1.append(tuple(float(component) for component in value[:4]))
            elif semantic is CdrVertexSemantic.WEIGHT:
                values = tuple(float(component) for component in value)
                if values and max(abs(component) for component in values) > 1.0:
                    values = tuple(component / 255.0 for component in values)
                weights.append((values + (0.0, 0.0, 0.0, 0.0))[:4])
            elif semantic is CdrVertexSemantic.BINDING:
                bindings.append(tuple(int(component) for component in value[:4]))
            elif CdrVertexSemantic.TEXCOORD0 <= semantic <= CdrVertexSemantic.TEXCOORD7:
                channel = int(semantic) - int(CdrVertexSemantic.TEXCOORD0)
                texcoords[channel].append((float(value[0]), float(value[1])))

    while texcoords and not texcoords[-1]:
        texcoords.pop()
    return {
        "positions": positions,
        "normals": normals,
        "tangents": tangents,
        "texcoords": texcoords,
        "colours0": colours0,
        "colours1": colours1,
        "blend_weights": weights,
        "blend_indices": bindings,
    }


def parse_edge_stream(data: bytes) -> CdrEdgeStream:
    if len(data) < 8:
        raise ValueError("EDGE stream description is truncated")
    attribute_count, stride, block_count = struct.unpack_from("3B", data, 0)
    required_size = (int(block_count) + 1) * 8
    if required_size > len(data):
        raise ValueError("EDGE stream blocks are truncated")
    attributes: list[CdrEdgeStreamAttribute] = []
    for index in range(attribute_count):
        offset = 8 + index * 8
        values = struct.unpack_from("8B", data, offset)
        fixed_bits: tuple[int, ...] = ()
        if values[1] == EDGE_FORMAT_FIXED_POINT:
            fixed_offset = 8 + values[6]
            if fixed_offset + 8 > required_size:
                raise ValueError("EDGE fixed-point block is out of range")
            fixed_bits = tuple(data[fixed_offset : fixed_offset + 8])
        attributes.append(
            CdrEdgeStreamAttribute(
                offset=values[0],
                format=values[1],
                component_count=values[2],
                semantic_id=values[3],
                size=values[4],
                vertex_program_slot=values[5],
                fixed_block_offset=values[6],
                fixed_bits=fixed_bits,
            )
        )
    return CdrEdgeStream(stride=stride, attributes=attributes)


def _sign_extend(value: int, width: int) -> int:
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def _read_msb_bits(data: bytes, bit_offset: int, width: int) -> int:
    value = 0
    for bit_index in range(width):
        absolute = bit_offset + bit_index
        if absolute // 8 >= len(data):
            raise ValueError("packed EDGE data is truncated")
        value = (value << 1) | ((data[absolute // 8] >> (7 - (absolute & 7))) & 1)
    return value


def _decode_x11y11z10(value: int) -> tuple[float, float, float, float]:
    x = _sign_extend((value >> 21) & 0x7FF, 11) / 1023.0
    y = _sign_extend((value >> 10) & 0x7FF, 11) / 1023.0
    z = _sign_extend(value & 0x3FF, 10) / 511.0
    return (max(-1.0, x), max(-1.0, y), max(-1.0, z), 1.0)


def _decode_unit_vector(value: int) -> tuple[float, float, float, float]:
    a = ((value >> 14) & 0x3FF) / 511.5 - 1.0
    b = ((value >> 4) & 0x3FF) / 511.5 - 1.0
    c = math.sqrt(max(0.0, 1.0 - a * a - b * b))
    if not value & 0x1:
        c = -c
    missing = (value >> 2) & 0x3
    if missing == 0:
        xyz = (c, a, b)
    elif missing == 1:
        xyz = (a, c, b)
    else:
        xyz = (a, b, c)
    return (*xyz, 1.0 if value & 0x2 else -1.0)


def _decode_edge_attribute(
    raw: bytes,
    base: int,
    attribute: CdrEdgeStreamAttribute,
    fixed_offsets: tuple[int, ...],
) -> tuple[float, ...]:
    offset = base + attribute.offset
    count = attribute.component_count
    if attribute.format == EDGE_FORMAT_F32:
        return tuple(float(value) for value in struct.unpack_from(">" + "f" * count, raw, offset))
    if attribute.format == EDGE_FORMAT_F16:
        return tuple(float(value) for value in struct.unpack_from(">" + "e" * count, raw, offset))
    if attribute.format == EDGE_FORMAT_I16:
        return tuple(float(value) for value in struct.unpack_from(">" + "h" * count, raw, offset))
    if attribute.format == EDGE_FORMAT_I16N:
        return tuple((value * 2.0 + 1.0) / 65535.0 for value in struct.unpack_from(">" + "h" * count, raw, offset))
    if attribute.format == EDGE_FORMAT_U8:
        return tuple(float(value) for value in raw[offset : offset + count])
    if attribute.format == EDGE_FORMAT_U8N:
        return tuple(value / 255.0 for value in raw[offset : offset + count])
    if attribute.format == EDGE_FORMAT_X11Y11Z10N:
        return _decode_x11y11z10(struct.unpack_from(">I", raw, offset)[0])
    if attribute.format == EDGE_FORMAT_UNIT_VECTOR:
        value = int.from_bytes(raw[offset : offset + 3], "big")
        return _decode_unit_vector(value)
    if attribute.format == EDGE_FORMAT_FIXED_POINT:
        bits = attribute.fixed_bits
        widths = [bits[index * 2] + bits[index * 2 + 1] for index in range(count)]
        mantissas = [bits[index * 2 + 1] for index in range(count)]
        packed = raw[offset : offset + attribute.size]
        values: list[float] = []
        bit_offset = 0
        for index, (width, mantissa) in enumerate(zip(widths, mantissas, strict=True)):
            encoded = _sign_extend(_read_msb_bits(packed, bit_offset, width), width)
            fixed_offset = fixed_offsets[index] if index < len(fixed_offsets) else 0
            values.append((encoded + fixed_offset) / float(1 << mantissa))
            bit_offset += width
        return tuple(values)
    raise ValueError(f"unsupported EDGE attribute format {attribute.format}")


def decode_edge_vertices(
    raw: bytes,
    count: int,
    stream: CdrEdgeStream,
    *,
    fixed_offsets: tuple[int, ...] = (),
) -> dict[int, list[tuple[float, ...]]]:
    if stream.stride <= 0 or len(raw) < count * stream.stride:
        raise ValueError("EDGE vertex stream is truncated")
    result: dict[int, list[tuple[float, ...]]] = {}
    fixed_index = 0
    for attribute in stream.attributes:
        attribute_fixed_offsets: tuple[int, ...] = ()
        if attribute.format == EDGE_FORMAT_FIXED_POINT:
            attribute_fixed_offsets = fixed_offsets[fixed_index : fixed_index + attribute.component_count]
            fixed_index += 4
        values = result.setdefault(attribute.semantic_id, [])
        for vertex_index in range(count):
            values.append(_decode_edge_attribute(raw, vertex_index * stream.stride, attribute, attribute_fixed_offsets))
    return result


def decompress_edge_indices(raw: bytes, index_count: int) -> list[int]:
    if index_count <= 0:
        return []
    if len(raw) < 8:
        raise ValueError("compressed EDGE index stream is truncated")
    out_of_sequence_count, delta_offset, control_bytes = struct.unpack_from(">3H", raw, 0)
    bits_per_delta = raw[6]
    triangle_count = index_count // 3
    two_bit_offset = 8 + control_bytes
    two_bit_size = (triangle_count * 2 + 7) // 8
    n_bit_offset = two_bit_offset + two_bit_size
    n_bit_size = (out_of_sequence_count * bits_per_delta + 7) // 8
    if n_bit_offset + n_bit_size > len(raw):
        raise ValueError("compressed EDGE delta stream is truncated")

    deltas = [
        _read_msb_bits(raw[n_bit_offset : n_bit_offset + n_bit_size], index * bits_per_delta, bits_per_delta)
        for index in range(out_of_sequence_count)
    ]
    lane_accumulators = [0] * 8
    for index, value in enumerate(deltas):
        lane = index & 7
        lane_accumulators[lane] = (value - delta_offset + lane_accumulators[lane]) & 0xFFFF
        deltas[index] = lane_accumulators[lane]

    sequence: list[int] = []
    next_sequential = 0
    delta_index = 0
    for bit_index in range(control_bytes * 8):
        out_of_sequence = (raw[8 + bit_index // 8] >> (7 - (bit_index & 7))) & 1
        if out_of_sequence:
            if delta_index >= len(deltas):
                raise ValueError("compressed EDGE index stream consumes too many deltas")
            sequence.append(deltas[delta_index])
            delta_index += 1
        else:
            sequence.append(next_sequential)
            next_sequential += 1

    output: list[int] = []
    sequence_index = 0
    for triangle_index in range(triangle_count):
        code = (raw[two_bit_offset + triangle_index // 4] >> (6 - 2 * (triangle_index & 3))) & 0x3
        consumed = 3 if code == 3 else 1
        if sequence_index + consumed > len(sequence):
            raise ValueError("compressed EDGE triangle stream consumes too many indices")
        if code == 3:
            output.extend(sequence[sequence_index : sequence_index + 3])
        elif not output:
            raise ValueError("compressed EDGE triangle stream starts with a reused triangle")
        elif code == 2:
            output.extend((output[-2], output[-3], sequence[sequence_index]))
        elif code == 1:
            output.extend((output[-1], output[-2], sequence[sequence_index]))
        else:
            output.extend((output[-3], output[-1], sequence[sequence_index]))
        sequence_index += consumed
    return output[:index_count]


__all__ = [
    "decode_edge_vertices",
    "decode_fvf_vertices",
    "decompress_edge_indices",
    "parse_edge_stream",
    "parse_fvf",
]
