from __future__ import annotations

import struct

from .enums import Dat54SoundType
from .sound_types import (
    Dat54CollapsingStereoSound,
    Dat54CrossfadeSound,
    Dat54DynamicEntitySound,
    Dat54EnvelopeSound,
    Dat54EnvironmentSound,
    Dat54GranularChannel,
    Dat54GranularChannelSettings,
    Dat54GranularSound,
    Dat54OnStopSound,
    Dat54RetriggeredOverlappedSound,
    Dat54SequentialOverlapSound,
    Dat54SpeechSound,
    Dat54SwitchSound,
    Dat54TwinLoopSound,
    Dat54VariablePrintValueSound,
)

ADDITIONAL_DAT54_SOUND_TYPES = frozenset(
    {
        int(Dat54SoundType.ENVELOPE_SOUND),
        int(Dat54SoundType.TWIN_LOOP_SOUND),
        int(Dat54SoundType.SPEECH_SOUND),
        int(Dat54SoundType.ON_STOP_SOUND),
        int(Dat54SoundType.RETRIGGERED_OVERLAPPED_SOUND),
        int(Dat54SoundType.CROSSFADE_SOUND),
        int(Dat54SoundType.COLLAPSING_STEREO_SOUND),
        int(Dat54SoundType.ENVIRONMENT_SOUND),
        int(Dat54SoundType.DYNAMIC_ENTITY_SOUND),
        int(Dat54SoundType.SEQUENTIAL_OVERLAP_SOUND),
        int(Dat54SoundType.GRANULAR_SOUND),
        int(Dat54SoundType.SWITCH_SOUND),
        int(Dat54SoundType.VARIABLE_PRINT_VALUE_SOUND),
    }
)


def _counted_hashes(
    data: bytes,
    offset: int,
    maximum: int,
) -> tuple[list[int], int]:
    if offset >= len(data):
        raise ValueError("missing count")
    count = data[offset]
    if count > maximum or offset + 1 + count * 4 > len(data):
        raise ValueError("invalid counted hash array")
    offset += 1
    return list(struct.unpack_from(f"<{count}I", data, offset)), offset + count * 4


def _text_u8(data: bytes, offset: int) -> tuple[str, int]:
    if offset >= len(data):
        raise ValueError("missing text length")
    length = data[offset]
    offset += 1
    if offset + length > len(data):
        raise ValueError("invalid text length")
    return data[offset : offset + length].decode("utf-8"), offset + length


