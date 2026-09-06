from __future__ import annotations

import pytest

from fivefury import (
    Ydr,
    YdrLod,
    YdrModel,
    build_yft_bytes,
    create_yft,
    read_yft,
    rewrite_yft_tune_name,
)
from fivefury.resource import RSC7_VIRTUAL_BASE, split_rsc7_sections


def _simple_yft(name: str) -> bytes:
    drawable = Ydr(
        version=162,
        lods={YdrLod.HIGH: [YdrModel(lod=YdrLod.HIGH)]},
    )
    yft = create_yft(drawable, name=name)
    yft.tune_name = f"pack:/{name}"
    return build_yft_bytes(yft)


def test_rewrite_yft_tune_name_reuses_existing_string_slot() -> None:
    raw = _simple_yft("native_fragment")
    source = read_yft(raw)
    rewritten = rewrite_yft_tune_name(raw, "pack:/renamed")
    result = read_yft(rewritten)

    before_header, before_system, before_graphics = split_rsc7_sections(raw)
    after_header, after_system, after_graphics = split_rsc7_sections(rewritten)
    tune_offset = source.pointers.tune_name - RSC7_VIRTUAL_BASE
    slot_end = tune_offset + len(source.tune_name) + 1

    assert result.tune_name == "pack:/renamed"
    assert result.pointers.tune_name == source.pointers.tune_name
    assert after_header == before_header
    assert after_graphics == before_graphics
    assert after_system[:tune_offset] == before_system[:tune_offset]
    assert after_system[slot_end:] == before_system[slot_end:]


def test_rewrite_yft_tune_name_requires_opt_in_for_larger_names() -> None:
    raw = _simple_yft("x")
    tune_name = "pack:/fragment_with_a_name_longer_than_the_original_slot"

    with pytest.raises(ValueError, match="allow_padding_relocation"):
        rewrite_yft_tune_name(raw, tune_name)


def test_rewrite_yft_tune_name_relocates_names_into_padding() -> None:
    raw = _simple_yft("x")
    tune_name = "pack:/fragment_with_a_name_longer_than_the_original_slot"

    before = read_yft(raw)
    rewritten = rewrite_yft_tune_name(
        raw,
        tune_name,
        allow_padding_relocation=True,
    )
    after = read_yft(rewritten)

    assert after.tune_name == tune_name
    assert after.pointers.tune_name != before.pointers.tune_name
    assert after.pointers.common_drawable == before.pointers.common_drawable
    assert after.pointers.physics_lod_group == before.pointers.physics_lod_group


def test_rewrite_yft_tune_name_is_exact_when_name_is_unchanged() -> None:
    raw = _simple_yft("same_fragment")

    assert rewrite_yft_tune_name(raw, read_yft(raw).tune_name) == raw


@pytest.mark.parametrize("tune_name", ["", "pack:/bad\0name", "pack:/café"])
def test_rewrite_yft_tune_name_rejects_invalid_names(tune_name: str) -> None:
    raw = _simple_yft("valid_fragment")

    with pytest.raises(ValueError):
        rewrite_yft_tune_name(raw, tune_name)
