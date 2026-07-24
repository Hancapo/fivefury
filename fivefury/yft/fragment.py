from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..ydr import Ydr, YdrLight, YdrMesh, YdrModel
from ..ydr.defs import YdrLod, coerce_lod
from .cloth import YftEnvironmentCloth
from .drawables import YftDrawable, YftDrawableMatch
from .events import YftEventSet
from .glass import YftGlassPane, YftVehicleGlassWindows
from .matrices import YftSharedMatrixSet
from .physics import (
    YftPhysicsChild,
    YftPhysicsEntity,
    YftPhysicsGroup,
    YftPhysicsLod,
    YftPhysicsLodPointers,
)
from .pointers import YftFragmentPointers, YftFragmentState, YftRawField
from .stats import YftGeometryStats


@dataclasses.dataclass(slots=True)
class Yft:
    version: int = 0
    path: str = ""
    bounding_sphere: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    pointers: YftFragmentPointers = dataclasses.field(
        default_factory=YftFragmentPointers
    )
    state: YftFragmentState = dataclasses.field(default_factory=YftFragmentState)
    physics_lods: YftPhysicsLodPointers = dataclasses.field(
        default_factory=YftPhysicsLodPointers
    )
    physics_lod_details: list[YftPhysicsLod] = dataclasses.field(default_factory=list)
    root_child: YftPhysicsChild | None = None
    collision_event_set: YftEventSet | None = None
    user_data: int = 0
    tune_name: str = ""
    raw_fields: list[YftRawField] = dataclasses.field(default_factory=list)
    main_drawable: Ydr | None = None
    drawables: list[YftDrawable] = dataclasses.field(default_factory=list)
    cloth_drawable: Ydr | None = None
    environment_cloths: list[YftEnvironmentCloth] = dataclasses.field(
        default_factory=list
    )
    character_cloth_count: int = 0
    glass_panes: list[YftGlassPane] = dataclasses.field(default_factory=list)
    vehicle_glass_windows: YftVehicleGlassWindows | None = None
    shared_matrix_set: YftSharedMatrixSet | None = None
    lights: list[YdrLight] = dataclasses.field(default_factory=list)
    raw_bytes: bytes = dataclasses.field(default=b"", repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, *, path: str = "") -> Yft:
        from .reader import read_yft

        return read_yft(data, path=path)

    @property
    def name(self) -> str:
        return Path(self.path).stem if self.path else "fragment"

    @property
    def drawable_count(self) -> int:
        return sum(1 for _entry in self.iter_drawables())

    @property
    def glass_pane_count(self) -> int:
        return len(self.glass_panes)

    def iter_drawables(self) -> Iterator[YftDrawable]:
        if self.main_drawable is not None:
            yield YftDrawable(
                "drawable",
                self.main_drawable,
                pointer=self.pointers.common_drawable,
                name="drawable",
            )
        yield from self.drawables
        if self.cloth_drawable is not None:
            yield YftDrawable(
                "drawable_cloth",
                self.cloth_drawable,
                pointer=self.pointers.cloth_drawable,
                name="drawable_cloth",
            )

    @property
    def damaged_drawable_entry(self) -> YftDrawable | None:
        index = self.state.damaged_drawable_index
        return self.drawables[index] if 0 <= index < len(self.drawables) else None

    @property
    def damaged_drawable(self) -> Ydr | None:
        entry = self.damaged_drawable_entry
        return entry.drawable if entry is not None else None

    def iter_models(self, lod: YdrLod | str | None = None) -> Iterator[YdrModel]:
        for entry in self.iter_drawables():
            yield from entry.drawable.iter_models(lod=lod)

    def iter_meshes(self, lod: YdrLod | str | None = None) -> Iterator[YdrMesh]:
        for model in self.iter_models(lod=lod):
            yield from model.meshes

    def iter_physics_groups(self) -> Iterator[YftPhysicsGroup]:
        for lod in self.physics_lod_details:
            yield from lod.groups

    def iter_physics_children(self) -> Iterator[YftPhysicsChild]:
        for lod in self.physics_lod_details:
            yield from lod.children

    def iter_physics_entities(self) -> Iterator[YftPhysicsEntity]:
        seen: set[int] = set()
        for child in self.iter_physics_children():
            for entity in child.entities():
                identity = entity.pointer or -id(entity)
                if identity in seen:
                    continue
                seen.add(identity)
                yield entity

    def iter_physics_drawables(self) -> Iterator[YftDrawable]:
        for entity in self.iter_physics_entities():
            if entity.drawable is not None:
                yield YftDrawable(
                    entity.label,
                    entity.drawable,
                    pointer=entity.pointer,
                    name=entity.label,
                )

    def iter_event_sets(self) -> Iterator[YftEventSet]:
        seen: set[int] = set()

        def emit(event_set: YftEventSet | None) -> Iterator[YftEventSet]:
            if event_set is None or id(event_set) in seen:
                return
            seen.add(id(event_set))
            yield event_set

        yield from emit(self.collision_event_set)
        if self.root_child is not None:
            for event_set in self.root_child.events.event_sets():
                yield from emit(event_set)
        for lod in self.physics_lod_details:
            for group in lod.groups:
                for event_set in group.events.event_sets():
                    yield from emit(event_set)
            for child in lod.children:
                for event_set in child.events.event_sets():
                    yield from emit(event_set)

    def models(self, lod: YdrLod | str | None = None) -> list[YdrModel]:
        return list(self.iter_models(lod=lod))

    def meshes(self, lod: YdrLod | str | None = None) -> list[YdrMesh]:
        return list(self.iter_meshes(lod=lod))

    def physics_groups(self) -> list[YftPhysicsGroup]:
        return list(self.iter_physics_groups())

    def physics_children(self) -> list[YftPhysicsChild]:
        return list(self.iter_physics_children())

    def physics_entities(self) -> list[YftPhysicsEntity]:
        return list(self.iter_physics_entities())

    def physics_drawables(self) -> list[YftDrawable]:
        return list(self.iter_physics_drawables())

    def physics_lod(self, key: int | str = "high") -> YftPhysicsLod | None:
        if isinstance(key, int):
            return (
                self.physics_lod_details[key]
                if 0 <= key < len(self.physics_lod_details)
                else None
            )
        lowered = key.lower()
        return next(
            (lod for lod in self.physics_lod_details if lod.label.lower() == lowered),
            None,
        )

    @property
    def best_physics_lod(self) -> YftPhysicsLod | None:
        for label in ("high", "medium", "low"):
            lod = self.physics_lod(label)
            if lod is not None:
                return lod
        return self.physics_lod_details[0] if self.physics_lod_details else None

    def validate(self, *, raise_on_error: bool = False):
        from .validation import validate_yft

        issues = validate_yft(self)
        if raise_on_error and any(issue.is_error for issue in issues):
            from .validation import assert_valid_yft

            assert_valid_yft(self)
        return issues

    def with_physics_lod(
        self,
        lod: YftPhysicsLod,
        *,
        composite_bound=None,
        density: float = 1.0,
    ) -> Yft:
        from .physics_authoring import normalize_physics_lod, physics_lod_pointers_for

        normalized = normalize_physics_lod(
            lod,
            composite_bound=composite_bound or lod.composite_bound,
            density=density,
        )
        self.physics_lod_details = [
            existing
            for existing in self.physics_lod_details
            if existing.label.lower() != normalized.label.lower()
        ]
        self.physics_lod_details.append(normalized)
        self.physics_lods = physics_lod_pointers_for(self.physics_lod_details)
        return self

    def with_simple_physics(
        self,
        *,
        bound,
        group_name: str = "default",
        mass: float | None = None,
        density: float = 1.0,
        lod: str = "high",
    ) -> Yft:
        from .physics import YftPhysicsChild, YftPhysicsGroup, YftPhysicsLod
        from .physics_authoring import bound_mass

        child = YftPhysicsChild.declare(
            undamaged_mass=bound_mass(bound, density=density)
            if mass is None
            else float(mass),
            owner_group_name=group_name,
        )
        group = YftPhysicsGroup.declare(group_name, children=(child,))
        return self.with_physics_lod(
            YftPhysicsLod.declare(lod, groups=(group,)),
            composite_bound=bound,
            density=density,
        )

    def geometry_stats(self, lod: YdrLod | str | None = None) -> YftGeometryStats:
        drawables = list(self.iter_drawables())
        models = [
            model
            for entry in drawables
            for model in entry.drawable.iter_models(lod=lod)
        ]
        meshes = [mesh for model in models for mesh in model.meshes]
        materials = {
            (entry.label, material.index)
            for entry in drawables
            for material in entry.drawable.materials
        }
        textures = {
            texture.name.lower()
            for entry in drawables
            for material in entry.drawable.materials
            for texture in material.textures
            if texture.name
        }
        index_count = sum(len(mesh.indices) for mesh in meshes)
        return YftGeometryStats(
            drawable_count=len(drawables),
            model_count=len(models),
            mesh_count=len(meshes),
            vertex_count=sum(len(mesh.positions) for mesh in meshes),
            index_count=index_count,
            triangle_count=index_count // 3,
            material_count=len(materials),
            texture_count=len(textures),
        )

    def texture_names(self) -> list[str]:
        names = {
            texture.name
            for entry in self.iter_drawables()
            for material in entry.drawable.materials
            for texture in material.textures
            if texture.name
        }
        return sorted(names, key=str.lower)

    def material_names(self) -> list[str]:
        names = {
            material.name or material.shader_file_name or f"material_{material.index}"
            for entry in self.iter_drawables()
            for material in entry.drawable.materials
        }
        return sorted(names, key=str.lower)

    def summary(self) -> dict[str, Any]:
        stats = self.geometry_stats()
        return {
            "name": self.name,
            "version": self.version,
            "bounding_sphere": self.bounding_sphere,
            "root_child_pointer": self.pointers.root_child,
            "tune_name": self.tune_name,
            "has_physics": self.physics_lods.has_physics,
            "physics_lod_count": self.physics_lods.active_count,
            "physics_children": sum(
                lod.num_children for lod in self.physics_lod_details
            ),
            "physics_groups": sum(lod.num_groups for lod in self.physics_lod_details),
            "physics_child_entities": len(
                {
                    pointer
                    for lod in self.physics_lod_details
                    for pointer in lod.child_entity_pointers
                }
            ),
            "drawables": [entry.label for entry in self.iter_drawables()],
            "environment_cloths": len(self.environment_cloths),
            "model_count": stats.model_count,
            "mesh_count": stats.mesh_count,
            "vertex_count": stats.vertex_count,
            "triangle_count": stats.triangle_count,
            "material_count": stats.material_count,
            "texture_count": stats.texture_count,
        }

    def drawable_for_lod(self, lod: YdrLod | str) -> list[YftDrawableMatch]:
        target_lod = coerce_lod(lod)
        return [
            YftDrawableMatch(
                label=entry.label,
                drawable=entry.drawable,
                models=list(entry.drawable.iter_models(target_lod)),
            )
            for entry in self.iter_drawables()
            if entry.drawable.lods.get(target_lod)
        ]


__all__ = [
    "Yft",
]
