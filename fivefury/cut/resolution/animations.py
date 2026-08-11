from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ...gamefile import GameFileType
from ..scene import CutScene
from .common import _load_file
from .models import CutsceneResolveIssue

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache
    from ...ycd import Ycd


def _resolve_ycds(
    cache: GameFileCache,
    source: AssetRecord,
    scene: CutScene,
    issues: list[CutsceneResolveIssue],
) -> tuple[dict[int, Ycd], dict[int, AssetRecord]]:
    path = PurePosixPath(source.path.replace("\\", "/"))
    section_count = max(1, len(scene.camera_cut_list or ()) + 1)
    ycds: dict[int, Ycd] = {}
    assets: dict[int, AssetRecord] = {}

    for section in range(section_count):
        candidates = [path.with_name(f"{path.stem}-{section}.ycd")]
        if section == 0:
            candidates.append(path.with_suffix(".ycd"))
        asset = next(
            (
                match
                for candidate in candidates
                if (
                    match := cache.find_path(
                        candidate.as_posix(), kind=GameFileType.YCD
                    )
                )
                is not None
            ),
            None,
        )
        if asset is None:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="ycd.section_missing",
                    message=f"No YCD was found for technical section {section}",
                    asset_path=source.path,
                )
            )
            continue
        game_file = _load_file(cache, asset, issues)
        ycd = game_file.parsed if game_file is not None else None
        if ycd is None or not hasattr(ycd, "build_cutscene_map"):
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="ycd.invalid",
                    message=f"Asset is not a decoded YCD: {asset.path}",
                    asset_path=asset.path,
                )
            )
            continue
        ycds[section] = ycd
        assets[section] = asset
        scene.attach_clip_dict(ycd)
    return ycds, assets
