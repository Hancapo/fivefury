from __future__ import annotations

import struct
from pathlib import Path

from ..binary import align, read_c_string
from .enums import Dat10RelType, Dat16RelType, Dat22RelType, Dat54SoundType, RelDatFileType
from .model import (
    Dat16Curve,
    Dat22Category,
    Dat10Synth,
    Dat10SynthPreset,
    Dat10SynthPresetVariable,
    Dat10SynthVariable,
    Dat54AutomationNoteMapRange,
    Dat54AutomationNoteMapSound,
    Dat54AutomationSound,
    Dat54AutomationSoundVariableOutput,
    Dat54ChildListSound,
    Dat54DirectionalSound,
    Dat54ExternalStreamSound,
    Dat54Fluctuator,
    Dat54FluctuatorSound,
    Dat54IfSound,
    Dat54KineticSound,
    Dat54LoopingSound,
    Dat54MathOperation,
    Dat54MathOperationSound,
    Dat54ModularSynthSound,
    Dat54ModularSynthSoundVariable,
    Dat54MultitrackSound,
    Dat54RandomizedSound,
    Dat54RandomizedVariation,
    Dat54SequentialSound,
    Dat54SimpleSound,
    Dat54SoundHashList,
    Dat54SoundSet,
    Dat54SoundSetItem,
    Dat54SoundSetList,
    Dat54StreamingSound,
    Dat54ParameterTransform,
    Dat54ParameterTransformBlock,
    Dat54ParameterTransformSound,
    Dat54VariableBlockSound,
    Dat54VariableCurveSound,
    Dat54VariableData,
    Dat54WrapperSound,
    Dat54WrapperVariable,
    RelFile,
    RelIndexHash,
    RelIndexString,
    RelItem,
    RelRawItem,
    RelSoundHeader,
    rel_hash,
)


def _read_source(source: bytes | bytearray | memoryview | str | Path) -> tuple[bytes, str | None]:
    if isinstance(source, (str, Path)):
        path = Path(source)
        return path.read_bytes(), str(path)
    return bytes(source), None


def _parse_name_table(data: bytes, offset: int, length: int, count: int) -> tuple[list[str], dict[int, str], int]:
    if length < 4:
        raise ValueError(f"Invalid REL name table length: {length}")
    table_start = offset + count * 4
    offsets = [struct.unpack_from("<I", data, offset + i * 4)[0] for i in range(count)]
    names = [read_c_string(data, table_start + rel_offset) for rel_offset in offsets]
    return names, dict(zip(offsets, names, strict=True)), offset + max(length - 4, 0)


def _parse_named_item_header(raw: bytes, name_by_offset: dict[int, str]) -> tuple[int, int, int, str | None] | None:
    if len(raw) < 8:
        return None
    packed, flags = struct.unpack_from("<II", raw, 0)
    type_id = packed & 0xFF
    name_table_offset = (packed >> 8) & 0xFFFFFF
    return type_id, name_table_offset, flags, name_by_offset.get(name_table_offset)


def _parse_dat10_item(index: RelIndexHash, raw: bytes, name_by_offset: dict[int, str]) -> RelItem:
    header = _parse_named_item_header(raw, name_by_offset)
    if header is None:
        return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=raw[0] if raw else 0, raw_data=raw)
    type_id, name_table_offset, flags, name = header
    if type_id == int(Dat10RelType.SYNTH_PRESET):
        count = raw[8]
        variables = [
            Dat10SynthPresetVariable(*struct.unpack_from("<Iff", raw, 9 + i * 12))
            for i in range(count)
            if 9 + i * 12 + 12 <= len(raw)
        ]
        return Dat10SynthPreset(
            name_hash=index.name_hash,
            name=name,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            name_table_offset=name_table_offset,
            flags=flags,
            variables=variables,
        )
    if type_id == int(Dat10RelType.SYNTH):
        offset = 8
        buffers_count, registers_count, outputs_count = struct.unpack_from("<iii", raw, offset)
        offset += 12
        output_indices = raw[offset : offset + 4]
        offset += 4
        bytecode_length, state_blocks_count, runtime_cost = struct.unpack_from("<iii", raw, offset)
        offset += 12
        bytecode = raw[offset : offset + bytecode_length]
        offset += bytecode_length
        constants_count = struct.unpack_from("<i", raw, offset)[0]
        offset += 4
        constants = list(struct.unpack_from("<" + "f" * constants_count, raw, offset)) if constants_count else []
        offset += constants_count * 4
        variables_count = struct.unpack_from("<i", raw, offset)[0]
        offset += 4
        variables = [
            Dat10SynthVariable(*struct.unpack_from("<If", raw, offset + i * 8))
            for i in range(variables_count)
            if offset + i * 8 + 8 <= len(raw)
        ]
        return Dat10Synth(
            name_hash=index.name_hash,
            name=name,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            name_table_offset=name_table_offset,
            flags=flags,
            buffers_count=buffers_count,
            registers_count=registers_count,
            outputs_count=outputs_count,
            output_indices=output_indices,
            bytecode=bytecode,
            state_blocks_count=state_blocks_count,
            runtime_cost=runtime_cost,
            constants=constants,
            variables=variables,
        )
    return RelRawItem(index.name_hash, name=name, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)


