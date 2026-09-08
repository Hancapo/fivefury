import os
from pathlib import Path

import numpy as np
import pytest

from fivefury import (
    GameTarget,
    Quaternion,
    Vector3,
    YcdChannelEncoding,
    YcdChannelEncodingPolicy,
    YcdCutsceneBuilder,
    YcdQuaternionEncoding,
    build_ycd_bytes,
    read_ycd,
)
from fivefury import (
    YcdAnimationTrack as Track,
)


@pytest.mark.integration("FIVEFURY_TEST_YCD_FACIAL_CORPUS")
@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_lossless_facial_samples_support_explicit_strict_precision(game):
    paths = sorted(Path(os.environ["FIVEFURY_TEST_YCD_FACIAL_CORPUS"]).rglob("*.npz"))
    assert paths
    policy = YcdChannelEncodingPolicy(YcdChannelEncoding.RAW_FLOAT, 1e-5, 0.05)
    for path in paths:
        with np.load(path, allow_pickle=False) as archive:
            tracks = []
            duration = 0.0
            for label, track, cls in [
                ("translations", Track.FACIAL_TRANSLATION, Vector3),
                ("rotations", Track.FACIAL_ROTATION, Quaternion),
            ]:
                for index, bone in enumerate(archive[label + "_tags"]):
                    values = archive[f"{label}_{index}"]
                    keys = {
                        float(row[0] - values[0, 0]): cls(*row[1:]) for row in values
                    }
                    duration = max(duration, max(keys))
                    tracks.append((int(bone), track, keys))
        builder = YcdCutsceneBuilder.create(
            "facial_corpus", duration=duration, game=game
        )
        for bone, track, samples in tracks:
            builder.track(
                "actor_dual",
                track=track,
                bone_id=bone,
                samples=samples,
                channel_policy=policy,
                quaternion_encoding=YcdQuaternionEncoding.EXPLICIT
                if track is Track.FACIAL_ROTATION
                else None,
            )
        try:
            assets = builder.build_ycds()
        except ValueError as exc:
            pytest.fail(f"{path.name}: {exc}")
        for ycd in assets:
            decoded = read_ycd(build_ycd_bytes(ycd))
            assert decoded.game == game
            assert len(decoded.animations[0].bone_ids) == len(tracks)
