from __future__ import annotations

import dataclasses
import struct

from ..binary import align
from ..resource import ResourceWriter
from .model import (
    Bound,
    BoundAabb,
    BoundBvh,
    BoundBvhNode,
    BoundBvhTree,
    BoundBox,
    BoundBVH,
    BoundCapsule,
    BoundChild,
    BoundCloth,
    BoundComposite,
    BoundCompositeFlags,
    BoundCylinder,
    BoundDisc,
    BoundGeometry,
    BoundGeometryOctants,
    BoundMaterial,
    BoundMaterialColor,
    BoundPolygon,
    BoundPolygonBox,
    BoundPolygonCapsule,
    BoundPolygonCylinder,
    BoundPolygonSphere,
    BoundPolygonTriangle,
    BoundSphere,
    BoundTransform,
)

_DAT_VIRTUAL_BASE = 0x50000000
_RESOURCE_FILE_BASE_SIZE = 0x10
_BOUND_BLOCK_SIZE = 0x80
_COMPOSITE_BLOCK_SIZE = 0xB0
_GEOMETRY_BLOCK_SIZE = 0x130
_GEOMETRY_BVH_BLOCK_SIZE = 0x150
_BVH_BLOCK_SIZE = 0x80
_GEOMETRY_BVH_ITEM_THRESHOLD = 4
_MAX_BVH_TREE_NODE_COUNT = 127


def _virtual(offset: int) -> int:
    return _DAT_VIRTUAL_BASE + int(offset)


def _bound_size(bound: Bound) -> int:
    if isinstance(bound, BoundComposite):
        return _COMPOSITE_BLOCK_SIZE
    if isinstance(bound, BoundBVH):
        return _GEOMETRY_BVH_BLOCK_SIZE
    if isinstance(bound, BoundGeometry):
        return _GEOMETRY_BLOCK_SIZE
    if isinstance(bound, (BoundSphere, BoundBox, BoundCapsule, BoundDisc, BoundCylinder, BoundCloth)):
        return _BOUND_BLOCK_SIZE
    raise NotImplementedError(f"bound writer does not support {bound.__class__.__name__} yet")


def _write_vec3(writer: ResourceWriter, offset: int, value: tuple[float, float, float]) -> None:
    writer.pack_into("3f", offset, *value)


def _write_aabb(writer: ResourceWriter, offset: int, bounds: BoundAabb) -> None:
    writer.pack_into("4f", offset + 0x00, *bounds.minimum, 0.0)
    writer.pack_into("4f", offset + 0x10, *bounds.maximum, 0.0)


def _write_transform(writer: ResourceWriter, offset: int, transform: BoundTransform | None) -> None:
    value = transform or BoundTransform(
        column1=(1.0, 0.0, 0.0),
        column2=(0.0, 1.0, 0.0),
        column3=(0.0, 0.0, 1.0),
        column4=(0.0, 0.0, 0.0),
    )
    writer.pack_into("3fI", offset + 0x00, *value.column1, value.flags1)
    writer.pack_into("3fI", offset + 0x10, *value.column2, value.flags2)
    writer.pack_into("3fI", offset + 0x20, *value.column3, value.flags3)
    writer.pack_into("3fI", offset + 0x30, *value.column4, value.flags4)


def _write_composite_flags(writer: ResourceWriter, offset: int, flags: BoundCompositeFlags | None) -> None:
    value = flags or BoundCompositeFlags()
    writer.pack_into("II", offset, value.flags1, value.flags2)


def _write_bound_common(writer: ResourceWriter, offset: int, bound: Bound) -> None:
    writer.pack_into("I", offset + 0x04, 1)
    writer.pack_into("B", offset + 0x10, int(bound.bound_type))
    writer.pack_into("B", offset + 0x11, 0)
    writer.pack_into("H", offset + 0x12, 0)
    writer.pack_into("f", offset + 0x14, bound.sphere_radius)
    writer.pack_into("I", offset + 0x18, 0)
    writer.pack_into("I", offset + 0x1C, 0)
    _write_vec3(writer, offset + 0x30, bound.box_max)
    writer.pack_into("f", offset + 0x3C, bound.margin)
    _write_vec3(writer, offset + 0x40, bound.box_min)
    writer.pack_into("I", offset + 0x4C, bound.unknown_3ch)
    _write_vec3(writer, offset + 0x50, bound.box_center)
    room_and_density = (bound.room_id & 0x1F) | ((bound.ped_density & 0x07) << 5)
    writer.pack_into(
        "4B",
        offset + 0x5C,
        bound.material_index & 0xFF,
        bound.procedural_id & 0xFF,
        room_and_density & 0xFF,
        bound.unk_flags & 0xFF,
    )
    _write_vec3(writer, offset + 0x60, bound.sphere_center)
    writer.pack_into("BBH", offset + 0x6C, bound.poly_flags & 0xFF, bound.material_color_index & 0xFF, 0)
    _write_vec3(writer, offset + 0x70, bound.unknown_60h)
    writer.pack_into("f", offset + 0x7C, bound.volume)