def _parse_dat16_item(index: RelIndexHash, raw: bytes, name_by_offset: dict[int, str]) -> RelItem:
    header = _parse_named_item_header(raw, name_by_offset)
    if header is None or len(raw) < 16:
        return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=raw[0] if raw else 0, raw_data=raw)
    type_id, name_table_offset, flags, name = header
    offset = 8
    min_input, max_input = struct.unpack_from("<ff", raw, offset)
    offset += 8
    curve = Dat16Curve(
        name_hash=index.name_hash,
        name=name,
        data_offset=index.offset,
        data_length=index.length,
        raw_data=raw,
        type_id=type_id,
        name_table_offset=name_table_offset,
        flags=flags,
        curve_type=Dat16RelType(type_id),
        min_input=min_input,
        max_input=max_input,
    )
    try:
        if type_id == int(Dat16RelType.CONSTANT_CURVE):
            curve.value = struct.unpack_from("<f", raw, offset)[0]
        elif type_id in {int(Dat16RelType.LINEAR_CURVE), int(Dat16RelType.LINEAR_DB_CURVE)}:
            curve.left_hand_pair_x, curve.left_hand_pair_y, curve.right_hand_pair_x, curve.right_hand_pair_y = struct.unpack_from(
                "<ffff", raw, offset
            )
        elif type_id == int(Dat16RelType.PIECEWISE_LINEAR_CURVE):
            count = struct.unpack_from("<I", raw, offset)[0]
            offset += 4
            curve.points = [
                struct.unpack_from("<ff", raw, offset + i * 8)
                for i in range(count)
                if offset + i * 8 + 8 <= len(raw)
            ]
        elif type_id == int(Dat16RelType.EQUAL_POWER_CURVE):
            curve.flip = struct.unpack_from("<i", raw, offset)[0]
        elif type_id in {int(Dat16RelType.VALUE_TABLE_CURVE), int(Dat16RelType.DISTANCE_ATTENUATION_VALUE_TABLE_CURVE)}:
            count = struct.unpack_from("<i", raw, offset)[0]
            offset += 4
            curve.values = list(struct.unpack_from("<" + "f" * count, raw, offset)) if count and offset + count * 4 <= len(raw) else []
        elif type_id == int(Dat16RelType.EXPONENTIAL_CURVE):
            curve.flip, curve.exponent = struct.unpack_from("<if", raw, offset)
        elif type_id in {
            int(Dat16RelType.DECAYING_EXPONENTIAL_CURVE),
            int(Dat16RelType.DECAYING_SQUARED_EXPONENTIAL_CURVE),
            int(Dat16RelType.ONE_OVER_X_SQUARED_CURVE),
        }:
            curve.horizontal_scaling = struct.unpack_from("<f", raw, offset)[0]
        elif type_id == int(Dat16RelType.SINE_CURVE):
            curve.start_phase, curve.end_phase, curve.frequency, curve.vertical_scaling, curve.vertical_offset = struct.unpack_from(
                "<fffff", raw, offset
            )
        elif type_id != int(Dat16RelType.DEFAULT_DISTANCE_ATTENUATION_CURVE):
            return RelRawItem(index.name_hash, name=name, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
    except struct.error:
        return RelRawItem(index.name_hash, name=name, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
    return curve


def _parse_dat22_item(index: RelIndexHash, raw: bytes, name_by_offset: dict[int, str]) -> RelItem:
    header = _parse_named_item_header(raw, name_by_offset)
    if header is None:
        return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=raw[0] if raw else 0, raw_data=raw)
    type_id, name_table_offset, flags, name = header
    if type_id != int(Dat22RelType.CATEGORY) or len(raw) < 48:
        return RelRawItem(index.name_hash, name=name, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
    fields = struct.unpack_from("<hhhhIhIhhhhhhhhhhBB", raw, 8)
    subcategory_count = fields[-1]
    offset = 48
    subcategories = [
        struct.unpack_from("<I", raw, offset + i * 4)[0]
        for i in range(subcategory_count)
        if offset + i * 4 + 4 <= len(raw)
    ]
    return Dat22Category(
        name_hash=index.name_hash,
        name=name,
        data_offset=index.offset,
        data_length=index.length,
        raw_data=raw,
        name_table_offset=name_table_offset,
        flags=flags,
        parent_overrides=fields[0],
        volume=fields[1],
        pitch=fields[2],
        lpf_cutoff=fields[3],
        lpf_distance_curve=fields[4],
        hpf_cutoff=fields[5],
        hpf_distance_curve=fields[6],
        distance_roll_off_scale=fields[7],
        plateau_roll_off_scale=fields[8],
        occlusion_damping=fields[9],
        environmental_filter_damping=fields[10],
        source_reverb_damping=fields[11],
        distance_reverb_damping=fields[12],
        interior_reverb_damping=fields[13],
        environmental_loudness=fields[14],
        underwater_wet_level=fields[15],
        stoned_wet_level=fields[16],
        timer=fields[17],
        subcategories=subcategories,
    )


def _parse_dat54_child_list(raw: bytes, offset: int) -> tuple[list[int], int]:
    if offset >= len(raw):
        return [], offset
    count = raw[offset]
    offset += 1
    children = [
        struct.unpack_from("<I", raw, offset + i * 4)[0]
        for i in range(count)
        if offset + i * 4 + 4 <= len(raw)
    ]
    return children, offset + count * 4


def _parse_dat54_variable_data(raw: bytes, offset: int) -> tuple[Dat54VariableData | None, int]:
    if offset + 13 > len(raw):
        return None, offset
    name, value, value_variance, variable_type = struct.unpack_from("<IffB", raw, offset)
    return Dat54VariableData(name, value, value_variance, variable_type), offset + 13


def _parse_dat54_math_operation(raw: bytes, offset: int) -> tuple[Dat54MathOperation | None, int]:
    size = struct.calcsize("<BfIfIfII")
    if offset + size > len(raw):
        return None, offset
    values = struct.unpack_from("<BfIfIfII", raw, offset)
    return Dat54MathOperation(*values), offset + size


def _parse_dat54_parameter_transform(raw: bytes, offset: int) -> tuple[Dat54ParameterTransform | None, int]:
    if offset + 24 > len(raw):
        return None, offset
    smooth_rate, transform_type, transform_type_parameter, output_range_min, output_range_max, vector_count = struct.unpack_from(
        "<fiIffi", raw, offset
    )
    offset += 24
    vectors = [
        struct.unpack_from("<ff", raw, offset + i * 8)
        for i in range(max(vector_count, 0))
        if offset + i * 8 + 8 <= len(raw)
    ]
    return (
        Dat54ParameterTransform(
            smooth_rate=smooth_rate,
            transform_type=transform_type,
            transform_type_parameter=transform_type_parameter,
            output_range_min=output_range_min,
            output_range_max=output_range_max,
            vectors=vectors,
        ),
        offset + max(vector_count, 0) * 8,
    )


def _parse_dat54_parameter_transform_block(raw: bytes, offset: int) -> tuple[Dat54ParameterTransformBlock | None, int]:
    if offset + 16 > len(raw):
        return None, offset
    input_parameter, input_range_min, input_range_max, count = struct.unpack_from("<Iffi", raw, offset)
    offset += 16
    transforms: list[Dat54ParameterTransform] = []
    for _ in range(max(count, 0)):
        transform, offset = _parse_dat54_parameter_transform(raw, offset)
        if transform is None:
            break
        transforms.append(transform)
    return (
        Dat54ParameterTransformBlock(
            input_parameter=input_parameter,
            input_range_min=input_range_min,
            input_range_max=input_range_max,
            transforms=transforms,
        ),
        offset,
    )


def _parse_dat54_fluctuator(raw: bytes, offset: int) -> tuple[Dat54Fluctuator | None, int]:
    size = struct.calcsize("<BBI" + "f" * 11)
    if offset + size > len(raw):
        return None, offset
    values = struct.unpack_from("<BBI" + "f" * 11, raw, offset)
    return Dat54Fluctuator(*values), offset + size


def _parse_dat54_item(index: RelIndexHash, raw: bytes) -> RelItem:
    if not raw:
        return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, raw_data=raw)
    type_id = raw[0]
    typed_sound_ids = {
        int(Dat54SoundType.LOOPING_SOUND),
        int(Dat54SoundType.WRAPPER_SOUND),
        int(Dat54SoundType.SEQUENTIAL_SOUND),
        int(Dat54SoundType.STREAMING_SOUND),
        int(Dat54SoundType.SIMPLE_SOUND),
        int(Dat54SoundType.MULTITRACK_SOUND),
        int(Dat54SoundType.RANDOMIZED_SOUND),
        int(Dat54SoundType.MODULAR_SYNTH_SOUND),
        int(Dat54SoundType.VARIABLE_CURVE_SOUND),
        int(Dat54SoundType.IF_SOUND),
        int(Dat54SoundType.AUTOMATION_SOUND),
        int(Dat54SoundType.DIRECTIONAL_SOUND),
        int(Dat54SoundType.KINETIC_SOUND),
        int(Dat54SoundType.VARIABLE_BLOCK_SOUND),
        int(Dat54SoundType.MATH_OPERATION_SOUND),
        int(Dat54SoundType.PARAMETER_TRANSFORM_SOUND),
        int(Dat54SoundType.FLUCTUATOR_SOUND),
        int(Dat54SoundType.EXTERNAL_STREAM_SOUND),
        int(Dat54SoundType.AUTOMATION_NOTE_MAP_SOUND),
        int(Dat54SoundType.SOUND_SET),
        int(Dat54SoundType.SOUND_SET_LIST),
        int(Dat54SoundType.SOUND_HASH_LIST),
    }
    if type_id not in typed_sound_ids:
        return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
    header, header_length = RelSoundHeader.from_bytes(raw, 1)
    offset = 1 + header_length
    if type_id == int(Dat54SoundType.LOOPING_SOUND):
        if offset + 14 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        loop_count, loop_count_variance, loop_point, child_sound, loop_count_variable = struct.unpack_from("<hhhII", raw, offset)
        return Dat54LoopingSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            loop_count=loop_count,
            loop_count_variance=loop_count_variance,
            loop_point=loop_point,
            child_sound=child_sound,
            loop_count_variable=loop_count_variable,
        )
    if type_id == int(Dat54SoundType.SIMPLE_SOUND):
        if offset + 9 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        container_name, file_name, wave_slot_index = struct.unpack_from("<IIB", raw, offset)
        return Dat54SimpleSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            container_name=container_name,
            file_name=file_name,
            wave_slot_index=wave_slot_index,
        )
    if type_id == int(Dat54SoundType.WRAPPER_SOUND):
        if offset + 15 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        child_sound, last_play_time, fallback_sound, min_repeat_time, variable_count = struct.unpack_from("<IiIhB", raw, offset)
        offset += 15
        variables = [
            Dat54WrapperVariable(*struct.unpack_from("<IB", raw, offset + i * 5))
            for i in range(variable_count)
            if offset + i * 5 + 5 <= len(raw)
        ]
        return Dat54WrapperSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sound=child_sound,
            last_play_time=last_play_time,
            fallback_sound=fallback_sound,
            min_repeat_time=min_repeat_time,
            variables=variables,
        )
    if type_id in {
        int(Dat54SoundType.SEQUENTIAL_SOUND),
        int(Dat54SoundType.MULTITRACK_SOUND),
        int(Dat54SoundType.STREAMING_SOUND),
    }:
        duration = 0
        child_offset = 0
        if type_id == int(Dat54SoundType.STREAMING_SOUND):
            if offset + 5 > len(raw):
                return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
            duration = struct.unpack_from("<i", raw, offset)[0]
            offset += 4
            child_offset = 4
        child_sounds, _ = _parse_dat54_child_list(raw, offset)
        cls: type[Dat54ChildListSound]
        if type_id == int(Dat54SoundType.SEQUENTIAL_SOUND):
            cls = Dat54SequentialSound
        elif type_id == int(Dat54SoundType.MULTITRACK_SOUND):
            cls = Dat54MultitrackSound
        else:
            return Dat54StreamingSound(
                name_hash=index.name_hash,
                data_offset=index.offset,
                data_length=index.length,
                raw_data=raw,
                header=header,
                child_sounds=child_sounds,
                child_offset=child_offset,
                duration=duration,
            )
        return cls(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sounds=child_sounds,
            child_offset=child_offset,
        )
    if type_id == int(Dat54SoundType.RANDOMIZED_SOUND):
        if offset + 3 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        history_index = raw[offset]
        history_count = raw[offset + 1]
        offset += 2
        history_space = raw[offset : offset + history_count]
        offset += history_count
        if offset >= len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        variation_count = raw[offset]
        offset += 1
        variations = [
            Dat54RandomizedVariation(*struct.unpack_from("<If", raw, offset + i * 8))
            for i in range(variation_count)
            if offset + i * 8 + 8 <= len(raw)
        ]
        return Dat54RandomizedSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            history_index=history_index,
            history_space=history_space,
            variations=variations,
        )
    if type_id == int(Dat54SoundType.MODULAR_SYNTH_SOUND):
        if offset + 40 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        synth_sound, synth_preset, playback_time_limit, virtualisation_mode, track_count = struct.unpack_from("<IIfii", raw, offset)
        offset += 20
        environment_sounds = list(struct.unpack_from("<4I", raw, offset))
        offset += 16
        exposed_count = struct.unpack_from("<i", raw, offset)[0]
        offset += 4
        exposed_variables = [
            Dat54ModularSynthSoundVariable(*struct.unpack_from("<IIf", raw, offset + i * 12))
            for i in range(exposed_count)
            if offset + i * 12 + 12 <= len(raw)
        ]
        return Dat54ModularSynthSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            synth_sound=synth_sound,
            synth_preset=synth_preset,
            playback_time_limit=playback_time_limit,
            virtualisation_mode=virtualisation_mode,
            track_count=track_count,
            environment_sounds=environment_sounds,
            exposed_variables=exposed_variables,
        )
    if type_id == int(Dat54SoundType.VARIABLE_CURVE_SOUND):
        if offset + 16 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        child_sound, input_variable, output_variable, curve = struct.unpack_from("<IIII", raw, offset)
        return Dat54VariableCurveSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sound=child_sound,
            input_variable=input_variable,
            output_variable=output_variable,
            curve=curve,
        )
    if type_id == int(Dat54SoundType.IF_SOUND):
        if offset + 21 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        true_sound, false_sound, condition_variable, condition_type, condition_value, rhs = struct.unpack_from("<IIIBfI", raw, offset)
        return Dat54IfSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            true_sound=true_sound,
            false_sound=false_sound,
            condition_variable=condition_variable,
            condition_type=condition_type,
            condition_value=condition_value,
            rhs=rhs,
        )
    if type_id == int(Dat54SoundType.DIRECTIONAL_SOUND):
        if offset + 24 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        child_sound, inner_angle, outer_angle, rear_attenuation, yaw_angle, pitch_angle = struct.unpack_from("<Ifffff", raw, offset)
        return Dat54DirectionalSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sound=child_sound,
            inner_angle=inner_angle,
            outer_angle=outer_angle,
            rear_attenuation=rear_attenuation,
            yaw_angle=yaw_angle,
            pitch_angle=pitch_angle,
        )
    if type_id == int(Dat54SoundType.KINETIC_SOUND):
        if offset + 16 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        child_sound, mass, yaw_angle, pitch_angle = struct.unpack_from("<Ifff", raw, offset)
        return Dat54KineticSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sound=child_sound,
            mass=mass,
            yaw_angle=yaw_angle,
            pitch_angle=pitch_angle,
        )
    if type_id == int(Dat54SoundType.VARIABLE_BLOCK_SOUND):
        if offset + 5 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        child_sound = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        count = raw[offset]
        offset += 1
        variables: list[Dat54VariableData] = []
        for _ in range(count):
            variable, offset = _parse_dat54_variable_data(raw, offset)
            if variable is None:
                break
            variables.append(variable)
        return Dat54VariableBlockSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sound=child_sound,
            variables=variables,
        )
    if type_id == int(Dat54SoundType.MATH_OPERATION_SOUND):
        if offset + 8 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        child_sound, count = struct.unpack_from("<Ii", raw, offset)
        offset += 8
        operations: list[Dat54MathOperation] = []
        for _ in range(max(count, 0)):
            operation, offset = _parse_dat54_math_operation(raw, offset)
            if operation is None:
                break
            operations.append(operation)
        return Dat54MathOperationSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sound=child_sound,
            operations=operations,
        )
    if type_id == int(Dat54SoundType.PARAMETER_TRANSFORM_SOUND):
        if offset + 8 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        child_sound, count = struct.unpack_from("<Ii", raw, offset)
        offset += 8
        blocks: list[Dat54ParameterTransformBlock] = []
        for _ in range(max(count, 0)):
            block, offset = _parse_dat54_parameter_transform_block(raw, offset)
            if block is None:
                break
            blocks.append(block)
        return Dat54ParameterTransformSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sound=child_sound,
            parameter_transforms=blocks,
        )
    if type_id == int(Dat54SoundType.FLUCTUATOR_SOUND):
        if offset + 8 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        child_sound, count = struct.unpack_from("<Ii", raw, offset)
        offset += 8
        fluctuators: list[Dat54Fluctuator] = []
        for _ in range(max(count, 0)):
            fluctuator, offset = _parse_dat54_fluctuator(raw, offset)
            if fluctuator is None:
                break
            fluctuators.append(fluctuator)
        return Dat54FluctuatorSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sound=child_sound,
            fluctuators=fluctuators,
        )
    if type_id == int(Dat54SoundType.EXTERNAL_STREAM_SOUND):
        child_sounds, offset = _parse_dat54_child_list(raw, offset)
        if offset + 8 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        environment_sound_1, environment_sound_2 = struct.unpack_from("<II", raw, offset)
        offset += 8
        environment_sound_3 = 0
        environment_sound_4 = 0
        if not child_sounds and offset + 8 <= len(raw):
            environment_sound_3, environment_sound_4 = struct.unpack_from("<II", raw, offset)
        return Dat54ExternalStreamSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            child_sounds=child_sounds,
            environment_sound_1=environment_sound_1,
            environment_sound_2=environment_sound_2,
            environment_sound_3=environment_sound_3,
            environment_sound_4=environment_sound_4,
        )
    if type_id == int(Dat54SoundType.AUTOMATION_SOUND):
        if offset + 32 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        (
            fallback_sound,
            playback_rate,
            playback_rate_variance,
            playback_rate_variable,
            note_map,
            container_name,
            file_name,
            output_count,
        ) = struct.unpack_from("<IffIIIIi", raw, offset)
        offset += 32
        variable_outputs = [
            Dat54AutomationSoundVariableOutput(*struct.unpack_from("<iI", raw, offset + i * 8))
            for i in range(max(output_count, 0))
            if offset + i * 8 + 8 <= len(raw)
        ]
        return Dat54AutomationSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            fallback_sound=fallback_sound,
            playback_rate=playback_rate,
            playback_rate_variance=playback_rate_variance,
            playback_rate_variable=playback_rate_variable,
            note_map=note_map,
            container_name=container_name,
            file_name=file_name,
            variable_outputs=variable_outputs,
        )
    if type_id == int(Dat54SoundType.AUTOMATION_NOTE_MAP_SOUND):
        if offset + 1 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        count = raw[offset]
        offset += 1
        ranges = [
            Dat54AutomationNoteMapRange(*struct.unpack_from("<BBBI", raw, offset + i * 7))
            for i in range(count)
            if offset + i * 7 + 7 <= len(raw)
        ]
        return Dat54AutomationNoteMapSound(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            ranges=ranges,
        )
    if type_id == int(Dat54SoundType.SOUND_SET):
        if offset + 4 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        count = struct.unpack_from("<i", raw, offset)[0]
        offset += 4
        sound_sets = [
            Dat54SoundSetItem(*struct.unpack_from("<II", raw, offset + i * 8))
            for i in range(max(count, 0))
            if offset + i * 8 + 8 <= len(raw)
        ]
        return Dat54SoundSet(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            sound_sets=sound_sets,
        )
    if type_id == int(Dat54SoundType.SOUND_SET_LIST):
        if offset + 4 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        count = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        sound_sets = [
            struct.unpack_from("<I", raw, offset + i * 4)[0]
            for i in range(count)
            if offset + i * 4 + 4 <= len(raw)
        ]
        return Dat54SoundSetList(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            sound_sets=sound_sets,
        )
    if type_id == int(Dat54SoundType.SOUND_HASH_LIST):
        if offset + 6 > len(raw):
            return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)
        unk_short, count = struct.unpack_from("<HI", raw, offset)
        offset += 6
        hashes = [
            struct.unpack_from("<I", raw, offset + i * 4)[0]
            for i in range(count)
            if offset + i * 4 + 4 <= len(raw)
        ]
        return Dat54SoundHashList(
            name_hash=index.name_hash,
            data_offset=index.offset,
            data_length=index.length,
            raw_data=raw,
            header=header,
            unk_short=unk_short,
            sound_hashes_list=hashes,
        )
    return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)


