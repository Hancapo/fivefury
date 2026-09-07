import copy
import struct

import pytest

from fivefury import (
    GameTarget,
    MetaHash,
    Vector4,
    YedExpression,
    YedInstruction,
    YedSpring,
    create_yed,
    read_yed,
)
from fivefury import YedInstructionType as Op
from fivefury.resource import (
    ResourceBlockSpan,
    build_rsc7,
    get_resource_chunk_sizes,
    split_rsc7_sections,
    validate_resource_block_layout,
)
from fivefury.yed.constants import SPRING_BLOCK_SIZE
from tests.support.yed import assert_scattered_yed, large_expression


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_large_alias_dictionary_survives_scattered_allocations_without_semantic_changes(
    game,
):
    source = create_yed(large_expression(), game=game)
    for index in range(11):
        source.clone_expression("calibrated", f"component_{index}")
    tuning = YedExpression.create("tuning")
    tuning.springs = [YedSpring(bytes(SPRING_BLOCK_SIZE)) for _ in range(70)]
    tuning.variables = [MetaHash(0x50000000 + i * 16) for i in range(20)]
    source.expressions.append(tuning)
    source.graphics_data = b"opaque" * 300
    before = copy.deepcopy(source)
    raw = source.to_bytes()
    reread = read_yed(raw)
    assert reread.game == game
    assert len(get_resource_chunk_sizes(reread.system_flags)) > 6
    assert reread.validate().valid
    assert reread.to_bytes() == raw
    assert reread.graphics_data.startswith(source.graphics_data)
    assert_scattered_yed(raw, before)


def test_pointer_shaped_instruction_literals_are_not_relocated():
    expression = large_expression()
    value = struct.unpack("<f", struct.pack("<I", 0x500006A0))[0]
    expression.streams[0].instructions[0] = YedInstruction(
        Op.PUSH_VECTOR, operands={"value": Vector4(value, 0, 0, 0)}
    )
    expression.recalculate_runtime_contract()
    source = create_yed(expression)
    raw = source.to_bytes()
    assert_scattered_yed(raw, source)
    assert (
        struct.pack("<Q", 0x500006A0) in read_yed(raw).expressions[0].streams[0].data1
    )


def crossing_import(game, field):
    # The former flat writer could split an owned block while retaining valid pointers.
    source = read_yed(create_yed(large_expression(), game=game).to_bytes())
    header, data, graphics = split_rsc7_sections(source.to_bytes())
    system = bytearray(data)
    expression = source.expressions[0]
    if field == "tracks":
        original = expression.tracks_info.pointer - 0x50000000
        payload = system[original : original + len(expression.tracks) * 4]
        pointer_field = expression.offset + 0x30
    else:
        stream = expression.streams[0]
        payload = stream.raw
        pointer_field = expression.streams_info.pointer - 0x50000000
    boundary = len(system)
    start = boundary - 32
    system.extend(bytes(len(payload)))
    system[start : start + len(payload)] = payload
    struct.pack_into("<Q", system, pointer_field, 0x50000000 + start)
    # A power-of-two section followed by a tail is encoded as separate chunks.
    return read_yed(
        build_rsc7(bytes(system), version=header.version, graphics_data=graphics)
    )


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize("field", ["tracks", "streams"])
def test_unsafe_import_is_inspectable_but_cannot_bypass_atomic_export(
    game, field, tmp_path
):
    imported = crossing_import(game, field)
    assert imported.validate_runtime_contract().valid
    assert "resource.block.crosses_chunk" in {i.code for i in imported.validate()}
    target = tmp_path / "existing.yed"
    target.write_bytes(b"original")
    with pytest.raises(ValueError, match="resource.block.crosses_chunk"):
        imported.save(target)
    assert target.read_bytes() == b"original"
    imported.recalculate_runtime_contract()
    repaired = imported.to_bytes()
    assert read_yed(repaired).validate().valid
    assert_scattered_yed(repaired, imported)


def test_chunk_validation_reports_boundary_and_section_overflow():
    flags = 0x04000000 | 0x08000000  # Two independent chunks, 1 KiB then 512 bytes.
    report = validate_resource_block_layout(
        {
            "exact": ResourceBlockSpan(0, 1024),
            "cross": ResourceBlockSpan(1008, 32),
            "outside": ResourceBlockSpan(1536, 1),
        },
        flags,
    )
    assert [(i.code, i.path) for i in report] == [
        ("resource.block.crosses_chunk", "cross"),
        ("resource.block.range", "outside"),
    ]


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("pages", "yed.resource.pages.count"),
        ("null_pages", "yed.resource.pointer"),
        ("name", "yed.resource.name.capacity"),
        ("streams", "yed.resource.count"),
        ("alignment", "yed.resource.alignment"),
    ],
)
def test_binary_metadata_errors_are_reported_before_export(game, field, code, tmp_path):
    raw = create_yed(large_expression(), game=game).to_bytes()
    source = read_yed(raw)
    header, data, graphics = split_rsc7_sections(raw)
    system = bytearray(data)
    expression = source.expressions[0]
    if field == "pages":
        system[source.dictionary.pages_info_pointer - 0x50000000 + 8] = 0
    elif field == "null_pages":
        struct.pack_into("<Q", system, 8, 0)
    elif field == "name":
        struct.pack_into("<H", system, expression.offset + 0x6A, 1)
    elif field == "streams":
        struct.pack_into("<H", system, expression.offset + 0x2A, 0)
    else:
        stream = expression.streams[0]
        start = len(system) + 1
        system.extend(b"\0" + stream.raw)
        struct.pack_into(
            "<Q",
            system,
            expression.streams_info.pointer - 0x50000000,
            0x50000000 + start,
        )
    imported = read_yed(
        build_rsc7(bytes(system), version=header.version, graphics_data=graphics)
    )
    assert imported.validate_runtime_contract().valid
    assert code in {issue.code for issue in imported.validate().errors}
    target = tmp_path / "rejected.yed"
    with pytest.raises(ValueError, match=code):
        imported.save(target)
    assert not target.exists()