def _write_bound(writer: ResourceWriter, bound: Bound, *, offset: int | None = None) -> int:
    bound_offset = 0 if offset is None else offset
    if offset is None:
        bound_offset = writer.alloc(_bound_size(bound), 16)
    _write_bound_common(writer, bound_offset, bound)
    if isinstance(bound, BoundComposite):
        _write_composite(writer, bound_offset, bound)
    elif isinstance(bound, BoundBVH):
        _write_geometry(writer, bound_offset, bound, with_bvh=True)
    elif isinstance(bound, BoundGeometry):
        _write_geometry(writer, bound_offset, bound, with_bvh=False)
    elif not isinstance(bound, (BoundSphere, BoundBox, BoundCapsule, BoundDisc, BoundCylinder, BoundCloth)):
        raise NotImplementedError(f"bound writer does not support {bound.__class__.__name__} yet")
    return bound_offset


def _child_bounds(child: BoundChild) -> BoundAabb:
    return child.bounds if child.bounds is not None else child.bound.bounds


def _write_composite(writer: ResourceWriter, offset: int, bound: BoundComposite) -> None:
    child_offsets = [_write_bound(writer, child.bound) for child in bound.children]
    child_count = len(bound.children)

    child_ptrs_offset = 0
    transforms_offset = 0
    child_bounds_offset = 0
    flags_offset = 0

    if child_count:
        child_ptrs_offset = writer.alloc(child_count * 8, 8)
        for index, child_offset in enumerate(child_offsets):
            writer.pack_into("Q", child_ptrs_offset + (index * 8), _virtual(child_offset))

        transforms_offset = writer.alloc(child_count * 0x40, 16)
        for index, child in enumerate(bound.children):
            _write_transform(writer, transforms_offset + (index * 0x40), child.transform)

        child_bounds_offset = writer.alloc(child_count * 0x20, 16)
        for index, child in enumerate(bound.children):
            _write_aabb(writer, child_bounds_offset + (index * 0x20), _child_bounds(child))

        flags_offset = writer.alloc(child_count * 0x08, 8)
        for index, child in enumerate(bound.children):
            _write_composite_flags(writer, flags_offset + (index * 0x08), child.flags1 or child.flags2)

    writer.pack_into("Q", offset + 0x70, _virtual(child_ptrs_offset) if child_ptrs_offset else 0)
    writer.pack_into("Q", offset + 0x78, _virtual(transforms_offset) if transforms_offset else 0)
    writer.pack_into("Q", offset + 0x80, _virtual(transforms_offset) if transforms_offset else 0)
    writer.pack_into("Q", offset + 0x88, _virtual(child_bounds_offset) if child_bounds_offset else 0)
    writer.pack_into("Q", offset + 0x90, _virtual(flags_offset) if flags_offset else 0)
    writer.pack_into("Q", offset + 0x98, _virtual(flags_offset) if flags_offset else 0)
    writer.pack_into("H", offset + 0xA0, child_count)
    writer.pack_into("H", offset + 0xA2, child_count)
    writer.pack_into("I", offset + 0xA4, 0)
    writer.pack_into("Q", offset + 0xA8, 0)


def _material_data(material: BoundMaterial) -> tuple[int, int]:
    if material.data1 or material.data2:
        return (material.data1, material.data2)
    data1 = (
        (material.type & 0xFF)
        | ((material.procedural_id & 0xFF) << 8)
        | ((material.room_id & 0x1F) << 16)
        | ((material.ped_density & 0x07) << 21)
        | ((material.flags & 0xFF) << 24)
    )
    data2 = (
        ((material.flags >> 8) & 0xFF)
        | ((material.material_color_index & 0xFF) << 8)
        | ((material.unknown & 0xFFFF) << 16)
    )
    return (data1, data2)


def _choose_center_geom(bound: BoundGeometry) -> tuple[float, float, float]:
    if bound.center_geom != (0.0, 0.0, 0.0):
        return bound.center_geom
    return tuple((bound.box_min[axis] + bound.box_max[axis]) * 0.5 for axis in range(3))