def _parse_item(rel_type: int, index: RelIndexHash, data_block: bytes, name_by_offset: dict[int, str]) -> RelItem:
    raw = data_block[index.offset : index.offset + index.length]
    if rel_type == int(RelDatFileType.DAT10_MODULAR_SYNTH):
        return _parse_dat10_item(index, raw, name_by_offset)
    if rel_type == int(RelDatFileType.DAT16_CURVES):
        return _parse_dat16_item(index, raw, name_by_offset)
    if rel_type == int(RelDatFileType.DAT22_CATEGORIES):
        return _parse_dat22_item(index, raw, name_by_offset)
    if rel_type == int(RelDatFileType.DAT54_DATA_ENTRIES):
        return _parse_dat54_item(index, raw)
    type_id = raw[0] if raw else 0
    return RelRawItem(index.name_hash, data_offset=index.offset, data_length=index.length, type_id=type_id, raw_data=raw)


def read_rel(source: bytes | bytearray | memoryview | str | Path, *, path: str | Path | None = None) -> RelFile:
    data, detected_path = _read_source(source)
    rel_path = str(path) if path is not None else detected_path
    if len(data) < 20:
        raise ValueError("REL data is too short")
    offset = 0
    rel_type_value, data_length = struct.unpack_from("<II", data, offset)
    offset += 8
    data_block = data[offset : offset + data_length]
    if len(data_block) != data_length or len(data_block) < 4:
        raise ValueError("REL data block is truncated")
    version = struct.unpack_from("<I", data_block, 0)[0]
    offset += data_length
    name_table_length, name_table_count = struct.unpack_from("<II", data, offset)
    offset += 8
    names, name_by_offset, offset = _parse_name_table(data, offset, name_table_length, name_table_count)
    index_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    is_audio_config = rel_type_value == int(RelDatFileType.DAT4) and name_table_length == 4
    index_string_flags = 2524
    index_hashes: list[RelIndexHash] = []
    index_strings: list[RelIndexString] = []
    if is_audio_config:
        index_string_flags = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        for _ in range(index_count):
            length = data[offset]
            offset += 1
            name = data[offset : offset + length].decode("ascii", errors="ignore")
            offset += length
            item_offset, item_length = struct.unpack_from("<II", data, offset)
            offset += 8
            index_strings.append(RelIndexString(name, item_offset, item_length))
            index_hashes.append(RelIndexHash(rel_hash(name), item_offset, item_length))
    else:
        for _ in range(index_count):
            name_hash, item_offset, item_length = struct.unpack_from("<III", data, offset)
            offset += 12
            index_hashes.append(RelIndexHash(name_hash, item_offset, item_length))
    hash_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    hash_table_offsets = list(struct.unpack_from("<" + "I" * hash_count, data, offset)) if hash_count else []
    offset += hash_count * 4
    pack_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    pack_table_offsets = list(struct.unpack_from("<" + "I" * pack_count, data, offset)) if pack_count else []
    items = [_parse_item(rel_type_value, index, data_block, name_by_offset) for index in index_hashes]
    return RelFile(
        rel_type=RelDatFileType(rel_type_value),
        version=version,
        items=items,
        name_table=names,
        index_hashes=index_hashes,
        index_strings=index_strings,
        hash_table_offsets=hash_table_offsets,
        pack_table_offsets=pack_table_offsets,
        is_audio_config=is_audio_config,
        index_string_flags=index_string_flags,
        path=rel_path,
    )


