from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise

import pytest

from fivefury import (
    CutScene,
    CutsceneResolutionCancellation,
    CutsceneResolutionCancelled,
    CutsceneResolutionIndex,
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
        "preparation",
        "source",
        "cut",
        "animations",
        "bindings",
        "vehicle_models",
        "vehicle_appearances",
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


def test_cutscene_resolution_preparation_is_typed_and_idempotent(tmp_path) -> None:
    progress = []
    with _build_cache(tmp_path) as cache:
        first = cache.prepare_cutscene_resolution(progress=progress.append)
        second = cache.prepare_cutscene_resolution()

    assert second is first
    assert tuple(item.index for item in first.indexes) == tuple(CutsceneResolutionIndex)
    assert [item.completed for item in progress] == [1, 2, 3, 4, 5]
    assert all(item.total == 5 for item in progress)
    assert all(left.fraction <= right.fraction for left, right in pairwise(progress))


def test_cutscene_resolution_preparation_cancels_between_indexes(tmp_path) -> None:
    cancellation = CutsceneResolutionCancellation()

    def cancel_after_first(progress) -> None:
        if progress.completed == 1:
            cancellation.cancel()

    with (
        _build_cache(tmp_path) as cache,
        pytest.raises(CutsceneResolutionCancelled),
    ):
        cache.prepare_cutscene_resolution(
            cancellation=cancellation,
            progress=cancel_after_first,
        )


def test_cutscene_resolution_preparation_shares_concurrent_build(tmp_path) -> None:
    entered = threading.Event()
    release = threading.Event()

    def hold_first_index(progress) -> None:
        if progress.completed == 1:
            entered.set()
            assert release.wait(timeout=5.0)

    with _build_cache(tmp_path) as cache, ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            cache.prepare_cutscene_resolution,
            progress=hold_first_index,
        )
        assert entered.wait(timeout=5.0)
        second = pool.submit(cache.prepare_cutscene_resolution)
        release.set()
        first_result = first.result(timeout=5.0)
        second_result = second.result(timeout=5.0)

    assert second_result is first_result


def test_cutscene_resolution_runs_independent_stages_concurrently(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendezvous = threading.Barrier(2, timeout=5.0)

    def vehicle_stage(*_args, **_kwargs) -> None:
        rendezvous.wait()

    def audio_stage(*_args, **_kwargs) -> dict:
        rendezvous.wait()
        return {}

    monkeypatch.setattr(
        "fivefury.cut.resolution.core._resolve_vehicle_appearances",
        vehicle_stage,
    )
    monkeypatch.setattr(
        "fivefury.cut.resolution.core._resolve_audio",
        audio_stage,
    )

    with _build_cache(tmp_path) as cache:
        bundle = cache.resolve_cutscene("trace.cut")

    assert bundle.audio == {}