def _choose_quantum(vertices: list[tuple[float, float, float]], center_geom: tuple[float, float, float]) -> tuple[float, float, float]:
    if not vertices:
        return (1.0, 1.0, 1.0)
    components: list[float] = []
    for axis in range(3):
        max_delta = max(abs(vertex[axis] - center_geom[axis]) for vertex in vertices)
        quantum = max_delta / 32767.0 if max_delta > 0 else (1.0 / 32767.0)
        components.append(quantum)
    return (components[0], components[1], components[2])


def _quantize_vertices(vertices: list[tuple[float, float, float]], center_geom: tuple[float, float, float], quantum: tuple[float, float, float]) -> bytes:
    data = bytearray(len(vertices) * 6)
    for index, vertex in enumerate(vertices):
        packed: list[int] = []
        for axis in range(3):
            q = quantum[axis] if quantum[axis] else (1.0 / 32767.0)
            value = round((vertex[axis] - center_geom[axis]) / q)
            value = max(-32767, min(32767, value))
            packed.append(int(value))
        struct.pack_into("<3h", data, index * 6, *packed)
    return bytes(data)


def _choose_vertices_shrunk(bound: BoundGeometry, *, with_bvh: bool) -> list[tuple[float, float, float]]:
    if with_bvh:
        return []
    if len(bound.vertices_shrunk) == len(bound.vertices):
        return list(bound.vertices_shrunk)
    return list(bound.vertices)


def _choose_octants(
    bound: BoundGeometry,
    vertices_shrunk: list[tuple[float, float, float]],
    *,
    with_bvh: bool,
) -> BoundGeometryOctants | None:
    if with_bvh or not vertices_shrunk:
        return None
    octants = bound.octants if bound.octants is not None else BoundGeometryOctants.from_vertices(vertices_shrunk)
    return octants if octants.has_items else None


def _write_octants(writer: ResourceWriter, octants: BoundGeometryOctants | None) -> tuple[int, int]:
    if octants is None or not octants.has_items:
        return (0, 0)
    total_items = octants.total_items
    block_size = 0x80 + (total_items * 4)
    block_offset = writer.alloc(block_size, 16)
    pointer_table_offset = block_offset + 0x20
    item_offset = block_offset + 0x60

    for index, count in enumerate(octants.counts):
        writer.pack_into("I", block_offset + (index * 4), count)

    current = item_offset
    for index, items in enumerate(octants.items):
        pointer_value = _virtual(current) if items else 0
        writer.pack_into("Q", pointer_table_offset + (index * 8), pointer_value)
        if items:
            for item_index, vertex_index in enumerate(items):
                writer.pack_into("I", current + (item_index * 4), vertex_index)
            current += len(items) * 4
    return (block_offset, pointer_table_offset)


def _encode_polygon(polygon: BoundPolygon) -> bytes:
    if len(polygon.raw) == 16 and not isinstance(
        polygon,
        (BoundPolygonTriangle, BoundPolygonSphere, BoundPolygonCapsule, BoundPolygonBox, BoundPolygonCylinder),
    ):
        raw = bytearray(polygon.raw)
    else:
        raw = bytearray(16)
        if isinstance(polygon, BoundPolygonTriangle):
            struct.pack_into(
                "<f6H",
                raw,
                0,
                polygon.tri_area,
                polygon.tri_index1,
                polygon.tri_index2,
                polygon.tri_index3,
                polygon.edge_index1,
                polygon.edge_index2,
                polygon.edge_index3,
            )
        elif isinstance(polygon, BoundPolygonSphere):
            struct.pack_into("<HHfII", raw, 0, polygon.sphere_type, polygon.sphere_index, polygon.sphere_radius, polygon.unused0, polygon.unused1)
        elif isinstance(polygon, BoundPolygonCapsule):
            struct.pack_into(
                "<HHfHHI",
                raw,
                0,
                polygon.capsule_type,
                polygon.capsule_index1,
                polygon.capsule_radius,
                polygon.capsule_index2,
                polygon.unused0,
                polygon.unused1,
            )
        elif isinstance(polygon, BoundPolygonBox):
            struct.pack_into(
                "<I4hI",
                raw,
                0,
                polygon.box_type,
                polygon.box_index1,
                polygon.box_index2,
                polygon.box_index3,
                polygon.box_index4,
                polygon.unused0,
            )
        elif isinstance(polygon, BoundPolygonCylinder):
            struct.pack_into(
                "<HHfHHI",
                raw,
                0,
                polygon.cylinder_type,
                polygon.cylinder_index1,
                polygon.cylinder_radius,
                polygon.cylinder_index2,
                polygon.unused0,
                polygon.unused1,
            )
        else:
            raw[: len(polygon.raw[:16])] = polygon.raw[:16]
    raw[0] = (raw[0] & 0xF8) | (int(polygon.polygon_type) & 0x07)
    return bytes(raw)