def _prepare_name_table(rel: RelFile) -> tuple[list[str], dict[str, int]]:
    names: list[str] = []
    for name in rel.name_table:
        if name not in names:
            names.append(name)
    for item in rel.items:
        if hasattr(item, "name_table_offset") and item.name and item.name not in names:
            names.append(item.name)
    offsets: dict[str, int] = {}
    current = 0
    for name in names:
        offsets[name] = current
        current += len(name.encode("ascii", errors="ignore")) + 1
    for item in rel.items:
        if hasattr(item, "name_table_offset") and item.name:
            item.name_table_offset = offsets[item.name]  # type: ignore[attr-defined]
    return names, offsets


def _data_order_items(rel: RelFile) -> list[RelItem]:
    if any(item.data_offset for item in rel.items):
        return sorted(rel.items, key=lambda item: item.data_offset)
    return list(rel.items)


def _build_data_block(rel: RelFile) -> bytes:
    data = bytearray(struct.pack("<I", rel.version & 0xFFFFFFFF))
    for item in _data_order_items(rel):
        if int(rel.rel_type) == int(RelDatFileType.DAT10_MODULAR_SYNTH):
            aligned = align(len(data), 4)
            data += b"\x00" * (aligned - len(data))
        item_data = item.to_data()
        item.data_offset = len(data)
        item.data_length = len(item_data)
        if item_data:
            item.type_id = item_data[0]
        data += item_data
    return bytes(data)


