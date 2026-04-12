from __future__ import annotations

import struct

from ..binary import f32, u16, u32, u64, vec3, vec4
from ..resource import checked_virtual_offset, read_virtual_pointer_array
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
    BoundPolygonType,
    BoundResourcePagesInfo,
    BoundSphere,
    BoundTransform,
    BoundType,
)

_RESOURCE_FILE_BASE_SIZE = 0x10


def _virtual_offset(pointer: int, data: bytes) -> int:
    return checked_virtual_offset(pointer, data, base=0x50000000)


def _read_pointer_array(pointer: int, count: int, system_data: bytes) -> list[int]:
    return read_virtual_pointer_array(system_data, pointer, count, base=0x50000000)


def _dequantize_bvh_point(
    quantized: tuple[int, int, int],
    center: tuple[float, float, float],
    quantum: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        center[0] + (quantized[0] * quantum[0]),
        center[1] + (quantized[1] * quantum[1]),
        center[2] + (quantized[2] * quantum[2]),
    )


def _read_vertices(
    pointer: int,
    count: int,
    quantum: tuple[float, float, float],
    center_geom: tuple[float, float, float],
    system_data: bytes,
) -> list[tuple[float, float, float]]:
    if not pointer or count <= 0:
        return []
    start = _virtual_offset(pointer, system_data)
    end = start + (count * 6)
    if end > len(system_data):
        raise ValueError("vertex array is truncated")
    vertices: list[tuple[float, float, float]] = []
    for index in range(count):
        x, y, z = struct.unpack_from("<3h", system_data, start + (index * 6))
        vertices.append(
            (
                center_geom[0] + (x * quantum[0]),
                center_geom[1] + (y * quantum[1]),
                center_geom[2] + (z * quantum[2]),
            )
        )
    return vertices


def _decode_polygon(index: int, raw: bytes) -> BoundPolygon:
    raw_bytes = bytearray(raw)
    polygon_type_value = raw_bytes[0] & 0x07
    raw_bytes[0] &= 0xF8
    raw = bytes(raw_bytes)
    try:
        polygon_type = BoundPolygonType(polygon_type_value)
    except ValueError:
        polygon_type = BoundPolygonType.TRIANGLE
    common = {
        "polygon_type": polygon_type,
        "raw": raw,
        "index": index,
    }
    if polygon_type is BoundPolygonType.TRIANGLE:
        tri_area, tri_index1, tri_index2, tri_index3, edge_index1, edge_index2, edge_index3 = struct.unpack_from("<f6H", raw, 0)
        return BoundPolygonTriangle(
            **common,
            tri_area=tri_area,
            tri_index1=tri_index1,
            tri_index2=tri_index2,
            tri_index3=tri_index3,
            edge_index1=edge_index1,
            edge_index2=edge_index2,
            edge_index3=edge_index3,
        )
    if polygon_type is BoundPolygonType.SPHERE:
        sphere_type, sphere_index = struct.unpack_from("<HH", raw, 0)
        sphere_radius = struct.unpack_from("<f", raw, 4)[0]
        unused0, unused1 = struct.unpack_from("<II", raw, 8)
        return BoundPolygonSphere(
            **common,
            sphere_type=sphere_type,
            sphere_index=sphere_index,
            sphere_radius=sphere_radius,
            unused0=unused0,
            unused1=unused1,
        )
    if polygon_type is BoundPolygonType.CAPSULE:
        capsule_type, capsule_index1 = struct.unpack_from("<HH", raw, 0)
        capsule_radius = struct.unpack_from("<f", raw, 4)[0]
        capsule_index2, unused0 = struct.unpack_from("<HH", raw, 8)
        unused1 = struct.unpack_from("<I", raw, 12)[0]
        return BoundPolygonCapsule(
            **common,
            capsule_type=capsule_type,
            capsule_index1=capsule_index1,
            capsule_radius=capsule_radius,
            capsule_index2=capsule_index2,
            unused0=unused0,
            unused1=unused1,
        )
    if polygon_type is BoundPolygonType.BOX:
        box_type, box_index1, box_index2, box_index3, box_index4, unused0 = struct.unpack_from("<I4hI", raw, 0)
        return BoundPolygonBox(
            **common,
            box_type=box_type,
            box_index1=box_index1,
            box_index2=box_index2,
            box_index3=box_index3,
            box_index4=box_index4,
            unused0=unused0,
        )
    if polygon_type is BoundPolygonType.CYLINDER:
        cylinder_type, cylinder_index1 = struct.unpack_from("<HH", raw, 0)
        cylinder_radius = struct.unpack_from("<f", raw, 4)[0]
        cylinder_index2, unused0 = struct.unpack_from("<HH", raw, 8)
        unused1 = struct.unpack_from("<I", raw, 12)[0]
        return BoundPolygonCylinder(
            **common,
            cylinder_type=cylinder_type,
            cylinder_index1=cylinder_index1,
            cylinder_radius=cylinder_radius,
            cylinder_index2=cylinder_index2,
            unused0=unused0,
            unused1=unused1,
        )
    return BoundPolygon(**common)


