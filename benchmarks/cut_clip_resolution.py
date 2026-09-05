"""Compare eager clip-map reconstruction with exact streaming-base lookup."""

from statistics import median
from timeit import repeat

from fivefury import CutScene, CutsceneAnimationDictionary, Vector3, YcdCutsceneBuilder
from fivefury.hashing import jenk_partial_hash


def main():
    builder = YcdCutsceneBuilder.create("resolution", duration=1)
    scene = CutScene.create(duration=1)
    for index in range(200):
        name = f"actor_{index}"
        builder.prop(name, mover_position=Vector3())
        scene.prop(name, animation_streaming_base=jenk_partial_hash(name))
    scene.animation_dictionary = CutsceneAnimationDictionary(
        sections=builder.build_ycds()
    )

    def eager():
        results = []
        for binding in scene.bindings:
            scene.available_clips()
            results.append(scene.clip_for_binding(binding))
        return results

    def direct():
        return [scene.clip_for_binding(binding) for binding in scene.bindings]

    assert all(left is right for left, right in zip(eager(), direct(), strict=True))
    baseline = median(repeat(eager, repeat=5, number=10)) / 10
    optimized = median(repeat(direct, repeat=5, number=10)) / 10
    print(
        f"200 actors: {baseline / optimized:.1f}x faster; {baseline * 1000:.3f} -> {optimized * 1000:.3f} ms"
    )


if __name__ == "__main__":
    main()
