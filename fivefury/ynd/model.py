from __future__ import annotations

import dataclasses
import math
from enum import IntEnum, IntFlag
from pathlib import Path

from ..resource import ResourcePagesInfo


class _FlexibleIntEnum(IntEnum):
    @classmethod
    def _missing_(cls, value: object) -> "_FlexibleIntEnum":
        if not isinstance(value, int):
            raise ValueError(f"{value!r} is not a valid {cls.__name__}")
        member = int.__new__(cls, value)
        member._name_ = f"UNKNOWN_{value}"
        member._value_ = value
        return member


class YndNodeSpeed(_FlexibleIntEnum):
    SLOW = 0
    NORMAL = 1
    FAST = 2
    FASTER = 3


class YndNodeSpecialType(_FlexibleIntEnum):
    NONE = 0
    PARKING_PARALLEL = 1
    PARKING_PERPENDICULAR = 2
    DROPOFF_GOODS = 3
    DRIVE_THROUGH = 4
    DRIVE_THROUGH_WINDOW = 5
    DROPOFF_GOODS_UNLOAD = 6
    HIDING_NODE = 7
    SMALL_WORK_VEHICLES = 8
    PETROL_STATION = 9
    PED_CROSSING = 10
    DROPOFF_PASSENGERS = 11
    DROPOFF_PASSENGERS_UNLOAD = 12
    OPEN_SPACE = 13
    PED_ASSISTED_MOVEMENT = 14
    TRAFFIC_LIGHT = 15
    GIVE_WAY = 16
    FORCE_JUNCTION = 17
    PED_DRIVEWAY_CROSSING = 18
    RESTRICTED_AREA = 19
    FALSE_JUNCTION = 20
    DISABLE_VEHICLE_CREATION = 21


class YndNodeMovementFlags(IntFlag):
    NONE = 0
    OFFROAD = 1 << 3
    ON_PLAYERS_ROAD = 1 << 4
    NO_BIG_VEHICLES = 1 << 5
    CANNOT_GO_RIGHT = 1 << 6
    CANNOT_GO_LEFT = 1 << 7


class YndNodeGuidanceFlags(IntFlag):
    NONE = 0
    SLIP_LANE = 1 << 0
    INDICATE_KEEP_LEFT = 1 << 1
    INDICATE_KEEP_RIGHT = 1 << 2


class YndNodeStateFlags(IntFlag):
    NONE = 0
    NO_GPS = 1 << 0
    CLOSE_TO_CAMERA = 1 << 1
    SLIP_JUNCTION = 1 << 2
    ALREADY_FOUND = 1 << 3
    SWITCHED_OFF_ORIGINAL = 1 << 4
    WATER_NODE = 1 << 5
    HIGHWAY_OR_LOW_BRIDGE = 1 << 6
    SWITCHED_OFF = 1 << 7


class YndNodeRoutingFlags(IntFlag):
    NONE = 0
    IN_TUNNEL = 1 << 0


class YndNodeTopographyFlags(IntFlag):
    NONE = 0
    LEFT_ONLY = 1 << 7


class YndLinkTravelFlags(IntFlag):
    NONE = 0
    GPS_CAN_GO_BOTH_WAYS = 1 << 0
    BLOCK_IF_NO_LANES = 1 << 1


class YndLinkShapeFlags(IntFlag):
    NONE = 0
    NARROW_ROAD = 1 << 1
    LEADS_TO_DEAD_END = 1 << 2
    LEADS_FROM_DEAD_END = 1 << 3


class YndLinkNavigationFlags(IntFlag):
    NONE = 0
    DONT_USE_FOR_NAVIGATION = 1 << 0
    SHORTCUT = 1 << 1


YndResourcePagesInfo = ResourcePagesInfo


