from __future__ import annotations

from copy import deepcopy


def expression_state(expression) -> tuple:
    """Snapshot serialized semantics, including edits made directly to operands."""
    return (
        expression.name,
        int(expression.name_hash),
        expression.vft,
        expression.unknown_4h,
        expression.unknown_70h,
        expression.signature,
        expression.max_stream_size,
        expression.expression_flags,
        expression.header,
        tuple(
            (info.pointer, info.count, info.capacity, info.unknown)
            for info in (
                expression.streams_info,
                expression.tracks_info,
                expression.springs_info,
                expression.variables_info,
            )
        ),
        tuple((track.bone_id, track.track, track.flags) for track in expression.tracks),
        tuple(spring.raw for spring in expression.springs),
        tuple(int(variable) for variable in expression.variables),
        tuple(
            (
                int(stream.name_hash),
                stream.depth,
                stream.data1,
                stream.data2,
                stream.data3,
                tuple(
                    (
                        instruction.opcode,
                        instruction.index,
                        instruction.data1_offset,
                        instruction.data2_offset,
                        instruction.parsed,
                        deepcopy(instruction.operands),
                    )
                    for instruction in stream.instructions
                ),
            )
            for stream in expression.streams
        ),
    )


def yed_state(yed) -> tuple:
    dictionary = yed.dictionary
    return (
        yed.version,
        yed.game,
        yed.system_flags,
        yed.graphics_flags,
        yed.system_data,
        yed.graphics_data,
        dictionary.file_vft,
        dictionary.file_unknown,
        dictionary.unknown_10h,
        dictionary.unknown_14h,
        dictionary.unknown_18h,
        dictionary.unknown_1ch,
        tuple(
            (info.pointer, info.count, info.capacity, info.unknown)
            for info in (dictionary.expression_name_hashes, dictionary.expressions_info)
        ),
        tuple(expression_state(expression) for expression in yed.expressions),
    )