def _hash_offset_base(item: RelItem) -> int:
    base = item.data_offset + 8
    if hasattr(item, "hash_base_adjustment"):
        base += item.hash_base_adjustment()  # type: ignore[attr-defined]
    else:
        base += 4
    return base


def _remap_existing_table(source_offsets: list[int], old_ranges: list[tuple[RelItem, int, int]]) -> list[int]:
    remapped: list[int] = []
    for table_offset in source_offsets:
        data_relative = table_offset - 8
        for item, old_offset, old_length in old_ranges:
            if old_offset <= data_relative < old_offset + old_length:
                remapped.append(table_offset + item.data_offset - old_offset)
                break
    return remapped


def _build_table_offsets(rel: RelFile, *, pack: bool, old_ranges: list[tuple[RelItem, int, int]]) -> list[int]:
    offsets = _remap_existing_table(rel.pack_table_offsets if pack else rel.hash_table_offsets, old_ranges)
    for item in _data_order_items(rel):
        item_offsets = item.pack_table_offsets() if pack else item.hash_table_offsets()
        for value in item_offsets:
            table_offset = _hash_offset_base(item) + int(value)
            if table_offset not in offsets:
                offsets.append(table_offset)
    return offsets


def _write_name_table(output: bytearray, names: list[str]) -> None:
    if not names:
        output += struct.pack("<II", 4, 0)
        return
    encoded = [name.encode("ascii", errors="ignore") + b"\x00" for name in names]
    length = 4 + len(names) * 4 + sum(len(value) for value in encoded)
    output += struct.pack("<II", length, len(names))
    rel_offset = 0
    for value in encoded:
        output += struct.pack("<I", rel_offset)
        rel_offset += len(value)
    for value in encoded:
        output += value


