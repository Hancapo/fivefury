from __future__ import annotations

from fivefury.pso import (
    PsoEntry,
    PsoEnum,
    PsoEnumEntry,
    PsoStruct,
    parse_psch,
    parse_psch_enums,
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
