from __future__ import annotations

import math

import pytest

from fivefury import AngleMode, BoxOccluder, Vector3


def test_box_occluder_matches_gta_v_runtime_layout() -> None:
    occluder = BoxOccluder.from_box(
        Vector3(10.0, 20.0, 30.0),
        Vector3(8.0, 4.0, 6.0),
        30.0,
        AngleMode.DEGREES,
    )

    # BoxOccluder::SetSize stores cos then sin. CalculateVerts expands width
    # along local X and length along local Y.
    assert occluder.iCosZ == 14189
    assert occluder.iSinZ == 8192
    assert occluder.iWidth == 32
    assert occluder.iLength == 16
    assert occluder.size == Vector3(8.0, 4.0, 6.0)
    assert occluder.angle_radians == pytest.approx(math.radians(30.0), abs=1e-4)

    extent_x = math.cos(math.radians(30.0)) * 4.0 + math.sin(math.radians(30.0)) * 2.0
    extent_y = math.sin(math.radians(30.0)) * 4.0 + math.cos(math.radians(30.0)) * 2.0
    assert occluder.bounds.minimum.components == pytest.approx(
        (10.0 - extent_x, 20.0 - extent_y, 27.0),
        abs=1e-3,
    )
    assert occluder.bounds.maximum.components == pytest.approx(
        (10.0 + extent_x, 20.0 + extent_y, 33.0),
        abs=1e-3,
    )


def test_box_occluder_preserves_sub_quantum_boxes_as_minimum_size() -> None:
    occluder = BoxOccluder.from_box(Vector3(), Vector3(0.1, 0.1, 0.1))

    assert occluder.size == Vector3(0.25, 0.25, 0.25)
