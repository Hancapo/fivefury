from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fivefury import (
    AssetRegistration,
    DlcDataFileType,
    GameFileOverlay,
    GameTarget,
    evaluate_yed,
)


@pytest.mark.integration("FIVEFURY_TEST_FACE_PROBE_ROOT")
def test_exported_face_probe_resolves_registered_metadata_and_expected_poses():
    root = Path(os.environ["FIVEFURY_TEST_FACE_PROBE_ROOT"])
    registration = AssetRegistration(
        os.environ["FIVEFURY_TEST_FACE_PROBE_METADATA"], DlcDataFileType.PED_METADATA
    )
    report = json.loads((root / "probe-report.json").read_text(encoding="utf-8"))
    cuts = list((root / "loose").glob("*.cut"))
    assert len(cuts) == 1
    with GameFileOverlay(
        root / "loose", registrations=[registration], game=GameTarget.GTA5_ENHANCED
    ) as overlay:
        bundle = overlay.resolve_cutscene(cuts[0].name)
        assert not bundle.issues
        peds = [
            binding
            for binding in bundle.bindings.values()
            if binding.ped_init_data is not None
        ]
        assert len(peds) == 1
        ped = peds[0]
        assert ped.ped_metadata is not None
        assert ped.ped_init_data in ped.ped_metadata.init_datas
        assert str(ped.ped_init_data.name) == report["model"]
        yed = ped.expression_dictionary
        assert yed is not None
        yed.require_expression(ped.ped_init_data.expression_name)
        yed.require_expression("faceinit")
        assert ped.component_assets
        for asset in ped.component_assets:
            yed.require_expression(asset.stem)
        clip = bundle.scene.clip_for_binding(ped.binding)
        assert clip is not None
        observed_times = set()
        for pose in report["poses"]:
            time = pose["time"]
            if time not in (0, 1, 3, 5):
                continue
            observed_times.add(time)
            result = evaluate_yed(
                yed,
                [ped.ped_init_data.expression_name.uint],
                clip.evaluate_tracks_at_time(time),
                time=time,
            )
            assert not result.issues
            for expected in pose["outputs"]:
                output = result.output_tracks[(expected["bone_tag"], expected["track"])]
                actual = tuple(output)[: len(expected["value"])]
                target = tuple(expected["value"])
                if expected["track"] == 1:
                    # q and -q describe the same rotation.
                    assert actual == pytest.approx(
                        target, abs=1e-6
                    ) or actual == pytest.approx(
                        tuple(-value for value in target), abs=1e-6
                    )
                else:
                    assert actual == pytest.approx(target, abs=1e-6)
        assert observed_times == {0, 1, 3, 5}
