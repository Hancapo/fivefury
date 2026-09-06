from __future__ import annotations

from fivefury.pso import (
    PMAP,
    PSIN,
    PsoBlockBuilder,
    PsoEntry,
    PsoEnum,
    PsoEnumEntry,
    PsoStruct,
    build_pmap_section,
    build_psin_section,
    parse_pmap,
    parse_psch,
    parse_psch_enums,
    parse_sections,
    serialize_psch,
)


def test_psch_roundtrip_preserves_structs_and_enums() -> None:
    struct_hash = 0x11223344
    enum_hash = 0x55667788
    data = serialize_psch(
        {
            struct_hash: PsoStruct(
                name_hash=struct_hash,
                length=4,
                entries=[PsoEntry(0xAABBCCDD, 0x0F, 0, 0, enum_hash)],
            )
        },
        {
            enum_hash: PsoEnum(
                name_hash=enum_hash,
                entries=[PsoEnumEntry(0x12345678, 0), PsoEnumEntry(0x87654321, 4)],
            )
        },
    )

    assert list(parse_psch(data)) == [struct_hash]
    assert parse_psch(data)[struct_hash].entries[0].reference_key == enum_hash
    assert [
        (entry.name_hash, entry.value)
        for entry in parse_psch_enums(data)[enum_hash].entries
    ] == [
        (0x12345678, 0),
        (0x87654321, 4),
    ]


def test_pso_writer_aligns_default_blocks_to_16_bytes() -> None:
    blocks = [
        PsoBlockBuilder(name_hash=0x11111111, data=bytearray(b"abcde")),
        PsoBlockBuilder(name_hash=0x22222222, data=bytearray(range(24))),
        PsoBlockBuilder(name_hash=0x33333333, data=bytearray(b"xyz")),
    ]
    data = build_psin_section(blocks) + build_pmap_section(blocks, root_block_id=1)
    sections = parse_sections(data)
    parsed, root_block_id = parse_pmap(sections[PMAP])

    assert root_block_id == 1
    assert [block.offset for block in parsed.values()] == [0x10, 0x20, 0x40]
    assert [block.length for block in parsed.values()] == [5, 24, 3]
    assert sections[PSIN][0x10:0x15] == b"abcde"
    assert sections[PSIN][0x20:0x38] == bytes(range(24))
    assert sections[PSIN][0x40:0x43] == b"xyz"
    assert sections[PSIN][0x15:0x20] == bytes(11)
    assert sections[PSIN][0x38:0x40] == bytes(8)
