import dataclasses
import math
import pickle
import struct
from concurrent.futures import ThreadPoolExecutor

import pytest

from fivefury import Quaternion, Vector2, Vector3, Vector4
from fivefury import _native_abi3 as native
from fivefury.ydr.reader import _decode_vertices


@pytest.mark.parametrize("cls,rows", [
    (Vector2, [(1, "2"), (-0.0, 3.5)]),
    (Vector3, [(1, 2, 3), (-0.0, 0, 4)]),
    (Vector4, [(1, 2, 3, 4)]),
    (Quaternion, [(0, 0, 0, 1)]),
])
def test_batch_vectors_match_constructors(cls, rows):
    result = cls.from_rows(iter(rows))
    assert result == [cls.from_iterable(row) for row in rows]
    assert all(type(value) is cls for value in result)
    assert pickle.loads(pickle.dumps(result)) == result
    assert cls.from_rows([]) == []
    with pytest.raises(dataclasses.FrozenInstanceError):
        result[0].x = 7


def test_batch_vectors_do_not_share_instances_and_preserve_negative_zero():
    left, right = Vector3.from_rows([(-0.0, 1, 2)] * 2)
    assert left is not right
    assert math.copysign(1, left.x) == -1


@pytest.mark.parametrize("rows,error", [([(1, 2)], ValueError), ([(1, 2, 3, 4)], ValueError), ([(1, object(), 3)], TypeError)])
def test_batch_vectors_reject_invalid_components(rows, error):
    with pytest.raises(error):
        Vector3.from_rows(rows)


def test_vertex_decoder_emits_nominal_channels_directly():
    data = struct.pack("<3f3f2f4f", 1, 2, 3, 0, 0, 1, .25, .75, 1, 0, 0, -1)
    flags = (1 << 0) | (1 << 3) | (1 << 6) | (1 << 14)
    types = 6 | (6 << 12) | (5 << 24) | (7 << 56)
    decoded = _decode_vertices(data * 2, 2, len(data), flags, types)
    assert decoded["positions"] == [Vector3(1, 2, 3)] * 2
    assert decoded["normals"] == [Vector3(0, 0, 1)] * 2
    assert decoded["texcoords"] == [[Vector2(.25, .75)] * 2]
    assert decoded["tangents"] == [Vector4(1, 0, 0, -1)] * 2
    assert decoded["positions"][0] is not decoded["positions"][1]
    with pytest.raises(dataclasses.FrozenInstanceError):
        decoded["positions"][0].x = 7


def test_vertex_packing_parallel_calls_preserve_independent_outputs():
    def pack(index):
        return native.ydr_pack_vertex_buffer(
            [(0, 6)], [Vector3(index, 2, 3)], [], [], [], [], [], None, None
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(pack, range(16)))
    assert outputs == [struct.pack("<3f", i, 2, 3) for i in range(16)]