def build_rel_bytes(rel: RelFile) -> bytes:
    old_ranges = [(item, item.data_offset, item.data_length) for item in rel.items]
    names, _ = _prepare_name_table(rel)
    data_block = _build_data_block(rel)
    index_items = rel.sorted_index_items()
    output = bytearray(struct.pack("<II", int(rel.rel_type), len(data_block)))
    output += data_block
    _write_name_table(output, names)
    output += struct.pack("<I", len(index_items))
    if rel.is_audio_config:
        output += struct.pack("<I", rel.index_string_flags)
        for item in index_items:
            name = item.name or f"0x{item.name_hash:08X}"
            encoded = name.encode("ascii", errors="ignore")
            if len(encoded) > 255:
                raise ValueError(f"REL index string is too long: {name}")
            output += bytes([len(encoded)])
            output += encoded
            output += struct.pack("<II", item.data_offset, item.data_length)
    else:
        for item in index_items:
            output += struct.pack("<III", item.name_hash & 0xFFFFFFFF, item.data_offset, item.data_length)
    hash_table = _build_table_offsets(rel, pack=False, old_ranges=old_ranges)
    output += struct.pack("<I", len(hash_table))
    output += b"".join(struct.pack("<I", value & 0xFFFFFFFF) for value in hash_table)
    pack_table = _build_table_offsets(rel, pack=True, old_ranges=old_ranges)
    output += struct.pack("<I", len(pack_table))
    output += b"".join(struct.pack("<I", value & 0xFFFFFFFF) for value in pack_table)
    return bytes(output)


def save_rel(rel: RelFile, path: str | Path | None = None) -> Path:
    return rel.save(path)
