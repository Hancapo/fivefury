"""Run with python -m benchmarks.drawable_embedded_textures --repeats 7.

Inputs and shader warmup are outside timing; each sample builds a complete RSC7.
Run the same command before and after changes and compare the output SHA-256s.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import statistics
import time
from functools import partial

from fivefury import Vector2, Vector3, Ydd, YdrMeshInput, create_ydr
from fivefury.texture import total_mip_data_size
from fivefury.yft import build_yft_bytes, create_yft
from fivefury.ytd import Texture, TextureFormat, Ytd


def synthetic_drawable(*, enhanced: bool, size: int, count: int, random_data: bool):
    rng = random.Random(1729)
    data_size = total_mip_data_size(size, size, TextureFormat.BC1, 1)
    textures = Ytd(
        [
            Texture.from_raw(
                rng.randbytes(data_size) if random_data else bytes(data_size),
                size,
                size,
                TextureFormat.BC1,
                1,
                name=f"embedded_{index}",
            )
            for index in range(count)
        ]
    )
    return create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[Vector3(), Vector3(1, 0, 0), Vector3(0, 1, 0)],
                indices=[0, 1, 2],
                texcoords=[[Vector2(), Vector2(1, 0), Vector2(0, 1)]],
            )
        ],
        material_textures={"DiffuseSampler": "embedded_0"},
        embedded_textures=textures,
        version=159 if enhanced else 165,
        name="embedded_benchmark",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--count", type=int, default=4)
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "size": args.size,
                "count": args.count,
                "repeats": args.repeats,
            }
        )
    )
    for enhanced in (False, True):
        for random_data in (False, True):
            drawable = synthetic_drawable(
                enhanced=enhanced,
                size=args.size,
                count=args.count,
                random_data=random_data,
            )
            dictionary = Ydd.from_drawables(
                {"embedded_benchmark": drawable},
                game="gta5_enhanced" if enhanced else "gta5",
            )
            fragment = create_yft(
                drawable, name="embedded_benchmark", version=171 if enhanced else 162
            )
            for kind, build in (
                ("ydr", drawable.to_bytes),
                ("ydd", dictionary.to_bytes),
                ("yft", partial(build_yft_bytes, fragment)),
            ):
                output = build()
                samples = []
                for _ in range(args.repeats):
                    start = time.perf_counter()
                    output = build()
                    samples.append(time.perf_counter() - start)
                print(
                    json.dumps(
                        {
                            "kind": kind,
                            "enhanced": enhanced,
                            "random": random_data,
                            "median_ms": statistics.median(samples) * 1000,
                            "sha256": hashlib.sha256(output).hexdigest(),
                        }
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    main()