@dataclasses.dataclass(slots=True)
class YndLink:
    area_id: int
    node_id: int
    travel_flags: YndLinkTravelFlags = YndLinkTravelFlags.NONE
    shape_flags: YndLinkShapeFlags = YndLinkShapeFlags.NONE
    navigation_flags: YndLinkNavigationFlags = YndLinkNavigationFlags.NONE
    tilt: int = 0
    tilt_falloff: int = 0
    width: int = 0
    lanes_from_other_node: int = 0
    lanes_to_other_node: int = 0
    distance: int = 0

    @classmethod
    def from_packed(
        cls,
        *,
        area_id: int,
        node_id: int,
        flags0: int,
        flags1: int,
        flags2: int,
        link_length: int,
    ) -> "YndLink":
        flags0 = int(flags0) & 0xFF
        flags1 = int(flags1) & 0xFF
        flags2 = int(flags2) & 0xFF
        return cls(
            area_id=int(area_id) & 0xFFFF,
            node_id=int(node_id) & 0xFFFF,
            travel_flags=YndLinkTravelFlags(flags0 & 0x03),
            shape_flags=YndLinkShapeFlags(flags1 & 0x1E),
            navigation_flags=YndLinkNavigationFlags(flags2 & 0x03),
            tilt=(flags0 >> 2) & 0x1F,
            tilt_falloff=((flags0 >> 7) & 0x1) | ((flags1 & 0x1) << 1),
            width=(flags1 >> 4) & 0x0F,
            lanes_from_other_node=(flags2 >> 2) & 0x07,
            lanes_to_other_node=(flags2 >> 5) & 0x07,
            distance=int(link_length) & 0xFF,
        )

    @property
    def flags0(self) -> int:
        return (
            int(self.travel_flags)
            | ((int(self.tilt) & 0x1F) << 2)
            | ((int(self.tilt_falloff) & 0x1) << 7)
        ) & 0xFF

    @property
    def flags1(self) -> int:
        return (
            ((int(self.tilt_falloff) >> 1) & 0x1)
            | int(self.shape_flags)
            | ((int(self.width) & 0x0F) << 4)
        ) & 0xFF

    @property
    def flags2(self) -> int:
        return (
            int(self.navigation_flags)
            | ((int(self.lanes_from_other_node) & 0x07) << 2)
            | ((int(self.lanes_to_other_node) & 0x07) << 5)
        ) & 0xFF

    @property
    def link_length(self) -> int:
        return int(self.distance) & 0xFF

    @link_length.setter
    def link_length(self, value: int) -> None:
        self.distance = int(value) & 0xFF

    def build(self) -> "YndLink":
        self.area_id = int(self.area_id) & 0xFFFF
        self.node_id = int(self.node_id) & 0xFFFF
        self.travel_flags = YndLinkTravelFlags(int(self.travel_flags) & 0x03)
        self.shape_flags = YndLinkShapeFlags(int(self.shape_flags) & 0x1E)
        self.navigation_flags = YndLinkNavigationFlags(int(self.navigation_flags) & 0x03)
        self.tilt = int(self.tilt) & 0x1F
        self.tilt_falloff = int(self.tilt_falloff) & 0x03
        self.width = int(self.width) & 0x0F
        self.lanes_from_other_node = int(self.lanes_from_other_node) & 0x07
        self.lanes_to_other_node = int(self.lanes_to_other_node) & 0x07
        self.distance = int(self.distance) & 0xFF
        return self


@dataclasses.dataclass(slots=True)
class YndJunction:
    position: tuple[float, float] = (0.0, 0.0)
    min_z: float = 0.0
    max_z: float = 0.0
    heightmap_dim_x: int = 0
    heightmap_dim_y: int = 0
    heightmap: bytes = b""
    junction_ref_unk0: int = 0

    @property
    def heightmap_count(self) -> int:
        return len(self.heightmap)

    def build(self) -> "YndJunction":
        self.position = (float(self.position[0]), float(self.position[1]))
        self.min_z = float(self.min_z)
        self.max_z = float(self.max_z)
        self.heightmap_dim_x = int(self.heightmap_dim_x) & 0xFF
        self.heightmap_dim_y = int(self.heightmap_dim_y) & 0xFF
        self.heightmap = bytes(self.heightmap)
        self.junction_ref_unk0 = int(self.junction_ref_unk0) & 0xFFFF
        expected = self.heightmap_dim_x * self.heightmap_dim_y
        if expected != len(self.heightmap):
            raise ValueError("junction heightmap byte count does not match heightmap_dim_x * heightmap_dim_y")
        return self


