from __future__ import annotations

import struct

from ..common import ByteSource, read_source_bytes
from ..resource import RSC7_VIRTUAL_BASE, build_rsc7, split_rsc7_sections
from .binary_validation import validate_yft_bytes
from .constants import TUNE_NAME_POINTER_OFFSET
from .reader import read_yft


def rewrite_yft_tune_name(
    source: ByteSource,
    tune_name: str,
    *,
    allow_padding_relocation: bool = False,
) -> bytes:
    """Rewrite ``fragType::m_TuneName`` without rebuilding the YFT graph.

    The existing string slot is reused when it has enough room. A longer string
    can be relocated into trailing system-page padding when explicitly enabled.
    Resource flags, page sizes, drawables, skeletons, shared matrices, physics
    data, and every other byte remain in their original uncompressed positions.
    """
    raw = read_source_bytes(source)
    validate_yft_bytes(raw).raise_for_errors()
    parsed = read_yft(raw)
    current_tune = parsed.tune_name
    if not tune_name or "\0" in tune_name:
        raise ValueError("YFT tune name must be non-empty and cannot contain NUL")
    try:
        desired = tune_name.encode("ascii")
        expected = current_tune.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("YFT tune names must be ASCII") from exc
    if tune_name == current_tune:
        return raw

    header, system_data, graphics_data = split_rsc7_sections(raw)
    system = bytearray(system_data)
    tune_pointer = int(parsed.pointers.tune_name)
    root_tune_pointer = struct.unpack_from("<Q", system, TUNE_NAME_POINTER_OFFSET)[0]
    if not tune_pointer or root_tune_pointer != tune_pointer:
        raise ValueError("YFT tune pointer does not match its root fragment")

    tune_offset = tune_pointer - RSC7_VIRTUAL_BASE
    if tune_offset < 0 or tune_offset >= len(system):
        raise ValueError("YFT tune string is outside the system pages")
    tune_end = system.find(0, tune_offset)
    if tune_end < 0 or bytes(system[tune_offset:tune_end]) != expected:
        raise ValueError("YFT tune pointer does not reference the parsed name")

    existing_capacity = tune_end - tune_offset
    if len(desired) <= existing_capacity:
        replacement = desired + bytes(existing_capacity - len(desired) + 1)
        system[tune_offset : tune_end + 1] = replacement
    else:
        if not allow_padding_relocation:
            raise ValueError(
                "YFT tune name exceeds the existing string capacity; "
                "enable allow_padding_relocation to use trailing zero padding"
            )
        required = len(desired) + 1
        trailing_padding = len(system) - len(system.rstrip(b"\0"))
        if trailing_padding < required:
            raise ValueError(
                "YFT tune name exceeds both the existing string capacity and "
                "the available trailing system-page padding"
            )
        relocated_offset = len(system) - required
        system[relocated_offset:] = desired + b"\0"
        struct.pack_into(
            "<Q",
            system,
            TUNE_NAME_POINTER_OFFSET,
            RSC7_VIRTUAL_BASE + relocated_offset,
        )

    rewritten = build_rsc7(
        bytes(system),
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )
    validate_yft_bytes(rewritten).raise_for_errors()
    reparsed = read_yft(rewritten)
    if reparsed.tune_name != tune_name:
        raise ValueError(
            f"rewritten YFT retained tune name {reparsed.tune_name!r} "
            f"instead of {tune_name!r}"
        )
    return rewritten


__all__ = ["rewrite_yft_tune_name"]