def _primitive_bounds(bound: BoundGeometry, polygon: BoundPolygon) -> BoundAabb:
    vertices = bound.vertices
    if not vertices:
        return BoundAabb(bound.box_min, bound.box_max)
    if isinstance(polygon, BoundPolygonTriangle):
        points = [vertices[index] for index in polygon.vertex_indices]
        minimum = tuple(min(point[axis] for point in points) for axis in range(3))
        maximum = tuple(max(point[axis] for point in points) for axis in range(3))
        return BoundAabb(minimum, maximum)
    if isinstance(polygon, BoundPolygonSphere):
        center = vertices[polygon.sphere_index]
        radius = polygon.sphere_radius
        minimum = (center[0] - radius, center[1] - radius, center[2] - radius)
        maximum = (center[0] + radius, center[1] + radius, center[2] + radius)
        return BoundAabb(minimum, maximum)
    if isinstance(polygon, (BoundPolygonCapsule, BoundPolygonCylinder)):
        index1, index2 = polygon.vertex_indices
        point1 = vertices[index1]
        point2 = vertices[index2]
        radius = polygon.capsule_radius if isinstance(polygon, BoundPolygonCapsule) else polygon.cylinder_radius
        minimum = tuple(min(point1[axis], point2[axis]) - radius for axis in range(3))
        maximum = tuple(max(point1[axis], point2[axis]) + radius for axis in range(3))
        return BoundAabb(minimum, maximum)
    if isinstance(polygon, BoundPolygonBox):
        points = [vertices[index] for index in polygon.vertex_indices]
        minimum = tuple(min(point[axis] for point in points) for axis in range(3))
        maximum = tuple(max(point[axis] for point in points) for axis in range(3))
        return BoundAabb(minimum, maximum)
    return BoundAabb(bound.box_min, bound.box_max)


def _merge_aabbs(bounds: list[BoundAabb], fallback: BoundAabb) -> BoundAabb:
    if not bounds:
        return fallback
    minimum = tuple(min(item.minimum[axis] for item in bounds) for axis in range(3))
    maximum = tuple(max(item.maximum[axis] for item in bounds) for axis in range(3))
    return BoundAabb(minimum, maximum)


def _choose_bvh_quantum(bounds: BoundAabb, center: tuple[float, float, float]) -> tuple[float, float, float]:
    values: list[float] = []
    for axis in range(3):
        half_extent = max(abs(bounds.minimum[axis] - center[axis]), abs(bounds.maximum[axis] - center[axis]))
        quantum = half_extent / 32767.0 if half_extent > 0 else (1.0 / 32767.0)
        values.append(quantum)
    return (values[0], values[1], values[2])


def _quantize_bvh_point(point: tuple[float, float, float], center: tuple[float, float, float], inverse: tuple[float, float, float]) -> tuple[int, int, int]:
    values: list[int] = []
    for axis in range(3):
        quantized = int((point[axis] - center[axis]) * inverse[axis])
        values.append(max(-32767, min(32767, quantized)))
    return (values[0], values[1], values[2])


@dataclasses.dataclass(slots=True)
class _BvhBuildItem:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    index: int
    polygon: BoundPolygon

    @property
    def center(self) -> tuple[float, float, float]:
        return tuple((self.minimum[axis] + self.maximum[axis]) * 0.5 for axis in range(3))