@dataclasses.dataclass(slots=True)
class YndNode:
    area_id: int
    node_id: int
    position: tuple[float, float, float]
    street_name_hash: int = 0
    group: int = 0
    movement_flags: YndNodeMovementFlags = YndNodeMovementFlags.NONE
    guidance_flags: YndNodeGuidanceFlags = YndNodeGuidanceFlags.NONE
    state_flags: YndNodeStateFlags = YndNodeStateFlags.NONE
    routing_flags: YndNodeRoutingFlags = YndNodeRoutingFlags.NONE
    topography_flags: YndNodeTopographyFlags = YndNodeTopographyFlags.NONE
    special: YndNodeSpecialType = YndNodeSpecialType.NONE
    speed: YndNodeSpeed = YndNodeSpeed.SLOW
    qualifies_as_junction: bool = False
    distance_hash: int = 0
    density: int = 0
    dead_endness: int = 0
    links: list[YndLink] = dataclasses.field(default_factory=list)
    junction: YndJunction | None = None
    unused0: int = 0
    unused1: int = 0
    unused2: int = 0
    unused3: int = 0
    unused4: int = 0

    @classmethod
    def from_packed(
        cls,
        *,
        area_id: int,
        node_id: int,
        position: tuple[float, float, float],
        street_name_hash: int,
        flags0: int,
        flags1: int,
        flags2: int,
        link_count_flags: int,
        flags3: int,
        flags4: int,
        links: list[YndLink] | None = None,
        junction: YndJunction | None = None,
        unused0: int = 0,
        unused1: int = 0,
        unused2: int = 0,
        unused3: int = 0,
        unused4: int = 0,
    ) -> "YndNode":
        flags0 = int(flags0) & 0xFF
        flags1 = int(flags1) & 0xFF
        flags2 = int(flags2) & 0xFF
        link_count_flags = int(link_count_flags) & 0xFF
        flags3 = int(flags3) & 0xFF
        flags4 = int(flags4) & 0xFF
        return cls(
            area_id=int(area_id) & 0xFFFF,
            node_id=int(node_id) & 0xFFFF,
            position=(float(position[0]), float(position[1]), float(position[2])),
            street_name_hash=int(street_name_hash) & 0xFFFFFFFF,
            group=flags0 & 0x07,
            movement_flags=YndNodeMovementFlags(flags0 & 0xF8),
            guidance_flags=YndNodeGuidanceFlags(flags1 & 0x07),
            state_flags=YndNodeStateFlags(flags2),
            routing_flags=YndNodeRoutingFlags(flags3 & 0x01),
            topography_flags=YndNodeTopographyFlags(flags4 & 0x80),
            special=YndNodeSpecialType((flags1 >> 3) & 0x1F),
            speed=YndNodeSpeed((link_count_flags >> 1) & 0x03),
            qualifies_as_junction=bool(link_count_flags & 0x01),
            distance_hash=(flags3 >> 1) & 0x7F,
            density=flags4 & 0x0F,
            dead_endness=(flags4 >> 4) & 0x07,
            links=list(links or []),
            junction=junction,
            unused0=int(unused0) & 0xFFFFFFFF,
            unused1=int(unused1) & 0xFFFFFFFF,
            unused2=int(unused2) & 0xFFFFFFFF,
            unused3=int(unused3) & 0xFFFFFFFF,
            unused4=int(unused4) & 0xFFFF,
        )

    @property
    def link_count(self) -> int:
        return len(self.links)

    @property
    def is_ped_node(self) -> bool:
        return self.special in {
            YndNodeSpecialType.PED_CROSSING,
            YndNodeSpecialType.PED_ASSISTED_MOVEMENT,
            YndNodeSpecialType.PED_DRIVEWAY_CROSSING,
        }

    @property
    def flags0(self) -> int:
        return (int(self.group) & 0x07) | int(self.movement_flags)

    @property
    def flags1(self) -> int:
        return (int(self.guidance_flags) & 0x07) | ((int(self.special) & 0x1F) << 3)

    @property
    def flags2(self) -> int:
        return int(self.state_flags) & 0xFF

    @property
    def link_count_flags(self) -> int:
        return (
            (0x01 if self.qualifies_as_junction else 0x00)
            | ((int(self.speed) & 0x03) << 1)
            | ((len(self.links) & 0x1F) << 3)
        ) & 0xFF

    @property
    def flags3(self) -> int:
        return (int(self.routing_flags) & 0x01) | ((int(self.distance_hash) & 0x7F) << 1)

    @property
    def flags4(self) -> int:
        return (
            (int(self.density) & 0x0F)
            | ((int(self.dead_endness) & 0x07) << 4)
            | int(self.topography_flags)
        ) & 0xFF

    @property
    def left_only(self) -> bool:
        return bool(self.topography_flags & YndNodeTopographyFlags.LEFT_ONLY)

    @left_only.setter
    def left_only(self, value: bool) -> None:
        if value:
            self.topography_flags |= YndNodeTopographyFlags.LEFT_ONLY
        else:
            self.topography_flags &= ~YndNodeTopographyFlags.LEFT_ONLY

    @property
    def in_tunnel(self) -> bool:
        return bool(self.routing_flags & YndNodeRoutingFlags.IN_TUNNEL)

    @in_tunnel.setter
    def in_tunnel(self, value: bool) -> None:
        if value:
            self.routing_flags |= YndNodeRoutingFlags.IN_TUNNEL
        else:
            self.routing_flags &= ~YndNodeRoutingFlags.IN_TUNNEL

    def build(self) -> "YndNode":
        self.area_id = int(self.area_id) & 0xFFFF
        self.node_id = int(self.node_id) & 0xFFFF
        self.position = (
            float(self.position[0]),
            float(self.position[1]),
            float(self.position[2]),
        )
        self.street_name_hash = int(self.street_name_hash) & 0xFFFFFFFF
        self.group = int(self.group) & 0x07
        self.movement_flags = YndNodeMovementFlags(int(self.movement_flags) & 0xF8)
        self.guidance_flags = YndNodeGuidanceFlags(int(self.guidance_flags) & 0x07)
        self.state_flags = YndNodeStateFlags(int(self.state_flags) & 0xFF)
        self.routing_flags = YndNodeRoutingFlags(int(self.routing_flags) & 0x01)
        self.topography_flags = YndNodeTopographyFlags(int(self.topography_flags) & 0x80)
        self.special = YndNodeSpecialType(int(self.special) & 0x1F)
        self.speed = YndNodeSpeed(int(self.speed) & 0x03)
        self.qualifies_as_junction = bool(self.qualifies_as_junction)
        self.distance_hash = int(self.distance_hash) & 0x7F
        self.density = int(self.density) & 0x0F
        self.dead_endness = int(self.dead_endness) & 0x07
        self.unused0 = int(self.unused0) & 0xFFFFFFFF
        self.unused1 = int(self.unused1) & 0xFFFFFFFF
        self.unused2 = int(self.unused2) & 0xFFFFFFFF
        self.unused3 = int(self.unused3) & 0xFFFFFFFF
        self.unused4 = int(self.unused4) & 0xFFFF
        self.links = [link.build() for link in self.links]
        if self.junction is not None:
            self.junction = self.junction.build()
            self.qualifies_as_junction = True
        return self


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> int:
    return min(255, int(math.sqrt(((b[0] - a[0]) ** 2) + ((b[1] - a[1]) ** 2) + ((b[2] - a[2]) ** 2))))