def _read_polygon_types(pointer: int, count: int, system_data: bytes) -> list[BoundPolygon]:
    if not pointer or count <= 0:
        return []
    start = _virtual_offset(pointer, system_data)
    end = start + (count * 16)
    if end > len(system_data):
        raise ValueError("polygon array is truncated")
    polygons: list[BoundPolygon] = []
    for index in range(count):
        raw = system_data[start + (index * 16) : start + ((index + 1) * 16)]
        polygons.append(_decode_polygon(index, raw))
    return polygons


def _read_bvh(pointer: int, system_data: bytes) -> BoundBvh | None:
    if not pointer:
        return None
    offset = _virtual_offset(pointer, system_data)
    nodes_pointer = u64(system_data, offset + 0x00)
    nodes_count = u32(system_data, offset + 0x08)
    minimum = vec3(system_data, offset + 0x20)
    maximum = vec3(system_data, offset + 0x30)
    center = vec3(system_data, offset + 0x40)
    quantum_inverse = vec3(system_data, offset + 0x50)
    quantum = vec3(system_data, offset + 0x60)
    trees_pointer = u64(system_data, offset + 0x70)
    trees_count = u16(system_data, offset + 0x78)

    nodes: list[BoundBvhNode] = []
    if nodes_pointer and nodes_count > 0:
        start = _virtual_offset(nodes_pointer, system_data)
        end = start + (nodes_count * 16)
        if end > len(system_data):
            raise ValueError("BVH node array is truncated")
        for index in range(nodes_count):
            qmin_x, qmin_y, qmin_z, qmax_x, qmax_y, qmax_z, item_id, item_count = struct.unpack_from(
                "<6hHH",
                system_data,
                start + (index * 16),
            )
            nodes.append(
                BoundBvhNode(
                    minimum=_dequantize_bvh_point((qmin_x, qmin_y, qmin_z), center, quantum),
                    maximum=_dequantize_bvh_point((qmax_x, qmax_y, qmax_z), center, quantum),
                    item_id=item_id,
                    item_count=item_count,
                )
            )

    trees: list[BoundBvhTree] = []
    if trees_pointer and trees_count > 0:
        start = _virtual_offset(trees_pointer, system_data)
        end = start + (trees_count * 16)
        if end > len(system_data):
            raise ValueError("BVH tree array is truncated")
        for index in range(trees_count):
            qmin_x, qmin_y, qmin_z, qmax_x, qmax_y, qmax_z, node_index, node_index2 = struct.unpack_from(
                "<6hHH",
                system_data,
                start + (index * 16),
            )
            trees.append(
                BoundBvhTree(
                    minimum=_dequantize_bvh_point((qmin_x, qmin_y, qmin_z), center, quantum),
                    maximum=_dequantize_bvh_point((qmax_x, qmax_y, qmax_z), center, quantum),
                    node_index=node_index,
                    node_index2=node_index2,
                )
            )

    return BoundBvh(
        minimum=minimum,
        maximum=maximum,
        center=center,
        quantum_inverse=quantum_inverse,
        quantum=quantum,
        nodes=nodes,
        trees=trees,
    )


