from __future__ import annotations

import dataclasses
import enum

from ..bounds import Bound

Vector3 = tuple[float, float, float]
Vector4 = tuple[float, float, float, float]


class YftClothTuningFlag(enum.IntFlag):
    NONE = 0
    WIND_FEEDBACK = 1 << 0
    FLIP_INDICES_ORDER = 1 << 1
    IGNORE_DISTURBANCES = 1 << 2
    IS_IN_INTERIOR = 1 << 3
    NO_PED_COLLISION = 1 << 4
    USE_DISTANCE_THRESHOLD = 1 << 5
    CLAMP_HORIZONTAL_FORCE = 1 << 6
    FLIP_GRAVITY = 1 << 7
    ACTIVATE_ON_HIT = 1 << 8
    FORCE_VERTEX_RESISTANCE = 1 << 9
    UPDATE_IF_VISIBLE = 1 << 10


class YftEnvironmentClothFlag(enum.IntFlag):
    NONE = 0
    DRAWABLE_OWNED = 1 << 1
    MORPH = 1 << 2
    VISIBLE = 1 << 3
    TUNING_OWNED = 1 << 4
    IN_INTERIOR = 1 << 5
    BLEND_OWNED = 1 << 6
    ALLOW_PED_COLLISION = 1 << 7
    MOVING = 1 << 8
    SKIP_SIMULATION = 1 << 9
    HAS_LOCAL_BOUNDS = 1 << 10
    UPDATING = 1 << 11
    FORCE_INACTIVE_FOR_REPLAY = 1 << 12


@dataclasses.dataclass(slots=True)
class YftClothTuning:
    rotation_rate: float = 3.14159274
    angle_threshold: float = 0.5235988
    extra_force: Vector3 = (0.0, 0.0, 0.0)
    flags: YftClothTuningFlag = YftClothTuningFlag.NONE
    weight: float = -1.0
    distance_threshold: float = 0.0
    pin_vertex: int = 0
    non_pin_vertex0: int = 0
    non_pin_vertex1: int = 0
    vft: int = 0


@dataclasses.dataclass(slots=True)
class YftClothBridge:
    mesh_vertex_counts: tuple[int, int, int, int] = (0, 0, 0, 0)
    pin_radii: tuple[list[float], list[float], list[float], list[float]] = (
        dataclasses.field(default_factory=lambda: ([], [], [], []))
    )
    vertex_weights: tuple[list[float], list[float], list[float], list[float]] = (
        dataclasses.field(default_factory=lambda: ([], [], [], []))
    )
    inflation_scales: tuple[list[float], list[float], list[float], list[float]] = (
        dataclasses.field(default_factory=lambda: ([], [], [], []))
    )
    display_maps: tuple[list[int], list[int], list[int], list[int]] = (
        dataclasses.field(default_factory=lambda: ([], [], [], []))
    )
    pinnable_words: list[int] = dataclasses.field(default_factory=list)
    raw_header: bytes = dataclasses.field(default=b"", repr=False)


@dataclasses.dataclass(slots=True)
class YftClothMorphMap:
    position_weights: list[Vector4] = dataclasses.field(default_factory=list)
    position_indices: tuple[list[int], list[int], list[int], list[int]] = (
        dataclasses.field(default_factory=lambda: ([], [], [], []))
    )
    normal_weights: list[Vector4] = dataclasses.field(default_factory=list)
    normal_indices: tuple[list[int], list[int], list[int], list[int]] = (
        dataclasses.field(default_factory=lambda: ([], [], [], []))
    )
    display_indices: tuple[list[int], list[int]] = dataclasses.field(
        default_factory=lambda: ([], [])
    )
    polygon_count: int = 0
    raw_header: bytes = dataclasses.field(default=b"", repr=False)


@dataclasses.dataclass(slots=True)
class YftClothMorphController:
    maps: tuple[
        YftClothMorphMap | None,
        YftClothMorphMap | None,
        YftClothMorphMap | None,
    ] = (None, None, None)
    raw_header: bytes = dataclasses.field(default=b"", repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class YftClothConstraint:
    raw: bytes

    def __post_init__(self) -> None:
        if len(self.raw) != 16:
            raise ValueError("cloth constraints must be exactly 16 bytes")


@dataclasses.dataclass(slots=True)
class YftVerletCloth:
    bounds_min: Vector3 = (0.0, 0.0, 0.0)
    bounds_max: Vector3 = (0.0, 0.0, 0.0)
    vertices: list[Vector4] = dataclasses.field(default_factory=list)
    previous_vertices: list[Vector4] = dataclasses.field(default_factory=list)
    constraints: list[YftClothConstraint] = dataclasses.field(default_factory=list)
    secondary_constraints: list[YftClothConstraint] = dataclasses.field(
        default_factory=list
    )
    bound: Bound | None = None
    behavior_data: bytes = b""
    auxiliary_data: bytes = b""
    raw_header: bytes = dataclasses.field(default=b"", repr=False)

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def constraint_count(self) -> int:
        return len(self.constraints)


@dataclasses.dataclass(slots=True)
class YftClothController:
    name: str = ""
    bridge: YftClothBridge | None = None
    morph: YftClothMorphController | None = None
    verlet_lods: tuple[
        YftVerletCloth | None,
        YftVerletCloth | None,
        YftVerletCloth | None,
    ] = (None, None, None)
    controller_type: int = 0
    blend: float = 0.0
    raw_header: bytes = dataclasses.field(default=b"", repr=False)


@dataclasses.dataclass(slots=True)
class YftEnvironmentCloth:
    controller: YftClothController
    tuning: YftClothTuning | None = None
    drawable_label: str = "drawable"
    behavior_data: bytes = b""
    initial_position: Vector3 = (0.0, 0.0, 0.0)
    force: Vector3 = (0.0, 0.0, 0.0)
    user_data: list[int] = dataclasses.field(default_factory=list)
    flags: YftEnvironmentClothFlag = YftEnvironmentClothFlag.NONE
    raw_header: bytes = dataclasses.field(default=b"", repr=False)


__all__ = [
    "YftClothBridge",
    "YftClothConstraint",
    "YftClothController",
    "YftClothMorphController",
    "YftClothMorphMap",
    "YftClothTuning",
    "YftClothTuningFlag",
    "YftEnvironmentCloth",
    "YftEnvironmentClothFlag",
    "YftVerletCloth",
]
