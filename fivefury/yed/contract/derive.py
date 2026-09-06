from __future__ import annotations

import copy
import struct
from dataclasses import dataclass

from ...hashing import crc32
from ...metahash import MetaHash
from ..enums import YedInstructionType as Op
from ..enums import YedTrackFormat
from ..model import ResourceListInfo, YedExpression, YedSpring, YedTrack
from .traversal import BLENDS, READS, WRITES, preorder


@dataclass(frozen=True, slots=True)
class _Access:
    bone: int
    channel: int
    format: YedTrackFormat
    is_input: bool
    operand: dict
    index_key: str


def _accesses(instruction, tracks):
    op, operands = instruction.type, instruction.operands
    if op in READS | WRITES:
        operands.setdefault("component_index", 0)
        yield _Access(
            int(operands["bone_id"]),
            int(operands["track"]),
            YedTrackFormat(operands["format"]),
            op in READS,
            operands,
            "track_index",
        )
    elif op in BLENDS:
        sources = operands["source_infos"]
        count = len(sources)
        if count % 4 or count != int(operands.get("source_count", count)):
            raise ValueError("Linear sources must form complete groups of four")
        groups = count // 4
        # Packed sources are transposed into four-wide lanes.
        for lane in range(4):
            for group in range(groups):
                source = sources[group * 4 + lane]
                index = int(source["track_index"])
                if not 0 <= index < len(tracks):
                    raise ValueError("Linear source references a missing track")
                track = tracks[index]
                yield _Access(
                    track.bone_id,
                    track.track,
                    track.format,
                    True,
                    source,
                    "track_index",
                )
    elif op == Op.DEFINE_SPRING:
        spring = YedSpring(bytes(operands["spring_raw"]))
        yield _Access(
            spring.bone_id,
            1,
            YedTrackFormat.QUATERNION,
            False,
            operands,
            "bone_track_rot",
        )
        yield _Access(
            spring.bone_id, 0, YedTrackFormat.VECTOR3, False, operands, "bone_track_pos"
        )


def derive_contract(expression: YedExpression) -> YedExpression:
    """Prepare a detached expression; failures never partially mutate authoring state."""
    result = copy.deepcopy(expression)
    result._original_contract_state = None
    old_tracks = result.tracks
    tracks: list[YedTrack] = []
    indices: dict[tuple[bool, int, int], int] = {}
    variables: list[MetaHash] = []
    motions: list[YedSpring] = []
    signature = 0
    for stream in result.streams:
        traversal, depth = preorder(stream.instructions)
        stream.depth = depth
        for instruction in traversal:
            for access in _accesses(instruction, old_tracks):
                if not 0 <= access.bone <= 0xFFFF or not 0 <= access.channel <= 0xFF:
                    raise ValueError("YED bone/channel does not fit its binary field")
                key = (access.is_input, access.channel, access.bone)
                index = indices.get(key)
                if index is None:
                    index = len(tracks)
                    if index >= 0xFFFF:
                        raise ValueError("YED track count exceeds 65535")
                    indices[key] = index
                    tracks.append(
                        YedTrack.from_parts(
                            access.bone,
                            access.channel,
                            access.format,
                            is_input=access.is_input,
                        )
                    )
                elif tracks[index].format != access.format:
                    raise ValueError(
                        "A directional DOF is accessed with conflicting formats"
                    )
                access.operand[access.index_key] = index
                signature = crc32(
                    struct.pack("<I", (access.channel << 16) | access.bone), signature
                )
            if instruction.type == Op.DEFINE_SPRING:
                motions.append(YedSpring(bytes(instruction.operands["spring_raw"])))
            elif instruction.type in (Op.GET_VARIABLE, Op.SET_VARIABLE):
                variable = MetaHash(instruction.operands["variable"])
                if variable not in variables:
                    variables.append(variable)
                instruction.operands["variable_index"] = variables.index(variable)
        stream.rebuild_buffers_from_instructions()
    result.tracks = tracks
    result.variables = variables
    if motions:
        result.springs = motions
    result.signature = signature
    result.max_stream_size = max(
        (
            0x10 + len(stream.data1) + len(stream.data2) + len(stream.data3)
            for stream in result.streams
        ),
        default=0,
    )
    for name in ("streams_info", "tracks_info", "springs_info", "variables_info"):
        setattr(result, name, ResourceListInfo())
    return result