def _read_materials(pointer: int, count: int, system_data: bytes) -> list[BoundMaterial]:
    if not pointer or count <= 0:
        return []
    start = _virtual_offset(pointer, system_data)
    end = start + (count * 8)
    if end > len(system_data):
        raise ValueError("material array is truncated")
    materials: list[BoundMaterial] = []
    for index in range(count):
        data1, data2 = struct.unpack_from("<II", system_data, start + (index * 8))
        materials.append(
            BoundMaterial(
                type=data1 & 0xFF,
                procedural_id=(data1 >> 8) & 0xFF,
                room_id=(data1 >> 16) & 0x1F,
                ped_density=(data1 >> 21) & 0x07,
                flags=((data1 >> 24) & 0xFF) | ((data2 & 0xFF) << 8),
                material_color_index=(data2 >> 8) & 0xFF,
                unknown=(data2 >> 16) & 0xFFFF,
                data1=data1,
                data2=data2,
            )
        )
    return materials


def _read_material_colours(pointer: int, count: int, system_data: bytes) -> list[BoundMaterialColor]:
    if not pointer or count <= 0:
        return []
    start = _virtual_offset(pointer, system_data)
    end = start + (count * 4)
    if end > len(system_data):
        raise ValueError("material colour array is truncated")
    colours: list[BoundMaterialColor] = []
    for index in range(count):
        r, g, b, a = struct.unpack_from("<4B", system_data, start + (index * 4))
        colours.append(BoundMaterialColor(r=r, g=g, b=b, a=a))
    return colours


def _read_bytes(pointer: int, count: int, system_data: bytes) -> list[int]:
    if not pointer or count <= 0:
        return []
    start = _virtual_offset(pointer, system_data)
    end = start + count
    if end > len(system_data):
        raise ValueError("byte array is truncated")
    return list(system_data[start:end])


def _read_octants(octants_pointer: int, octant_items_pointer: int, system_data: bytes) -> BoundGeometryOctants | None:
    if not octants_pointer or not octant_items_pointer:
        return None
    counts_offset = _virtual_offset(octants_pointer, system_data)
    items_offset = _virtual_offset(octant_items_pointer, system_data)
    counts = [u32(system_data, counts_offset + (index * 4)) for index in range(8)]
    item_pointers = [u64(system_data, items_offset + (index * 8)) for index in range(8)]
    items: list[list[int]] = []
    for count, item_pointer in zip(counts, item_pointers, strict=True):
        if count <= 0 or not item_pointer:
            items.append([])
            continue
        item_offset = _virtual_offset(item_pointer, system_data)
        end = item_offset + (count * 4)
        if end > len(system_data):
            raise ValueError("octant item array is truncated")
        items.append([u32(system_data, item_offset + (index * 4)) for index in range(count)])
    octants = BoundGeometryOctants(items=items)
    return octants if octants.has_items else None


def _read_matrix4f(offset: int, system_data: bytes) -> BoundTransform:
    c1 = vec3(system_data, offset + 0x00)
    f1 = u32(system_data, offset + 0x0C)
    c2 = vec3(system_data, offset + 0x10)
    f2 = u32(system_data, offset + 0x1C)
    c3 = vec3(system_data, offset + 0x20)
    f3 = u32(system_data, offset + 0x2C)
    c4 = vec3(system_data, offset + 0x30)
    f4 = u32(system_data, offset + 0x3C)
    return BoundTransform(c1, c2, c3, c4, f1, f2, f3, f4)


def _read_aabb(offset: int, system_data: bytes) -> BoundAabb:
    minimum = vec4(system_data, offset + 0x00)[:3]
    maximum = vec4(system_data, offset + 0x10)[:3]
    return BoundAabb(minimum=minimum, maximum=maximum)


def _read_composite_flags(offset: int, system_data: bytes) -> BoundCompositeFlags:
    return BoundCompositeFlags(flags1=u32(system_data, offset + 0x00), flags2=u32(system_data, offset + 0x04))


def _read_resource_pages_info(pointer: int, system_data: bytes) -> BoundResourcePagesInfo | None:
    if not pointer:
        return None
    offset = _virtual_offset(pointer, system_data)
    return BoundResourcePagesInfo(
        unknown_0h=u32(system_data, offset + 0x00),
        unknown_4h=u32(system_data, offset + 0x04),
        system_pages_count=system_data[offset + 0x08],
        graphics_pages_count=system_data[offset + 0x09],
        unknown_ah=u16(system_data, offset + 0x0A),
        unknown_ch=u32(system_data, offset + 0x0C),
    )


