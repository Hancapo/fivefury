import pytest

from fivefury import Vector4, create_yed, evaluate_yed
from tests.support.yed import large_expression

pytestmark = pytest.mark.performance


@pytest.fixture
def facial_program():
    yed = create_yed(large_expression())
    tracks = {
        (t.bone_id, t.track): Vector4(0.1, 0.2, 0.3, 1)
        for t in yed.expressions[0].tracks
        if t.is_input
    }
    return yed, tracks


def test_mutable_yed_evaluation(benchmark, facial_program):
    yed, tracks = facial_program
    assert benchmark(evaluate_yed, yed, ("calibrated",), tracks).output_tracks


def test_compiled_yed_evaluation(benchmark, facial_program):
    yed, tracks = facial_program
    evaluator = yed.compile(("calibrated",))
    assert benchmark(evaluator.evaluate, tracks).output_tracks
