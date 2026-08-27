from __future__ import annotations

import argparse
import ctypes
import json
import os
import time
import tracemalloc
from dataclasses import dataclass

from fivefury import (
    Vector3,
    YcdAnimationTrack,
    YcdCutsceneBuilder,
    YcdTrackFormat,
    build_ycd_bytes,
)


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    frame_count: int = 7887
    track_count: int = 2800
    entity_count: int = 107
    section_count: int = 6
    fps: float = 30.0
    serialize: bool = True


def _windows_memory() -> tuple[int, int]:
    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    )
    get_process_memory_info.restype = ctypes.c_int
    process = get_current_process()
    if not get_process_memory_info(
        process,
        ctypes.byref(counters),
        counters.cb,
    ):
        raise OSError("GetProcessMemoryInfo failed")
    return counters.working_set_size, counters.peak_working_set_size


def _process_memory() -> tuple[int, int]:
    if os.name == "nt":
        return _windows_memory()
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if os.uname().sysname != "Darwin":
        peak *= 1024
    return 0, int(peak)


def run(config: BenchmarkConfig) -> dict[str, float | int | bool]:
    duration = (config.frame_count - 1) / config.fps
    cuts = [
        duration * index / config.section_count
        for index in range(1, config.section_count)
    ]
    active_start = config.frame_count // 2
    dense_samples = [Vector3()] * config.frame_count
    for frame in range(active_start, min(active_start + 64, config.frame_count)):
        value = float(frame - active_start)
        dense_samples[frame] = Vector3(value, value * 0.5, -value * 0.25)

    baseline_rss, _ = _process_memory()
    tracemalloc.start()
    started = time.perf_counter()
    builder = YcdCutsceneBuilder.create(
        "dense_authoring_benchmark",
        duration=duration,
        camera_cuts=cuts,
        fps=config.fps,
    )
    for track_index in range(config.track_count):
        entity_index = track_index % config.entity_count
        builder.track(
            f"entity_{entity_index:03d}",
            track=YcdAnimationTrack.BONE_TRANSLATION,
            samples=dense_samples,
            bone_id=track_index // config.entity_count,
            format=YcdTrackFormat.VECTOR3,
        )
    registered = time.perf_counter()
    assets = builder.build_ycds()
    built = time.perf_counter()
    binary_size = 0
    if config.serialize:
        binary_size = sum(len(build_ycd_bytes(asset)) for asset in assets)
    finished = time.perf_counter()
    _, python_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    _, process_peak = _process_memory()

    return {
        "frames": config.frame_count,
        "tracks": config.track_count,
        "entities": config.entity_count,
        "sections": len(assets),
        "logical_samples": config.frame_count * config.track_count,
        "retained_samples": sum(
            track.samples.retained_count
            for clip in builder._clips.values()
            for track in clip.tracks
        ),
        "register_seconds": registered - started,
        "build_seconds": built - registered,
        "serialize_seconds": finished - built,
        "total_seconds": finished - started,
        "python_peak_mib": python_peak / (1024 * 1024),
        "rss_increment_mib": max(process_peak - baseline_rss, 0) / (1024 * 1024),
        "binary_size": binary_size,
        "serialized": config.serialize,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=7887)
    parser.add_argument("--tracks", type=int, default=2800)
    parser.add_argument("--entities", type=int, default=107)
    parser.add_argument("--sections", type=int, default=6)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument(
        "--serialize",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()
    result = run(
        BenchmarkConfig(
            frame_count=args.frames,
            track_count=args.tracks,
            entity_count=args.entities,
            section_count=args.sections,
            fps=args.fps,
            serialize=args.serialize,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
