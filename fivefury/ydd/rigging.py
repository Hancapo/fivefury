from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Sequence

from ..common import ByteSource
from ..ydr import RadialBoneRigRule, Ydr, YdrSkeleton, rig_ydr_to_bones_radially
from .model import Ydd, YddDrawable
from .reader import read_ydd


BODY_JIGGLE_BREAST_BONES: tuple[str, str] = ("SPR_R_Breast", "SPR_L_Breast")
BODY_JIGGLE_BUTT_BONES: tuple[str, str] = ("SM_R_BackSkirtRoll", "SM_L_BackSkirtRoll")


@dataclasses.dataclass(frozen=True, slots=True)
class YddRadialRigReport:
    drawables: int = 0
    meshes: int = 0
    vertices: int = 0
    bones_added: int = 0
    saved_files: tuple[Path, ...] = ()

    @property
    def changed(self) -> bool:
        return self.vertices > 0 or self.bones_added > 0


def _coerce_ydd(source: Ydd | ByteSource) -> Ydd:
    if isinstance(source, Ydd):
        return source
    return read_ydd(source, path=str(source) if isinstance(source, (str, Path)) else "")


def _coerce_ydr(source: Ydr | Ydd | YddDrawable | ByteSource, *, drawable: str | int | None = None) -> Ydr:
    if isinstance(source, Ydr):
        return source
    if isinstance(source, YddDrawable):
        if not isinstance(source.drawable, Ydr):
            raise TypeError("YDD drawable entry does not contain a parsed YDR")
        return source.drawable
    ydd = _coerce_ydd(source)
    if drawable is not None:
        entry = ydd.require(drawable)
        if not isinstance(entry.drawable, Ydr):
            raise TypeError(f"YDD drawable {entry.name!r} does not contain a parsed YDR")
        return entry.drawable
    for entry in ydd.iter_drawables():
        if isinstance(entry.drawable, Ydr) and entry.drawable.has_skeleton:
            return entry.drawable
    raise ValueError("YDD has no drawable with a skeleton")


def _skeleton_from_source(source: Ydr | Ydd | YddDrawable | ByteSource, *, drawable: str | int | None = None) -> YdrSkeleton:
    ydr = _coerce_ydr(source, drawable=drawable)
    if ydr.skeleton is None or not ydr.skeleton.bones:
        raise ValueError("source drawable has no skeleton")
    return ydr.skeleton


def _iter_body_ydd_paths(folder: str | Path) -> list[Path]:
    root = Path(folder)
    if not root.is_dir():
        raise FileNotFoundError(f"body folder does not exist: {root}")
    return sorted(root.glob("*.ydd"), key=lambda path: path.name.lower())


def find_body_skeleton_ydd(folder: str | Path) -> Path:
    errors: list[str] = []
    for path in _iter_body_ydd_paths(folder):
        try:
            _skeleton_from_source(path)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        return path
    detail = "; ".join(errors[:4])
    raise ValueError(f"no YDD with a skeleton was found in {folder!s}" + (f" ({detail})" if detail else ""))


def rig_ydd_to_bones_radially(
    ydd: Ydd,
    rules: Sequence[RadialBoneRigRule],
    *,
    skeleton: YdrSkeleton | None = None,
    skeleton_source: Ydr | Ydd | YddDrawable | ByteSource | None = None,
    skeleton_drawable: str | int | None = None,
    drawable: str | int | None = None,
    max_influences: int = 4,
    min_weight: float = 0.0001,
) -> YddRadialRigReport:
    active_skeleton = skeleton
    if active_skeleton is None and skeleton_source is not None:
        active_skeleton = _skeleton_from_source(skeleton_source, drawable=skeleton_drawable)
    if active_skeleton is None:
        active_skeleton = _skeleton_from_source(ydd, drawable=drawable)

    entries = [ydd.require(drawable)] if drawable is not None else list(ydd.iter_drawables())
    drawables_changed = 0
    total_meshes = 0
    total_vertices = 0
    total_bones_added = 0
    for entry in entries:
        if not isinstance(entry.drawable, Ydr):
            continue
        report = rig_ydr_to_bones_radially(
            entry.drawable,
            rules,
            skeleton=active_skeleton,
            max_influences=max_influences,
            min_weight=min_weight,
        )
        drawables_changed += int(report.changed)
        total_meshes += report.meshes
        total_vertices += report.vertices
        total_bones_added += report.bones_added
    return YddRadialRigReport(
        drawables=drawables_changed,
        meshes=total_meshes,
        vertices=total_vertices,
        bones_added=total_bones_added,
    )


