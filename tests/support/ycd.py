import math

from fivefury import (
    Quaternion,
    Vector3,
    YcdChannelEncoding,
    YcdChannelEncodingPolicy,
    YcdCutsceneBuilder,
)
from fivefury import (
    YcdAnimationTrack as Track,
)


def facial_rig_builder(game, encoding, *, controls=64):
    """Dense body/camera and facial tracks, with technical and physical boundaries."""
    raw = YcdChannelEncodingPolicy(YcdChannelEncoding.RAW_FLOAT, 2e-5, 0.05)
    policy = YcdChannelEncodingPolicy(encoding, 1e-5, 0.05)
    builder = YcdCutsceneBuilder.create(
        "facial_rig",
        duration=20,
        fps=30,
        camera_cuts=[10],
        game=game,
        channel_policy=raw,
    )
    sources = {}
    for bone in range(1, controls + 1):
        phase = bone * 0.13
        angles = [0.06 * math.sin(frame * 0.035 + phase) for frame in range(601)]
        tracks = {
            Track.FACIAL_TRANSLATION: [
                Vector3(
                    0.01 * math.sin(frame * 0.045 + phase),
                    0.02 * math.cos(frame * 0.021 + phase),
                    0,
                )
                for frame in range(601)
            ],
            Track.FACIAL_ROTATION: [
                Quaternion(
                    math.sin(a / 2) / math.sqrt(3),
                    math.sin(a / 2) / math.sqrt(3),
                    math.sin(a / 2) / math.sqrt(3),
                    math.cos(a / 2),
                )
                for a in angles
            ],
            Track.FACIAL_SCALE: [
                Vector3(1 + 0.03 * math.sin(frame * 0.018 + phase), 1, 1)
                for frame in range(601)
            ],
        }
        for track, samples in tracks.items():
            sources[bone, int(track)] = samples
            builder.track(
                "actor_dual",
                bone_id=bone,
                track=track,
                samples=samples,
                channel_policy=policy,
            )
    for track in (
        Track.BONE_TRANSLATION,
        Track.MOVER_TRANSLATION,
        Track.CAMERA_TRANSLATION,
    ):
        samples = [
            Vector3(100 + frame / 100, 3 + frame / 300, 2) for frame in range(601)
        ]
        sources[0, int(track)] = samples
        builder.track("actor_dual", bone_id=0, track=track, samples=samples)
    samples = [50 + 0.2 * math.sin(frame / 50) for frame in range(601)]
    sources[0, int(Track.CAMERA_FIELD_OF_VIEW)] = samples
    builder.track("actor_dual", track=Track.CAMERA_FIELD_OF_VIEW, samples=samples)
    return builder, sources