@dataclasses.dataclass(slots=True)
class _BvhBuildNode:
    items: list[_BvhBuildItem] | None = None
    children: list["_BvhBuildNode"] | None = None
    minimum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    maximum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    index: int = 0

    @property
    def total_nodes(self) -> int:
        count = 1
        if self.children:
            for child in self.children:
                count += child.total_nodes
        return count

    @property
    def total_items(self) -> int:
        count = len(self.items or [])
        if self.children:
            for child in self.children:
                count += child.total_items
        return count

    def update_bounds(self) -> None:
        if self.items:
            source = [BoundAabb(item.minimum, item.maximum) for item in self.items]
        else:
            source = [BoundAabb(child.minimum, child.maximum) for child in (self.children or [])]
        bounds = _merge_aabbs(source, BoundAabb((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))
        self.minimum = bounds.minimum
        self.maximum = bounds.maximum

    def build(self, item_threshold: int) -> None:
        self.update_bounds()
        if not self.items or len(self.items) <= item_threshold:
            return

        average = [0.0, 0.0, 0.0]
        for item in self.items:
            average[0] += item.minimum[0] + item.maximum[0]
            average[1] += item.minimum[1] + item.maximum[1]
            average[2] += item.minimum[2] + item.maximum[2]
        count = 0.5 / len(self.items)
        average = [component * count for component in average]

        counts = [0, 0, 0]
        for item in self.items:
            center = item.center
            if center[0] < average[0]:
                counts[0] += 1
            if center[1] < average[1]:
                counts[1] += 1
            if center[2] < average[2]:
                counts[2] += 1

        target = len(self.items) / 2.0
        deltas = [abs(target - value) for value in counts]
        axis = min(range(3), key=deltas.__getitem__)

        upper: list[_BvhBuildItem] = []
        lower: list[_BvhBuildItem] = []
        for item in self.items:
            center = item.center
            goes_upper = center[axis] > average[axis]
            (upper if goes_upper else lower).append(item)

        if not upper or not lower:
            all_items = sorted(self.items, key=lambda item: (item.minimum, item.maximum))
            midpoint = len(all_items) // 2
            upper = all_items[:midpoint]
            lower = all_items[midpoint:]
            if not upper or not lower:
                return

        self.items = None
        self.children = [
            _BvhBuildNode(items=upper),
            _BvhBuildNode(items=lower),
        ]
        for child in self.children:
            child.build(item_threshold)
        self.children.sort(key=lambda child: child.total_items, reverse=True)
        self.update_bounds()

    def gather_nodes(self, nodes: list["_BvhBuildNode"]) -> None:
        self.index = len(nodes)
        nodes.append(self)
        for child in self.children or []:
            child.gather_nodes(nodes)

    def gather_trees(self, trees: list["_BvhBuildNode"], max_tree_node_count: int) -> None:
        if self.total_nodes > max_tree_node_count and self.children:
            for child in self.children:
                child.gather_trees(trees, max_tree_node_count)
            return
        trees.append(self)


def _polygon_material_indices_for_write(bound: BoundGeometry, polygons: list[BoundPolygon] | None = None) -> list[int]:
    source = polygons or bound.polygons
    indices: list[int] = []
    for index, polygon in enumerate(source):
        if polygon.material_index >= 0:
            indices.append(int(polygon.material_index) & 0xFF)
        elif index < len(bound.polygon_material_indices):
            indices.append(int(bound.polygon_material_indices[index]) & 0xFF)
        else:
            indices.append(0)
    return indices


def _needs_bvh_rebuild(bound: BoundGeometry, bvh: BoundBvh | None) -> bool:
    if bvh is None or not bvh.nodes or not bvh.trees:
        return True
    if len(bound.polygons) <= _GEOMETRY_BVH_ITEM_THRESHOLD:
        return False
    if len(bvh.nodes) != 1 or len(bvh.trees) != 1:
        return False
    node = bvh.nodes[0]
    return node.is_leaf and node.item_id == 0 and node.item_count >= len(bound.polygons)


def _reordered_leaf_polygons(nodes: list[_BvhBuildNode], item_threshold: int) -> list[_BvhBuildItem]:
    if item_threshold <= 1:
        result: list[_BvhBuildItem] = []
        for node in nodes:
            if node.items:
                result.extend(node.items)
        return result

    result: list[_BvhBuildItem] = []
    for node in nodes:
        if node.items:
            result.extend(node.items)
    return result


def _copy_polygon_for_reorder(
    polygon: BoundPolygon,
    *,
    new_index: int,
    edge_lookup: dict[int, int],
) -> BoundPolygon:
    new_polygon = dataclasses.replace(polygon, index=new_index)
    if isinstance(new_polygon, BoundPolygonTriangle):
        new_polygon.edge_index1 = edge_lookup.get(polygon.edge_index1, 0xFFFF)
        new_polygon.edge_index2 = edge_lookup.get(polygon.edge_index2, 0xFFFF)
        new_polygon.edge_index3 = edge_lookup.get(polygon.edge_index3, 0xFFFF)
    return new_polygon


def _build_geometry_bvh(bound: BoundGeometry, item_threshold: int = _GEOMETRY_BVH_ITEM_THRESHOLD) -> tuple[BoundBvh, list[BoundPolygon], list[int]]:
    items: list[_BvhBuildItem] = []
    for index, polygon in enumerate(bound.polygons):
        bounds = _primitive_bounds(bound, polygon)
        items.append(
            _BvhBuildItem(
                minimum=bounds.minimum,
                maximum=bounds.maximum,
                index=index,
                polygon=polygon,
            )
        )

    if not items:
        fallback = BoundAabb(bound.box_min, bound.box_max)
        center = tuple((fallback.minimum[axis] + fallback.maximum[axis]) * 0.5 for axis in range(3))
        quantum = _choose_bvh_quantum(fallback, center)
        quantum_inverse = tuple((1.0 / value) if value else 0.0 for value in quantum)
        return (
            BoundBvh(
                minimum=fallback.minimum,
                maximum=fallback.maximum,
                center=center,
                quantum_inverse=quantum_inverse,
                quantum=quantum,
                nodes=[],
                trees=[],
            ),
            [],
            [],
        )

    root = _BvhBuildNode(items=list(items))
    root.build(item_threshold)

    nodes: list[_BvhBuildNode] = []
    root.gather_nodes(nodes)
    trees: list[_BvhBuildNode] = []
    root.gather_trees(trees, _MAX_BVH_TREE_NODE_COUNT)

    ordered_items = _reordered_leaf_polygons(nodes, item_threshold)
    item_lookup = {item.index: new_index for new_index, item in enumerate(ordered_items)}

    reordered_polygons: list[BoundPolygon] = []
    reordered_material_indices: list[int] = []
    source_material_indices = _polygon_material_indices_for_write(bound)
    for new_index, item in enumerate(ordered_items):
        reordered_polygons.append(_copy_polygon_for_reorder(item.polygon, new_index=new_index, edge_lookup=item_lookup))
        reordered_material_indices.append(source_material_indices[item.index] if item.index < len(source_material_indices) else 0)
        item.index = new_index

    overall = BoundAabb(root.minimum, root.maximum)
    center = tuple((overall.minimum[axis] + overall.maximum[axis]) * 0.5 for axis in range(3))
    quantum = _choose_bvh_quantum(overall, center)
    quantum_inverse = tuple((1.0 / value) if value else 0.0 for value in quantum)

    bvh_nodes: list[BoundBvhNode] = []
    for node in nodes:
        is_leaf = bool(node.items)
        bvh_nodes.append(
            BoundBvhNode(
                minimum=node.minimum,
                maximum=node.maximum,
                item_id=(node.items[0].index if is_leaf and node.items else node.total_nodes),
                item_count=(node.total_items if is_leaf else 0),
            )
        )

    bvh_trees: list[BoundBvhTree] = []
    for tree in trees:
        bvh_trees.append(
            BoundBvhTree(
                minimum=tree.minimum,
                maximum=tree.maximum,
                node_index=tree.index,
                node_index2=tree.index + tree.total_nodes,
            )
        )

    return (
        BoundBvh(
            minimum=overall.minimum,
            maximum=overall.maximum,
            center=center,
            quantum_inverse=quantum_inverse,
            quantum=quantum,
            nodes=bvh_nodes,
            trees=bvh_trees,
        ),
        reordered_polygons,
        reordered_material_indices,
    )


def _write_bvh(writer: ResourceWriter, bound: BoundGeometry) -> int:
    bvh = bound.bvh if isinstance(bound, BoundBVH) else None
    if _needs_bvh_rebuild(bound, bvh):
        bvh, _, _ = _build_geometry_bvh(bound)
    assert bvh is not None

    nodes_offset = 0
    if bvh.nodes:
        nodes_offset = writer.alloc(len(bvh.nodes) * 16, 16)
        for index, node in enumerate(bvh.nodes):
            qmin = _quantize_bvh_point(node.minimum, bvh.center, bvh.quantum_inverse)
            qmax = _quantize_bvh_point(node.maximum, bvh.center, bvh.quantum_inverse)
            writer.pack_into("6hHH", nodes_offset + (index * 16), *qmin, *qmax, node.item_id, node.item_count)

    trees_offset = 0
    if bvh.trees:
        trees_offset = writer.alloc(len(bvh.trees) * 16, 16)
        for index, tree in enumerate(bvh.trees):
            qmin = _quantize_bvh_point(tree.minimum, bvh.center, bvh.quantum_inverse)
            qmax = _quantize_bvh_point(tree.maximum, bvh.center, bvh.quantum_inverse)
            writer.pack_into("6hHH", trees_offset + (index * 16), *qmin, *qmax, tree.node_index, tree.node_index2)

    bvh_offset = writer.alloc(_BVH_BLOCK_SIZE, 16)
    writer.pack_into("Q", bvh_offset + 0x00, _virtual(nodes_offset) if nodes_offset else 0)
    writer.pack_into("I", bvh_offset + 0x08, len(bvh.nodes))
    writer.pack_into("I", bvh_offset + 0x0C, len(bvh.nodes))
    writer.pack_into("I", bvh_offset + 0x10, 0)
    writer.pack_into("I", bvh_offset + 0x14, 0)
    writer.pack_into("I", bvh_offset + 0x18, 0)
    writer.pack_into("I", bvh_offset + 0x1C, 0)
    writer.pack_into("3f", bvh_offset + 0x20, *bvh.minimum)
    writer.pack_into("f", bvh_offset + 0x2C, 0.0)
    writer.pack_into("3f", bvh_offset + 0x30, *bvh.maximum)
    writer.pack_into("f", bvh_offset + 0x3C, 0.0)
    writer.pack_into("3f", bvh_offset + 0x40, *bvh.center)
    writer.pack_into("f", bvh_offset + 0x4C, 0.0)
    writer.pack_into("3f", bvh_offset + 0x50, *bvh.quantum_inverse)
    writer.pack_into("f", bvh_offset + 0x5C, 0.0)
    writer.pack_into("3f", bvh_offset + 0x60, *bvh.quantum)
    writer.pack_into("f", bvh_offset + 0x6C, 0.0)
    writer.pack_into("Q", bvh_offset + 0x70, _virtual(trees_offset) if trees_offset else 0)
    writer.pack_into("H", bvh_offset + 0x78, len(bvh.trees))
    writer.pack_into("H", bvh_offset + 0x7A, len(bvh.trees))
    writer.pack_into("I", bvh_offset + 0x7C, 0)
    return bvh_offset


def _write_geometry(writer: ResourceWriter, offset: int, bound: BoundGeometry, *, with_bvh: bool) -> None:
    polygons = bound.polygons
    polygon_material_indices = _polygon_material_indices_for_write(bound)
    if with_bvh and _needs_bvh_rebuild(bound, bound.bvh if isinstance(bound, BoundBVH) else None):
        _, polygons, polygon_material_indices = _build_geometry_bvh(bound)

    center_geom = _choose_center_geom(bound)
    quantum = bound.quantum if bound.quantum != (1.0, 1.0, 1.0) or not bound.vertices else _choose_quantum(bound.vertices, center_geom)
    vertices_shrunk = _choose_vertices_shrunk(bound, with_bvh=with_bvh)
    octants = _choose_octants(bound, vertices_shrunk, with_bvh=with_bvh)

    vertices_shrunk_offset = 0
    vertices_shrunk_count = len(vertices_shrunk) if vertices_shrunk else len(bound.vertices)
    if vertices_shrunk:
        vertices_shrunk_blob = _quantize_vertices(vertices_shrunk, center_geom, quantum)
        vertices_shrunk_offset = writer.alloc(len(vertices_shrunk_blob), 16)
        writer.data[vertices_shrunk_offset : vertices_shrunk_offset + len(vertices_shrunk_blob)] = vertices_shrunk_blob

    vertices_offset = 0
    if bound.vertices:
        vertices_blob = _quantize_vertices(bound.vertices, center_geom, quantum)
        vertices_offset = writer.alloc(len(vertices_blob), 16)
        writer.data[vertices_offset : vertices_offset + len(vertices_blob)] = vertices_blob

    polygons_offset = 0
    if polygons:
        polygons_blob = b"".join(_encode_polygon(polygon) for polygon in polygons)
        polygons_offset = writer.alloc(len(polygons_blob), 16)
        writer.data[polygons_offset : polygons_offset + len(polygons_blob)] = polygons_blob

    materials_offset = 0
    if bound.materials:
        padded_materials = list(bound.materials)
        while len(padded_materials) < 4:
            padded_materials.append(BoundMaterial())
        materials_offset = writer.alloc(len(padded_materials) * 8, 16)
        for index, material in enumerate(padded_materials):
            data1, data2 = _material_data(material)
            writer.pack_into("II", materials_offset + (index * 8), data1, data2)

    material_colours_offset = 0
    if bound.material_colours:
        material_colours_offset = writer.alloc(len(bound.material_colours) * 4, 4)
        for index, colour in enumerate(bound.material_colours):
            writer.pack_into("4B", material_colours_offset + (index * 4), colour.r, colour.g, colour.b, colour.a)

    vertex_colours_offset = 0
    if bound.vertex_colours:
        vertex_colours_offset = writer.alloc(len(bound.vertex_colours) * 4, 4)
        for index, colour in enumerate(bound.vertex_colours):
            writer.pack_into("4B", vertex_colours_offset + (index * 4), colour.r, colour.g, colour.b, colour.a)

    polygon_material_indices_offset = 0
    if polygons:
        polygon_material_indices_blob = bytes(index & 0xFF for index in polygon_material_indices)
        polygon_material_indices_offset = writer.alloc(len(polygon_material_indices_blob), 16)
        writer.data[polygon_material_indices_offset : polygon_material_indices_offset + len(polygon_material_indices_blob)] = polygon_material_indices_blob

    octants_offset, octant_items_offset = _write_octants(writer, octants)

    writer.pack_into("I", offset + 0x70, 0)
    writer.pack_into("I", offset + 0x74, 0)
    writer.pack_into("Q", offset + 0x78, _virtual(vertices_shrunk_offset) if vertices_shrunk_offset else 0)
    writer.pack_into("H", offset + 0x80, 0)
    writer.pack_into("H", offset + 0x82, 0)
    writer.pack_into("I", offset + 0x84, vertices_shrunk_count)
    writer.pack_into("Q", offset + 0x88, _virtual(polygons_offset) if polygons_offset else 0)
    writer.pack_into("3f", offset + 0x90, *quantum)
    writer.pack_into("f", offset + 0x9C, 0.0)
    writer.pack_into("3f", offset + 0xA0, *center_geom)
    writer.pack_into("f", offset + 0xAC, 0.0)
    writer.pack_into("Q", offset + 0xB0, _virtual(vertices_offset) if vertices_offset else 0)
    writer.pack_into("Q", offset + 0xB8, _virtual(vertex_colours_offset) if vertex_colours_offset else 0)
    writer.pack_into("Q", offset + 0xC0, _virtual(octants_offset) if octants_offset else 0)
    writer.pack_into("Q", offset + 0xC8, _virtual(octant_items_offset) if octant_items_offset else 0)
    writer.pack_into("I", offset + 0xD0, len(bound.vertices))
    writer.pack_into("I", offset + 0xD4, len(polygons))
    writer.pack_into("I", offset + 0xD8, 0)
    writer.pack_into("I", offset + 0xDC, 0)
    writer.pack_into("I", offset + 0xE0, 0)
    writer.pack_into("I", offset + 0xE4, 0)
    writer.pack_into("I", offset + 0xE8, 0)
    writer.pack_into("I", offset + 0xEC, 0)
    writer.pack_into("Q", offset + 0xF0, _virtual(materials_offset) if materials_offset else 0)
    writer.pack_into("Q", offset + 0xF8, _virtual(material_colours_offset) if material_colours_offset else 0)
    writer.pack_into("I", offset + 0x100, 0)
    writer.pack_into("I", offset + 0x104, 0)
    writer.pack_into("I", offset + 0x108, 0)
    writer.pack_into("I", offset + 0x10C, 0)
    writer.pack_into("I", offset + 0x110, 0)
    writer.pack_into("I", offset + 0x114, 0)
    writer.pack_into("Q", offset + 0x118, _virtual(polygon_material_indices_offset) if polygon_material_indices_offset else 0)
    writer.pack_into("B", offset + 0x120, len(bound.materials) & 0xFF)
    writer.pack_into("B", offset + 0x121, len(bound.material_colours) & 0xFF)
    writer.pack_into("H", offset + 0x122, 0)
    writer.pack_into("I", offset + 0x124, 0)
    writer.pack_into("I", offset + 0x128, 0)
    writer.pack_into("I", offset + 0x12C, 0)
    if with_bvh:
        bvh_offset = _write_bvh(writer, bound)
        writer.pack_into("Q", offset + 0x130, _virtual(bvh_offset))
        writer.pack_into("I", offset + 0x138, 0)
        writer.pack_into("I", offset + 0x13C, 0)
        writer.pack_into("H", offset + 0x140, 0xFFFF)
        writer.pack_into("H", offset + 0x142, 0)
        writer.pack_into("I", offset + 0x144, 0)
        writer.pack_into("I", offset + 0x148, 0)
        writer.pack_into("I", offset + 0x14C, 0)


def build_bound_system_data(bound: Bound) -> bytes:
    writer = ResourceWriter(_bound_size(bound))
    _write_bound(writer, bound, offset=0)
    return writer.finish()


def write_bound_resource(writer: ResourceWriter, bound: Bound) -> int:
    return _write_bound(writer, bound)


__all__ = [
    "build_bound_system_data",
    "write_bound_resource",
]
