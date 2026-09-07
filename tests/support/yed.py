import struct

from fivefury import MetaHash, YedExpression, YedInstruction, YedStream, read_yed
from fivefury import YedInstructionType as Op
from fivefury.resource import get_resource_total_page_count
from fivefury.yed.constants import SPRING_BLOCK_SIZE
from tests.support.resource import ScatteredResource


def large_expression():
    expression = YedExpression.create("calibrated")
    for start in range(0, 147, 32):
        instructions = []
        for bone in range(56462 + start, 56462 + min(start + 32, 147)):
            for source, target, format in ((25, 0, 0), (26, 1, 1)):
                instructions.extend(
                    [
                        YedInstruction(
                            Op.TRACK_GET,
                            operands={
                                "bone_id": bone,
                                "track": source,
                                "format": format,
                            },
                        ),
                        YedInstruction(
                            Op.TRACK_SET,
                            operands={
                                "bone_id": bone,
                                "track": target,
                                "format": format,
                            },
                        ),
                    ]
                )
        instructions.append(YedInstruction(Op.END))
        expression.streams.append(
            YedStream(
                MetaHash(f"part{start}"), 0, b"", b"", b"", instructions=instructions
            )
        )
    return expression.recalculate_runtime_contract()


def pointer_fields(yed):
    yield from (0x50000008, 0x50000020, 0x50000030)
    for index in range(len(yed.expressions)):
        yield yed.dictionary.expressions_info.pointer + 8 * index
    for expression in yed.expressions:
        for relative in (0x20, 0x30, 0x40, 0x50, 0x60):
            yield expression.pointer + relative
        for index in range(len(expression.streams)):
            yield expression.streams_info.pointer + 8 * index


def assert_scattered_yed(raw, expected):
    parsed = read_yed(raw)
    scattered = ScatteredResource(raw)
    for field in pointer_fields(parsed):
        scattered.fixup(field)

    def array(address, stride):
        pointer, count, capacity, _ = struct.unpack(
            "<QHHI", scattered.read(address, 16)
        )
        assert count <= capacity
        return (
            pointer,
            count,
            scattered.read(pointer, stride * capacity) if capacity else b"",
        )

    root = scattered.relocate(0x50000000)
    _, count, expression_pointers = array(root + 0x30, 8)
    _, hash_count, hashes = array(root + 0x20, 4)
    assert hash_count == count == len(expected.expressions)
    expected_by_hash = {int(e.name_hash): e for e in expected.expressions}
    for index in range(count):
        pointer = struct.unpack_from("<Q", expression_pointers, index * 8)[0]
        expression = expected_by_hash[struct.unpack_from("<I", hashes, index * 4)[0]]
        header = scattered.read(pointer, 0x90)
        assert struct.unpack_from("<I", header, 0x74)[0] == expression.signature
        name_pointer, name_len, name_cap = struct.unpack_from("<QHH", header, 0x60)
        name = scattered.read(name_pointer, name_cap)
        assert name[: name_len + 1] == expression.name.encode("ascii") + b"\0"
        _, track_count, tracks = array(pointer + 0x30, 4)
        assert track_count == len(expression.tracks)
        assert tracks[: track_count * 4] == b"".join(
            struct.pack("<HBB", t.bone_id, t.track, t.flags) for t in expression.tracks
        )
        _, spring_count, springs = array(pointer + 0x40, SPRING_BLOCK_SIZE)
        assert spring_count == len(expression.springs)
        assert springs[: spring_count * SPRING_BLOCK_SIZE] == b"".join(
            s.raw for s in expression.springs
        )
        _, variable_count, variables = array(pointer + 0x50, 4)
        assert variables[: variable_count * 4] == b"".join(
            struct.pack("<I", int(v)) for v in expression.variables
        )
        _, stream_count, streams = array(pointer + 0x20, 8)
        assert stream_count == len(expression.streams)
        for si, source in enumerate(expression.streams):
            stream_pointer = struct.unpack_from("<Q", streams, si * 8)[0]
            stream_header = scattered.read(stream_pointer, 16)
            _, n1, n2, n3, depth = struct.unpack("<IIIHH", stream_header)
            assert depth == source.depth
            payload = scattered.read(stream_pointer, 16 + n1 + n2 + n3)[16:]
            assert payload == source.data1 + source.data2 + source.data3
    pages_pointer = struct.unpack("<Q", scattered.read(root + 8, 8))[0]
    pages = scattered.read(pages_pointer, 16)
    sc, gc = pages[8:10]
    assert sc == get_resource_total_page_count(parsed.system_flags)
    assert gc == get_resource_total_page_count(parsed.graphics_flags)
    scattered.read(pages_pointer, 16 + 8 * (sc + gc))