def parse_additional_dat54_sound(
    type_id: int,
    data: bytes,
) -> (
    Dat54EnvelopeSound
    | Dat54TwinLoopSound
    | Dat54SpeechSound
    | Dat54OnStopSound
    | Dat54RetriggeredOverlappedSound
    | Dat54CrossfadeSound
    | Dat54CollapsingStereoSound
    | Dat54EnvironmentSound
    | Dat54DynamicEntitySound
    | Dat54SequentialOverlapSound
    | Dat54GranularSound
    | Dat54SwitchSound
    | Dat54VariablePrintValueSound
    | None
):
    try:
        if type_id == int(Dat54SoundType.ENVELOPE_SOUND):
            values = struct.unpack_from("<HHHHBBiHiI3I5IIB3xIff", data)
            return Dat54EnvelopeSound(
                attack=values[0],
                attack_variance=values[1],
                decay=values[2],
                decay_variance=values[3],
                sustain=values[4],
                sustain_variance=values[5],
                hold=values[6],
                hold_variance=values[7],
                release=values[8],
                release_variance=values[9],
                attack_curve=values[10],
                decay_curve=values[11],
                release_curve=values[12],
                attack_variable=values[13],
                decay_variable=values[14],
                sustain_variable=values[15],
                hold_variable=values[16],
                release_variable=values[17],
                child_sound=values[18],
                mode=values[19],
                output_variable=values[20],
                output_range_min=values[21],
                output_range_max=values[22],
            )
        if type_id == int(Dat54SoundType.TWIN_LOOP_SOUND):
            values = struct.unpack_from("<HHHH5I", data)
            children, _ = _counted_hashes(data, 28, 2)
            return Dat54TwinLoopSound(
                min_swap_time=values[0],
                max_swap_time=values[1],
                min_crossfade_time=values[2],
                max_crossfade_time=values[3],
                crossfade_curve=values[4],
                min_swap_time_variable=values[5],
                max_swap_time_variable=values[6],
                min_crossfade_time_variable=values[7],
                max_crossfade_time_variable=values[8],
                child_sounds=children,
            )
        if type_id == int(Dat54SoundType.SPEECH_SOUND):
            last_variation, dynamic_field_name, voice_name = struct.unpack_from(
                "<III", data
            )
            context_name, _ = _text_u8(data, 12)
            return Dat54SpeechSound(
                last_variation=last_variation,
                dynamic_field_name=dynamic_field_name,
                voice_name=voice_name,
                context_name=context_name,
            )
        if type_id == int(Dat54SoundType.ON_STOP_SOUND):
            child_sound, stop_sound, finished_sound = struct.unpack_from("<III", data)
            return Dat54OnStopSound(
                child_sound=child_sound,
                stop_sound=stop_sound,
                finished_sound=finished_sound,
            )
        if type_id == int(Dat54SoundType.RETRIGGERED_OVERLAPPED_SOUND):
            values = struct.unpack_from("<hHHH5I", data)
            return Dat54RetriggeredOverlappedSound(
                loop_count=values[0],
                loop_count_variance=values[1],
                delay_time=values[2],
                delay_time_variance=values[3],
                loop_count_variable=values[4],
                delay_time_variable=values[5],
                start_sound=values[6],
                retrigger_sound=values[7],
                stop_sound=values[8],
            )
        if type_id == int(Dat54SoundType.CROSSFADE_SOUND):
            values = struct.unpack_from("<IIBfff6I", data)
            return Dat54CrossfadeSound(
                near_sound=values[0],
                far_sound=values[1],
                mode=values[2],
                min_distance=values[3],
                max_distance=values[4],
                hysteresis=values[5],
                crossfade_curve=values[6],
                distance_variable=values[7],
                min_distance_variable=values[8],
                max_distance_variable=values[9],
                hysteresis_variable=values[10],
                crossfade_variable=values[11],
            )
        if type_id == int(Dat54SoundType.COLLAPSING_STEREO_SOUND):
            values = struct.unpack_from("<IIff5IfIB", data)
            return Dat54CollapsingStereoSound(
                left_sound=values[0],
                right_sound=values[1],
                min_distance=values[2],
                max_distance=values[3],
                min_distance_variable=values[4],
                max_distance_variable=values[5],
                crossfade_override_variable=values[6],
                frontend_left_pan_variable=values[7],
                frontend_right_pan_variable=values[8],
                position_relative_pan_damping=values[9],
                position_relative_pan_damping_variable=values[10],
                mode=values[11],
            )
        if type_id == int(Dat54SoundType.ENVIRONMENT_SOUND):
            return Dat54EnvironmentSound(channel_id=struct.unpack_from("<B", data)[0])
        if type_id == int(Dat54SoundType.DYNAMIC_ENTITY_SOUND):
            entities, _ = _counted_hashes(data, 0, 8)
            return Dat54DynamicEntitySound(entities=entities)
        if type_id == int(Dat54SoundType.SEQUENTIAL_OVERLAP_SOUND):
            delay_time, delay_variable, direction = struct.unpack_from("<HII", data)
            children, _ = _counted_hashes(data, 10, 254)
            return Dat54SequentialOverlapSound(
                delay_time=delay_time,
                delay_time_variable=delay_variable,
                sequence_direction=direction,
                child_sounds=children,
            )
        if type_id == int(Dat54SoundType.GRANULAR_SOUND):
            if len(data) < 125:
                return None
            channels = [
                Dat54GranularChannel(*struct.unpack_from("<II", data, 4 + index * 8))
                for index in range(6)
            ]
            settings = [
                Dat54GranularChannelSettings(
                    *struct.unpack_from("<BBBBf", data, 52 + index * 8)
                )
                for index in range(6)
            ]
            change_rate, pitch_fraction = struct.unpack_from("<ff", data, 100)
            volumes = list(struct.unpack_from("<6h", data, 108))
            parent_sound = struct.unpack_from("<I", data, 120)[0]
            count = data[124]
            if count > 2 or 125 + count * 8 > len(data):
                return None
            clocks = [
                struct.unpack_from("<ff", data, 125 + index * 8)
                for index in range(count)
            ]
            return Dat54GranularSound(
                wave_slot_index=struct.unpack_from("<I", data)[0],
                channels=channels,
                channel_settings=settings,
                loop_randomisation_change_rate=change_rate,
                loop_randomisation_pitch_fraction=pitch_fraction,
                channel_volumes=volumes,
                parent_sound=parent_sound,
                granular_clocks=clocks,
            )
        if type_id == int(Dat54SoundType.SWITCH_SOUND):
            variable = struct.unpack_from("<I", data)[0]
            children, _ = _counted_hashes(data, 4, 32)
            return Dat54SwitchSound(variable=variable, child_sounds=children)
        if type_id == int(Dat54SoundType.VARIABLE_PRINT_VALUE_SOUND):
            variable = struct.unpack_from("<I", data)[0]
            message, _ = _text_u8(data, 4)
            return Dat54VariablePrintValueSound(variable=variable, message=message)
    except (UnicodeDecodeError, ValueError, struct.error):
        return None
    return None


__all__ = ["ADDITIONAL_DAT54_SOUND_TYPES", "parse_additional_dat54_sound"]
