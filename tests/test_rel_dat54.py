from __future__ import annotations

import pytest

from fivefury import (
    Dat54AutomationSound,
    Dat54AutomationSoundVariableOutput,
    Dat54CollapsingStereoSound,
    Dat54CrossfadeSound,
    Dat54DynamicEntitySound,
    Dat54EnvelopeSound,
    Dat54EnvironmentSound,
    Dat54Fluctuator,
    Dat54FluctuatorSound,
    Dat54GranularChannel,
    Dat54GranularChannelSettings,
    Dat54GranularSound,
    Dat54LoopingSound,
    Dat54MathOperation,
    Dat54MathOperationSound,
    Dat54ModularSynthSound,
    Dat54OnStopSound,
    Dat54ParameterTransform,
    Dat54ParameterTransformBlock,
    Dat54ParameterTransformSound,
    Dat54RetriggeredOverlappedSound,
    Dat54SequentialOverlapSound,
    Dat54SoundHashList,
    Dat54SoundSet,
    Dat54SoundSetItem,
    Dat54SoundSetList,
    Dat54SpeechSound,
    Dat54StreamingSound,
    Dat54SwitchSound,
    Dat54TwinLoopSound,
    Dat54VariablePrintValueSound,
    Dat54WrapperSound,
    Dat54WrapperVariable,
    RelDatFileType,
    RelFile,
    RelSoundIndex,
    build_rel_bytes,
    read_rel,
)

_SOUNDS = (
    Dat54EnvelopeSound(
        name_hash=0x1001,
        attack=10,
        decay=20,
        sustain=80,
        hold=30,
        release=40,
        attack_curve=0x2001,
        decay_curve=0x2002,
        release_curve=0x2003,
        child_sound=0x3001,
        mode=2,
        output_range_min=-1.0,
        output_range_max=1.0,
    ),
    Dat54TwinLoopSound(
        name_hash=0x1002,
        min_swap_time=100,
        max_swap_time=200,
        crossfade_curve=0x2004,
        child_sounds=[0x3002, 0x3003],
    ),
    Dat54SpeechSound(
        name_hash=0x1003,
        last_variation=4,
        dynamic_field_name=0x2005,
        voice_name=0x2006,
        context_name="MISSION_INTRO",
    ),
    Dat54OnStopSound(
        name_hash=0x1004,
        child_sound=0x3004,
        stop_sound=0x3005,
        finished_sound=0x3006,
    ),
    Dat54RetriggeredOverlappedSound(
        name_hash=0x1005,
        loop_count=3,
        delay_time=125,
        start_sound=0x3007,
        retrigger_sound=0x3008,
        stop_sound=0x3009,
    ),
    Dat54CrossfadeSound(
        name_hash=0x1006,
        near_sound=0x3010,
        far_sound=0x3011,
        mode=1,
        min_distance=5.0,
        max_distance=50.0,
        hysteresis=0.25,
        crossfade_curve=0x2007,
    ),
    Dat54CollapsingStereoSound(
        name_hash=0x1007,
        left_sound=0x3012,
        right_sound=0x3013,
        min_distance=2.0,
        max_distance=20.0,
        position_relative_pan_damping=0.75,
        mode=2,
    ),
    Dat54EnvironmentSound(name_hash=0x1008, channel_id=3),
    Dat54DynamicEntitySound(
        name_hash=0x1009,
        entities=[0x4001, 0x4002],
    ),
    Dat54SequentialOverlapSound(
        name_hash=0x1010,
        delay_time=75,
        sequence_direction=0x2008,
        child_sounds=[0x3014, 0x3015],
    ),
    Dat54GranularSound(
        name_hash=0x1011,
        wave_slot_index=2,
        channels=[
            Dat54GranularChannel(0x5001, 0x6001),
            Dat54GranularChannel(0x5002, 0x6002),
        ],
        channel_settings=[
            Dat54GranularChannelSettings(max_loop_proportion=0.5),
        ],
        channel_volumes=[-100, -200],
        parent_sound=0x3016,
        granular_clocks=[(0.5, 1.5), (1.0, 2.0)],
    ),
    Dat54SwitchSound(
        name_hash=0x1012,
        variable=0x2009,
        child_sounds=[0x3017, 0x3018, 0x3019],
    ),
    Dat54VariablePrintValueSound(
        name_hash=0x1013,
        variable=0x2010,
        message="speed",
    ),
)


@pytest.mark.parametrize("sound", _SOUNDS, ids=lambda sound: type(sound).__name__)
def test_remaining_dat54_sound_types_roundtrip(sound: object) -> None:
    original = RelFile(RelDatFileType.DAT54_DATA_ENTRIES, items=[sound])

    data = build_rel_bytes(original)
    parsed = read_rel(data)

    assert type(parsed.items[0]) is type(sound)
    assert build_rel_bytes(parsed) == data


def test_granular_sound_graph_exposes_all_awc_endpoints() -> None:
    sound = Dat54GranularSound(
        name_hash=0x1234,
        channels=[
            Dat54GranularChannel(0x5001, 0x6001),
            Dat54GranularChannel(0x5002, 0x6002),
        ],
    )

    graph = RelSoundIndex(
        [RelFile(RelDatFileType.DAT54_DATA_ENTRIES, items=[sound])]
    ).resolve(0x1234)

    assert [(item.container_hash, item.stream_hash) for item in graph.endpoints] == [
        (0x5001, 0x6001),
        (0x5002, 0x6002),
    ]


