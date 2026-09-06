from __future__ import annotations

import struct
import zlib

import pytest

from fivefury.resource import (
    RSC7_MAGIC,
    ResourceBlockSpan,
    ResourceWriter,
    decompress_resource_stream,
    get_resource_flags_from_size,
    layout_resource_sections,
    parse_rsc7,
    prepare_rsc7_sections,
    read_rsc7_header,
)


@pytest.mark.parametrize("version", [5, 13, 165])
def test_prepare_resource_sections_preserves_padding_and_explicit_flags(version):
    sections = prepare_rsc7_sections(
        b"system", version=version, graphics_data=b"graphics",
        system_alignment=0x200, graphics_alignment=0x200,
    )
    assert sections.system_data == b"system".ljust(sections.header.system_size, b"\0")
    assert sections.graphics_data == b"graphics".ljust(sections.header.graphics_size, b"\0")
    assert prepare_rsc7_sections(
        sections.system_data, version=version, graphics_data=sections.graphics_data,
        system_flags=sections.header.system_flags, graphics_flags=sections.header.graphics_flags,
    ) == sections
    header, payload = parse_rsc7(sections.to_bytes())
    assert header == sections.header
    assert payload == sections.system_data + sections.graphics_data


@pytest.mark.parametrize("section", ["system", "graphics"])
def test_prepare_resource_sections_rejects_undersized_flags(section):
    with pytest.raises(ValueError, match=f"{section}_data is larger"):
        prepare_rsc7_sections(b"system", graphics_data=b"graphics", **{f"{section}_flags": 0})


def _compress_with_zero_history(data: bytes) -> bytes:
    compressor = zlib.compressobj(
        level=9,
        wbits=-15,
        zdict=b"\0" * 32768,
    )
    return compressor.compress(data) + compressor.flush()


def test_resource_stream_accepts_zero_initialized_deflate_history():
    compressed = _compress_with_zero_history(b"\0" * 32)
    flags = get_resource_flags_from_size(8192, 5)
    raw = struct.pack("<4I", RSC7_MAGIC, 5, flags, 0) + compressed

    header, payload = parse_rsc7(raw)

    assert header.version == 5
    assert header.total_size == 8192
    assert payload == b"\0" * 32


@pytest.mark.parametrize("version", [165, 171])
def test_resource_header_reader_decodes_without_inflating(version: int) -> None:
    system_flags = get_resource_flags_from_size(8192, version)
    graphics_flags = get_resource_flags_from_size(4096, version)
    data = struct.pack("<4I", RSC7_MAGIC, version, system_flags, graphics_flags)

    header = read_rsc7_header(data)

    assert header.version == version
    assert header.system_flags == system_flags
    assert header.graphics_flags == graphics_flags


def test_resource_header_reader_rejects_short_or_invalid_data() -> None:
    with pytest.raises(ValueError, match="too short"):
        read_rsc7_header(b"RSC7")
    with pytest.raises(ValueError, match="does not start"):
        read_rsc7_header(b"BAD!" + b"\0" * 12)


def test_resource_stream_rejects_trailing_data():
    compressed = zlib.compress(b"payload", level=9, wbits=-15)

    with pytest.raises(ValueError, match="trailing data"):
        decompress_resource_stream(compressed + b"extra")


def test_resource_layout_relocates_only_declared_pointer_fields():
    data = bytearray(0x140)
    address_shaped_scalar = 0x50000020
    struct.pack_into("Q", data, 0x00, address_shaped_scalar)
    struct.pack_into("Q", data, 0x08, 0x50000020)

    system, _, _, _ = layout_resource_sections(
        data,
        [
            ResourceBlockSpan(0x00, 0x20, pointer_offsets=(0x08,)),
            ResourceBlockSpan(0x40, 0x100, relocate_pointers=False),
            ResourceBlockSpan(0x20, 0x20, relocate_pointers=False),
        ],
        version=46,
    )

    assert struct.unpack_from("Q", system, 0x00)[0] == address_shaped_scalar
    assert struct.unpack_from("Q", system, 0x08)[0] == 0x50000120


def test_resource_layout_rejects_invalid_declared_pointer():
    data = bytearray(0x20)
    struct.pack_into("Q", data, 0x08, 0x50001000)

    with pytest.raises(ValueError, match="does not target a resource block"):
        layout_resource_sections(
            data,
            [ResourceBlockSpan(0x00, 0x20, pointer_offsets=(0x08,))],
            version=46,
        )


def test_resource_writer_can_require_explicit_pointer_fields():
    writer = ResourceWriter(0x10)
    with pytest.raises(ValueError, match="does not declare its pointer fields"):
        writer.require_explicit_pointer_fields()

    classified = ResourceWriter(0x10, initial_pointer_offsets=())
    classified.require_explicit_pointer_fields()