def _rules_for_bones(
    bones: Sequence[str],
    *,
    radius: float,
    strength: float,
) -> tuple[RadialBoneRigRule, ...]:
    return tuple(RadialBoneRigRule(bone=name, radius=radius, strength=strength) for name in bones)


def _body_component_rules(
    path: Path,
    *,
    breast: bool,
    butt: bool,
    breast_radius: float,
    butt_radius: float,
    breast_strength: float,
    butt_strength: float,
) -> tuple[RadialBoneRigRule, ...]:
    name = path.name.lower()
    rules: list[RadialBoneRigRule] = []
    if breast and "uppr" in name:
        rules.extend(_rules_for_bones(BODY_JIGGLE_BREAST_BONES, radius=breast_radius, strength=breast_strength))
    if butt and "lowr" in name:
        rules.extend(_rules_for_bones(BODY_JIGGLE_BUTT_BONES, radius=butt_radius, strength=butt_strength))
    return tuple(rules)


def rig_body_folder_jiggle_bones(
    body_folder: str | Path,
    *,
    output_folder: str | Path | None = None,
    skeleton_ydd: str | Path | Ydd | Ydr | YddDrawable | None = None,
    breast: bool = True,
    butt: bool = True,
    breast_radius: float = 0.14,
    butt_radius: float = 0.16,
    breast_strength: float = 0.65,
    butt_strength: float = 0.65,
    max_influences: int = 4,
    min_weight: float = 0.0001,
) -> YddRadialRigReport:
    root = Path(body_folder)
    skeleton_source = skeleton_ydd if skeleton_ydd is not None else find_body_skeleton_ydd(root)
    destination_root = Path(output_folder) if output_folder is not None else None
    if destination_root is not None:
        destination_root.mkdir(parents=True, exist_ok=True)

    drawables = 0
    meshes = 0
    vertices = 0
    bones_added = 0
    saved_files: list[Path] = []
    for path in _iter_body_ydd_paths(root):
        rules = _body_component_rules(
            path,
            breast=breast,
            butt=butt,
            breast_radius=breast_radius,
            butt_radius=butt_radius,
            breast_strength=breast_strength,
            butt_strength=butt_strength,
        )
        if not rules:
            continue
        ydd = read_ydd(path)
        report = rig_ydd_to_bones_radially(
            ydd,
            rules,
            skeleton_source=skeleton_source,
            max_influences=max_influences,
            min_weight=min_weight,
        )
        drawables += report.drawables
        meshes += report.meshes
        vertices += report.vertices
        bones_added += report.bones_added
        if destination_root is not None and report.changed:
            output_path = destination_root / path.name
            ydd.save(output_path)
            saved_files.append(output_path)
    return YddRadialRigReport(
        drawables=drawables,
        meshes=meshes,
        vertices=vertices,
        bones_added=bones_added,
        saved_files=tuple(saved_files),
    )


__all__ = [
    "BODY_JIGGLE_BREAST_BONES",
    "BODY_JIGGLE_BUTT_BONES",
    "YddRadialRigReport",
    "find_body_skeleton_ydd",
    "rig_body_folder_jiggle_bones",
    "rig_ydd_to_bones_radially",
]
