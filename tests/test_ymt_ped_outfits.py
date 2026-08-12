from __future__ import annotations

from fivefury import (
    PedPropAnchor,
    Ymt,
    YmtContentType,
    coerce_ped_prop_anchor,
    iter_ped_props,
    ped_prop_file_stem,
)


def _ped_variation(prop_info: dict) -> Ymt:
    return Ymt(
        content={"propInfo": prop_info},
        content_type=YmtContentType.PED_VARIATION,
    )


def test_iter_ped_props_enumerates_every_anchor_drawable_and_texture_count() -> None:
    ymt = _ped_variation(
        {
            "numAvailProps": 4,
            "aAnchors": [
                {"anchor": 0, "props": [1, 3, 2]},
                {"anchor": 6, "props": [4]},
            ],
        }
    )

    props = list(iter_ped_props(ymt))

    assert [(item.anchor, item.drawable_index, item.texture_count) for item in props] == [
        (PedPropAnchor.HEAD, 0, 1),
        (PedPropAnchor.HEAD, 1, 3),
        (PedPropAnchor.HEAD, 2, 2),
        (PedPropAnchor.LEFT_WRIST, 0, 4),
    ]
    assert [item.slot for item in props] == [12, 12, 12, 18]
    assert [item.file_stem for item in props] == [
        "p_head_000",
        "p_head_001",
        "p_head_002",
        "p_lwrist_000",
    ]


def test_iter_ped_props_accepts_unresolved_meta_field_hashes() -> None:
    ymt = Ymt(
        content={
            "0x8590CDD8": {
                "0x09AD30FA": [
                    {"0x7019CA89": 10, "0x8856F65A": [2, 1]},
                ]
            }
        },
        content_type=YmtContentType.PED_VARIATION,
    )

    props = list(iter_ped_props(ymt))

    assert [item.anchor for item in props] == [
        PedPropAnchor.RIGHT_FOOT,
        PedPropAnchor.RIGHT_FOOT,
    ]
    assert [item.texture_count for item in props] == [2, 1]


def test_ped_prop_anchor_coercion_and_all_runtime_stems() -> None:
    assert coerce_ped_prop_anchor("p_eyes") is PedPropAnchor.EYES
    assert coerce_ped_prop_anchor("left_wrist") is PedPropAnchor.LEFT_WRIST
    assert ped_prop_file_stem(PedPropAnchor.PHYSICS_RIGHT_HAND, 7) == "ph_rhand_007"
    assert len({ped_prop_file_stem(anchor, 0) for anchor in PedPropAnchor}) == 13
