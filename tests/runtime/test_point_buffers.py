import copy
import math
import struct
from unittest.mock import patch

import numpy as np
import pytest

from fivefury import Vector3
from fivefury import _native_abi3 as native
from fivefury._native import _ydr_decode_vertex_buffer
from fivefury.vector import Aabb3, _PointCloud3, sphere_radius_from_points


def test_point_snapshot_reuses_float64_values_without_quantizing_bounds():
    values = [Vector3(-0.0, 0.123456789, 2), Vector3(4, -5, 6)]
    cloud = _PointCloud3.from_points(iter(values))
    before = copy.deepcopy(cloud)
    assert cloud.rows.readonly
    assert cloud.rows.shape == (2, 3)
    assert cloud.bounds == Aabb3.from_points(values)
    assert cloud.sphere_radius(cloud.bounds.center) == sphere_radius_from_points(
        cloud.bounds.center, values
    )
    assert math.copysign(1, struct.unpack_from("=d", cloud.data)[0]) == -1
    packed = native.ydr_pack_vertex_buffer(
        [(0, 6)], cloud.rows, [], [], [], [], []
    )
    assert packed == struct.pack("<6f", *(component for value in values for component in value))
    values[0] = Vector3(99, 99, 99)
    assert cloud == before
    assert cloud.bounds.maximum == Vector3(4, .123456789, 6)


def test_empty_point_snapshot():
    cloud = _PointCloud3.from_points([])
    assert cloud.bounds == Aabb3(Vector3(), Vector3())
    assert cloud.sphere_radius(Vector3(99, 99, 99)) == 0


@pytest.mark.parametrize("dimensions", [0, 1, 5, -1])
def test_component_buffer_rejects_unsupported_dimensions(dimensions):
    with pytest.raises(ValueError, match="2 to 4"):
        native.vector_component_buffer([Vector3()], dimensions)


def test_component_buffer_rejects_missing_nominal_components():
    with pytest.raises(AttributeError):
        native.vector_component_buffer([(1, 2, 3)], 3)


def test_point_transform_keeps_coordinates_in_buffers():
    cloud = _PointCloud3.from_points([Vector3(1, 2, 3)])
    transform = ((2, 0, 0, 10), (0, -3, 0, 20), (0, 0, 4, 30), (0, 0, 0, 1))
    with patch.object(native, "vector_component_buffer", side_effect=AssertionError("reconverted vectors")):
        result = cloud.transformed(transform)
        empty = _PointCloud3(b"").transformed(transform)
    assert struct.unpack("=3d", result.data) == (12, 14, 42)
    assert struct.unpack("=3d", cloud.data) == (1, 2, 3)
    assert empty.data == b""


@pytest.mark.parametrize("rows", [
    np.zeros((2, 3), dtype=np.float32),
    np.zeros((2, 4), dtype=np.float64),
    np.zeros((4, 3), dtype=np.float64)[::2],
    np.zeros((2, 3), dtype=">f8"),
])
def test_native_float64_buffer_boundary_rejects_incompatible_views(rows):
    with pytest.raises(ValueError, match="contiguous float64"):
        native.bounds_from_vertices(memoryview(rows))
    with pytest.raises(ValueError, match="contiguous float64"):
        native.ydr_pack_vertex_buffer([(0, 6)], memoryview(rows), [], [], [], [], [])


def test_native_float64_rows_allow_unaligned_storage():
    data = b"x" + struct.pack("=3d", 1, 2, 3)
    rows = memoryview(data)[1:].cast("d", shape=(1, 3))
    assert native.bounds_from_vertices(rows) == ((1, 2, 3), (1, 2, 3))
    assert native.ydr_pack_vertex_buffer([(0, 6)], rows, [], [], [], [], []) == struct.pack("<3f", 1, 2, 3)


def test_decoder_channel_walk_preserves_explicit_offsets_and_partial_buffers():
    offsets = [0] * 16
    offsets[0] = 8
    raw = struct.pack("<10f", .25, .75, 1, 2, 3, .5, 1, 4, 5, 6)
    decoded = _ydr_decode_vertex_buffer(raw, 99, 20, 0x41, 6 | (5 << 24), tuple(offsets))
    assert decoded["positions"] == [Vector3(1, 2, 3), Vector3(4, 5, 6)]
    assert [uv.as_tuple() for uv in decoded["texcoords"][0]] == [(.25, .75), (.5, 1)]
    offsets[0] = len(raw) - 12
    decoded = _ydr_decode_vertex_buffer(raw, 99, 20, 1, 6, tuple(offsets))
    assert decoded["positions"] == [Vector3(4, 5, 6)]
    offsets[0] = -1
    assert _ydr_decode_vertex_buffer(raw, 99, 20, 1, 6, tuple(offsets))["positions"] == []
