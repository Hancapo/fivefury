from __future__ import annotations

import json

import pytest

from fivefury import (
    CutScene,
    CutsceneResolutionCancellation,
    CutsceneResolutionCancelled,
    CutsceneResolutionTrace,
    GameFileCache,
    audit_cutscene_resolution,
    benchmark_cutscene_resolution,
    save_cut,
    scene_to_cut,
)


def _build_cache(tmp_path) -> GameFileCache:
    destination = tmp_path / "trace.cut"
    scene = CutScene.create(scene_name="trace", duration=1.0)
    save_cut(scene_to_cut(scene), destination)
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan()
    return cache


def test_cutscene_resolution_trace_records_resolver_phases(tmp_path) -> None:
    with _build_cache(tmp_path) as cache:
        trace = CutsceneResolutionTrace()
        bundle = cache.resolve_cutscene("trace.cut", trace=trace)

    assert bundle.trace is trace
    assert trace.source == "trace.cut"
    assert trace.elapsed_ns > 0
    assert [span.name for span in trace.spans] == [
        "source",
        "cut",
        "animations",
        "bindings",
        "facial_resources",
        "ped_components",
        "textures",
        "subtitles",
        "audio",
    ]
    assert json.loads(trace.to_json())["elapsed_ns"] == trace.elapsed_ns
    destination = trace.save_json(tmp_path / "reports" / "trace.json")
    assert json.loads(destination.read_text())["elapsed_ns"] == trace.elapsed_ns


def test_cutscene_resolution_cancellation_is_not_an_audit_failure(tmp_path) -> None:
    cancellation = CutsceneResolutionCancellation()
    cancellation.cancel()

    with (
        _build_cache(tmp_path) as cache,
        pytest.raises(CutsceneResolutionCancelled),
    ):
        audit_cutscene_resolution(cache, cancellation=cancellation)


def test_cutscene_resolution_audit_and_benchmark_are_structured(tmp_path) -> None:
    with _build_cache(tmp_path) as cache:
        report = audit_cutscene_resolution(cache, include_traces=True)
        traces = benchmark_cutscene_resolution(cache, "trace.cut", iterations=2)

    assert report.total == 1
    assert report.passed == 1
    assert report.failed == 0
    assert report.entries[0].trace is not None
    assert len(traces) == 2
    assert all(trace.elapsed_ns > 0 for trace in traces)