def test_dat54_sound_reference_tables_point_into_typed_payloads() -> None:
    sound = Dat54GranularSound(
        name_hash=0x1234,
        channels=[Dat54GranularChannel(0x5001, 0x6001)],
        parent_sound=0x3001,
    )

    parsed = read_rel(
        build_rel_bytes(RelFile(RelDatFileType.DAT54_DATA_ENTRIES, items=[sound]))
    )
    item = parsed.items[0]
    payload_base = item.data_offset + 8 + 1 + item.header.byte_length()

    assert parsed.hash_table_offsets == [payload_base + 120]
    assert parsed.pack_table_offsets == [
        payload_base + offset for offset in (4, 12, 20, 28, 36, 44)
    ]


def test_dat54_count_limits_are_not_silently_truncated() -> None:
    sound = Dat54SwitchSound(child_sounds=list(range(33)))

    with pytest.raises(ValueError, match="at most 32"):
        sound.sound_payload_bytes()


def test_existing_dat54_sound_layouts_preserve_runtime_field_widths() -> None:
    sounds = [
        Dat54LoopingSound(
            name_hash=0x2001,
            loop_count=-1,
            loop_count_variance=0xFFFF,
            loop_point=0xFFFE,
        ),
        Dat54WrapperSound(
            name_hash=0x2002,
            last_play_time=0xFFFFFFFF,
            min_repeat_time=0xFFFF,
            variables=[Dat54WrapperVariable(0x3001, 2)],
        ),
        Dat54StreamingSound(name_hash=0x2003, duration=0xFFFFFFFF),
        Dat54ModularSynthSound(
            name_hash=0x2004,
            virtualisation_mode=1,
            environment_sound_count=1,
            environment_sounds=[0x3002],
        ),
        Dat54MathOperationSound(
            name_hash=0x2005,
            operations=[Dat54MathOperation(operation_type=3)],
        ),
        Dat54ParameterTransformSound(
            name_hash=0x2006,
            parameter_transforms=[
                Dat54ParameterTransformBlock(
                    transforms=[
                        Dat54ParameterTransform(
                            destination=2,
                            output_variable=0x3003,
                            vectors=[(0.0, 1.0)],
                        )
                    ]
                )
            ],
        ),
        Dat54FluctuatorSound(
            name_hash=0x2007,
            fluctuators=[
                Dat54Fluctuator(
                    min_switch_time=125,
                    max_switch_time=0xFFFFFFFF,
                )
            ],
        ),
        Dat54AutomationSound(
            name_hash=0x2008,
            variable_outputs=[Dat54AutomationSoundVariableOutput(0xFFFFFFFF, 0x3004)],
        ),
        Dat54SoundHashList(
            name_hash=0x2009,
            current_sound_index=0xFFFF,
            sound_hashes_list=[0x3005],
        ),
    ]

    original = RelFile(RelDatFileType.DAT54_DATA_ENTRIES, items=sounds)
    data = build_rel_bytes(original)
    parsed = read_rel(data)

    assert build_rel_bytes(parsed) == data
    assert parsed.items[0].loop_count_variance == 0xFFFF
    assert parsed.items[1].last_play_time == 0xFFFFFFFF
    assert parsed.items[2].duration == 0xFFFFFFFF
    assert parsed.items[3].environment_sound_count == 1
    assert len(parsed.items[4].sound_payload_bytes()) == 34
    assert parsed.items[5].parameter_transforms[0].transforms[0].destination == 2
    assert parsed.items[6].fluctuators[0].max_switch_time == 0xFFFFFFFF
    assert parsed.items[7].variable_outputs[0].channel == 0xFFFFFFFF
    assert parsed.items[8].current_sound_index == 0xFFFF


@pytest.mark.parametrize(
    "sound",
    (
        Dat54WrapperSound(variables=[Dat54WrapperVariable(0)] * 9),
        Dat54ModularSynthSound(environment_sounds=[0] * 5),
        Dat54MathOperationSound(operations=[Dat54MathOperation()] * 11),
        Dat54ParameterTransformSound(
            parameter_transforms=[Dat54ParameterTransformBlock()] * 17
        ),
        Dat54ParameterTransformBlock(
            transforms=[Dat54ParameterTransform()] * 5
        ),
        Dat54ParameterTransform(vectors=[(0.0, 0.0)] * 17),
        Dat54FluctuatorSound(fluctuators=[Dat54Fluctuator()] * 5),
        Dat54AutomationSound(
            variable_outputs=[Dat54AutomationSoundVariableOutput()] * 9
        ),
        Dat54SoundSet(sound_sets=[Dat54SoundSetItem(0, 0)] * 1001),
        Dat54SoundSetList(sound_sets=[0] * 65536),
        Dat54SoundHashList(sound_hashes_list=[0] * 65536),
    ),
    ids=lambda sound: type(sound).__name__,
)
def test_existing_dat54_runtime_limits_are_enforced(sound: object) -> None:
    with pytest.raises(ValueError, match="at most"):
        sound.to_bytes() if hasattr(sound, "to_bytes") else sound.sound_payload_bytes()