@dataclasses.dataclass(slots=True)
class Ynd:
    version: int = 1
    path: str = ""
    nodes: list[YndNode] = dataclasses.field(default_factory=list)
    file_vft: int = 0x406203D0
    file_unknown: int = 1
    pages_info: YndResourcePagesInfo = dataclasses.field(default_factory=YndResourcePagesInfo)
    unknown_24h: int = 0
    unknown_34h: int = 0
    unknown_48h: int = 1
    unknown_4ch: int = 0
    unknown_5ch: int = 0
    unknown_68h: int = 0
    unknown_6ch: int = 0
    system_pages_count: int = 0
    graphics_pages_count: int = 0

    @classmethod
    def from_nodes(cls, nodes: list[YndNode], *, path: str | Path = "", version: int = 1) -> "Ynd":
        return cls(version=int(version), path=str(path) if path else "", nodes=list(nodes))

    @property
    def vehicle_node_count(self) -> int:
        return sum(1 for node in self.nodes if not node.is_ped_node)

    @property
    def ped_node_count(self) -> int:
        return sum(1 for node in self.nodes if node.is_ped_node)

    @property
    def link_count(self) -> int:
        return sum(len(node.links) for node in self.nodes)

    @property
    def junction_count(self) -> int:
        return sum(1 for node in self.nodes if node.junction is not None)

    def build(self) -> "Ynd":
        self.version = int(self.version)
        self.file_vft = int(self.file_vft) & 0xFFFFFFFF
        self.file_unknown = int(self.file_unknown) & 0xFFFFFFFF
        self.nodes = [node.build() for node in self.nodes]
        sorted_nodes = sorted(self.nodes, key=lambda node: (1 if node.is_ped_node else 0, int(node.node_id)))

        id_map: dict[tuple[int, int], int] = {}
        for new_node_id, node in enumerate(sorted_nodes):
            old_key = (int(node.area_id), int(node.node_id))
            id_map[old_key] = int(new_node_id)
            node.node_id = new_node_id

        node_lookup = {(int(node.area_id), int(node.node_id)): node for node in sorted_nodes}
        for node in sorted_nodes:
            for link in node.links:
                target_key = (int(link.area_id), int(link.node_id))
                new_target = id_map.get(target_key)
                if new_target is not None:
                    link.node_id = new_target
                target_node = node_lookup.get((int(link.area_id), int(link.node_id)))
                if target_node is not None:
                    link.distance = _distance(node.position, target_node.position)

        self.nodes = sorted_nodes
        return self

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.version != 1:
            issues.append("YND version must be 1")
        for node in self.nodes:
            if len(node.links) > 31:
                issues.append(f"Node {node.node_id} exceeds the 31-link limit encoded by LinkCountFlags")
            if node.junction is not None:
                expected = node.junction.heightmap_dim_x * node.junction.heightmap_dim_y
                if expected != len(node.junction.heightmap):
                    issues.append(f"Node {node.node_id} has a junction heightmap size mismatch")
        return issues

    def to_bytes(self) -> bytes:
        from .writer import build_ynd_bytes

        return build_ynd_bytes(self)

    def save(self, destination: str | Path) -> Path:
        from .writer import save_ynd

        return save_ynd(self, destination)