def _read_bound_common(offset: int, system_data: bytes) -> dict[str, object]:
    data_offset = offset + _RESOURCE_FILE_BASE_SIZE
    pages_info_pointer = u64(system_data, offset + 0x08)
    room_and_density = system_data[data_offset + 0x4E]
    return {
        "file_vft": u32(system_data, offset + 0x00),
        "file_unknown": u32(system_data, offset + 0x04),
        "file_pages_info": _read_resource_pages_info(pages_info_pointer, system_data),
        "bound_type": BoundType(system_data[data_offset + 0x00]),
        "unknown_11h": system_data[data_offset + 0x01],
        "unknown_12h": u16(system_data, data_offset + 0x02),
        "sphere_radius": f32(system_data, data_offset + 0x04),
        "unknown_18h": u32(system_data, data_offset + 0x08),
        "unknown_1ch": u32(system_data, data_offset + 0x0C),
        "box_max": vec3(system_data, data_offset + 0x20),
        "margin": f32(system_data, data_offset + 0x2C),
        "box_min": vec3(system_data, data_offset + 0x30),
        "unknown_3ch": u32(system_data, data_offset + 0x3C),
        "box_center": vec3(system_data, data_offset + 0x40),
        "material_index": system_data[data_offset + 0x4C],
        "procedural_id": system_data[data_offset + 0x4D],
        "room_id": room_and_density & 0x1F,
        "ped_density": (room_and_density >> 5) & 0x07,
        "unk_flags": system_data[data_offset + 0x4F],
        "sphere_center": vec3(system_data, data_offset + 0x50),
        "poly_flags": system_data[data_offset + 0x5C],
        "material_color_index": system_data[data_offset + 0x5D],
        "unknown_5eh": u16(system_data, data_offset + 0x5E),
        "unknown_60h": vec3(system_data, data_offset + 0x60),
        "volume": f32(system_data, data_offset + 0x6C),
    }


def _read_geometry(offset: int, system_data: bytes, *, with_bvh: bool) -> BoundGeometry:
    values = _read_bound_common(offset, system_data)
    quantum = vec3(system_data, offset + 0x90)
    center_geom = vec3(system_data, offset + 0xA0)
    vertices_count = u32(system_data, offset + 0xD0)
    polygons_count = u32(system_data, offset + 0xD4)
    materials_count = system_data[offset + 0x120]
    material_colours_count = system_data[offset + 0x121]

    geometry_cls = BoundBVH if with_bvh else BoundGeometry
    geometry = geometry_cls(
        **values,
        quantum=quantum,
        center_geom=center_geom,
        vertices=_read_vertices(u64(system_data, offset + 0xB0), vertices_count, quantum, center_geom, system_data),
        vertices_shrunk=_read_vertices(u64(system_data, offset + 0x78), vertices_count, quantum, center_geom, system_data),
        polygons=_read_polygon_types(u64(system_data, offset + 0x88), polygons_count, system_data),
        polygon_material_indices=_read_bytes(u64(system_data, offset + 0x118), polygons_count, system_data),
        materials=_read_materials(u64(system_data, offset + 0xF0), max(4, materials_count) if materials_count else 0, system_data)[:materials_count or 0],
        material_colours=_read_material_colours(u64(system_data, offset + 0xF8), material_colours_count, system_data),
        vertex_colours=_read_material_colours(u64(system_data, offset + 0xB8), vertices_count, system_data),
        octants=None if with_bvh else _read_octants(u64(system_data, offset + 0xC0), u64(system_data, offset + 0xC8), system_data),
    )
    for index, polygon in enumerate(geometry.polygons):
        if index < len(geometry.polygon_material_indices):
            polygon.material_index = geometry.polygon_material_indices[index]
    if with_bvh:
        geometry.bvh_pointer = u64(system_data, offset + 0x130)
        geometry.bvh = _read_bvh(geometry.bvh_pointer, system_data)
    return geometry


