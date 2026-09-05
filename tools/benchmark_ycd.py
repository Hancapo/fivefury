"""Measure warm, in-memory YCD authoring independently of asset conversion."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import sys
import time
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--actors", type=int, default=8)
    parser.add_argument("--bones", type=int, default=64)
    parser.add_argument("--duration", type=float, default=262.8333333333333)
    args = parser.parse_args()
    if args.package_root:
        sys.path.insert(0, str(args.package_root.resolve()))
    from fivefury import (
        GameTarget,
        Quaternion,
        Vector3,
        YcdChannelEncoding,
        YcdChannelEncodingPolicy,
        YcdCutsceneBoneAnimation,
        YcdCutsceneBuilder,
        build_ycd_bytes,
    )
    from fivefury.ycd import channel_validation

    start = time.perf_counter()
    builder = YcdCutsceneBuilder.create(
        "dense_skeletons",
        duration=args.duration,
        camera_cuts=[args.duration * index / 6 for index in range(1, 6)],
        game=GameTarget.GTA5_ENHANCED,
        channel_policy=YcdChannelEncodingPolicy(
            encoding=YcdChannelEncoding.RAW_FLOAT,
            maximum_error=1e-3,
            maximum_angular_error_degrees=0.05,
        ),
    )
    count = builder.total_frames
    rotations = [
        Quaternion.from_euler_xyz(
            Vector3(
                math.sin(frame * 0.017) * 0.7,
                math.sin(frame * 0.011) * 0.9,
                frame * 0.019,
            )
        )
        for frame in range(count)
    ]
    positions = [
        Vector3(frame * 0.003, math.sin(frame * 0.013), 1.0) for frame in range(count)
    ]
    for actor in range(args.actors):
        builder.prop(
            f"actor_{actor}",
            mover_position=positions,
            bones={
                bone: YcdCutsceneBoneAnimation(
                    rotation=Quaternion() if bone % 4 == 0 else rotations,
                )
                for bone in range(args.bones)
            },
        )
    setup = time.perf_counter() - start
    timings = defaultdict(float)
    calls = defaultdict(int)

    def timed(name, function):
        def wrapper(*values, **kwargs):
            started = time.perf_counter()
            try:
                return function(*values, **kwargs)
            finally:
                timings[name] += time.perf_counter() - started
                calls[name] += 1

        return wrapper

    with ExitStack() as stack:
        for module, name, label in (
            (YcdCutsceneBuilder, "_build_section", "encoding"),
            (channel_validation, "build_ycd_bytes", "validation_write"),
            (channel_validation, "read_ycd", "validation_read"),
            (
                channel_validation,
                "validate_cutscene_section_precision",
                "precision_inclusive",
            ),
        ):
            stack.enter_context(
                patch.object(module, name, timed(label, getattr(module, name)))
            )
        started = time.perf_counter()
        ycds = builder.build_ycds()
        timings["build_total"] = time.perf_counter() - started
        started = time.perf_counter()
        sizes = [len(build_ycd_bytes(ycd)) for ycd in ycds]
        timings["final_serialization"] = time.perf_counter() - started
    peak_mib = None
    if os.name == "nt":

        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "peak_working_set",
                    "working_set",
                    "peak_paged",
                    "paged",
                    "peak_nonpaged",
                    "nonpaged",
                    "pagefile",
                    "peak_pagefile",
                )
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.c_void_p(-1), ctypes.byref(counters), counters.cb
        )
        peak_mib = counters.peak_working_set / 1024**2
    print(
        json.dumps(
            {
                "setup": setup,
                "timings": timings,
                "calls": calls,
                "peak_mib": peak_mib,
                "actors": args.actors,
                "bones": args.bones,
                "frames": count,
                "sections": len(ycds),
                "output_bytes": sum(sizes),
                "asset_conversion_included": False,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