def _read_composite(offset: int, system_data: bytes) -> BoundComposite:
    values = _read_bound_common(offset, system_data)
    children_pointer = u64(system_data, offset + 0x70)
    transforms1_pointer = u64(system_data, offset + 0x78)
    transforms2_pointer = u64(system_data, offset + 0x80)
    child_bounds_pointer = u64(system_data, offset + 0x88)
    flags1_pointer = u64(system_data, offset + 0x90)
    flags2_pointer = u64(system_data, offset + 0x98)
    children_count = u16(system_data, offset + 0xA0)
    bvh_pointer = u64(system_data, offset + 0xA8)

    child_pointers = _read_pointer_array(children_pointer, children_count, system_data)
    transforms1 = []
    transforms2 = []
    child_bounds = []
    flags1 = []
    flags2 = []
    if transforms1_pointer:
        start = _virtual_offset(transforms1_pointer, system_data)
        transforms1 = [_read_matrix4f(start + (index * 0x40), system_data) for index in range(children_count)]
    if transforms2_pointer:
        start = _virtual_offset(transforms2_pointer, system_data)
        transforms2 = [_read_matrix4f(start + (index * 0x40), system_data) for index in range(children_count)]
    if child_bounds_pointer:
        start = _virtual_offset(child_bounds_pointer, system_data)
        child_bounds = [_read_aabb(start + (index * 0x20), system_data) for index in range(children_count)]
    if flags1_pointer:
        start = _virtual_offset(flags1_pointer, system_data)
        flags1 = [_read_composite_flags(start + (index * 0x08), system_data) for index in range(children_count)]
    if flags2_pointer:
        start = _virtual_offset(flags2_pointer, system_data)
        flags2 = [_read_composite_flags(start + (index * 0x08), system_data) for index in range(children_count)]

    children: list[BoundChild] = []
    for index, child_pointer in enumerate(child_pointers):
        child = read_bound_from_pointer(child_pointer, system_data)
        children.append(
            BoundChild(
                bound=child,
                transform=(transforms1[index] if index < len(transforms1) else transforms2[index] if index < len(transforms2) else None),
                bounds=child_bounds[index] if index < len(child_bounds) else None,
                flags1=flags1[index] if index < len(flags1) else None,
                flags2=flags2[index] if index < len(flags2) else None,
            )
        )
    return BoundComposite(
        **values,
        children=children,
        bvh_pointer=bvh_pointer,
        bvh=_read_bvh(bvh_pointer, system_data),
    )


def read_bound_at(offset: int, system_data: bytes) -> Bound:
    bound_type = BoundType(system_data[offset + _RESOURCE_FILE_BASE_SIZE + 0x00])
    values = _read_bound_common(offset, system_data)
    if bound_type is BoundType.SPHERE:
        return BoundSphere(**values)
    if bound_type is BoundType.BOX:
        return BoundBox(**values)
    if bound_type is BoundType.CAPSULE:
        return BoundCapsule(
            **values,
            unknown_70h=u32(system_data, offset + 0x70),
            unknown_74h=u32(system_data, offset + 0x74),
            unknown_78h=u32(system_data, offset + 0x78),
            unknown_7ch=u32(system_data, offset + 0x7C),
        )
    if bound_type is BoundType.DISC:
        return BoundDisc(
            **values,
            unknown_70h=u32(system_data, offset + 0x70),
            unknown_74h=u32(system_data, offset + 0x74),
            unknown_78h=u32(system_data, offset + 0x78),
            unknown_7ch=u32(system_data, offset + 0x7C),
        )
    if bound_type is BoundType.CYLINDER:
        return BoundCylinder(
            **values,
            unknown_70h=u32(system_data, offset + 0x70),
            unknown_74h=u32(system_data, offset + 0x74),
            unknown_78h=u32(system_data, offset + 0x78),
            unknown_7ch=u32(system_data, offset + 0x7C),
        )
    if bound_type is BoundType.CLOTH:
        return BoundCloth(
            **values,
            unknown_70h=u32(system_data, offset + 0x70),
            unknown_74h=u32(system_data, offset + 0x74),
            unknown_78h=u32(system_data, offset + 0x78),
            unknown_7ch=u32(system_data, offset + 0x7C),
        )
    if bound_type is BoundType.GEOMETRY:
        return _read_geometry(offset, system_data, with_bvh=False)
    if bound_type is BoundType.GEOMETRY_BVH:
        return _read_geometry(offset, system_data, with_bvh=True)
    if bound_type is BoundType.COMPOSITE:
        return _read_composite(offset, system_data)
    raise ValueError(f"unsupported bound type: {bound_type!r}")


def read_bound_from_pointer(pointer: int, system_data: bytes) -> Bound:
    if not pointer:
        raise ValueError("bound pointer is null")
    return read_bound_at(_virtual_offset(pointer, system_data), system_data)


__all__ = [
    "read_bound_at",
    "read_bound_from_pointer",
]
