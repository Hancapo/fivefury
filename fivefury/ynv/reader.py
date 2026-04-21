from __future__ import annotations

import struct
from pathlib import Path

from ..binary import f32, i16, u16, u32, u64, vec3, vec4
from ..resource import RSC7_MAGIC, checked_virtual_offset, get_resource_total_page_count, split_rsc7_sections
from .model import (
    Ynv,
    YnvAabb,
    YnvContentFlags,
    YnvEdge,
    YnvEdgePart,
    YnvListInfo,
    YnvPoint,
    YnvPoly,
    YnvPortal,
    YnvSector,
    YnvSectorData,
)

_ROOT_SIZE = 0x170
_LIST_HEADER_SIZE = 0x30
_LIST_PART_SIZE = 0x10
_VERTEX_SIZE = 0x06
_EDGE_SIZE = 0x08
_POLY_SIZE = 0x30
_SECTOR_SIZE = 0x60
_SECTOR_DATA_SIZE = 0x20
_POINT_SIZE = 0x08
_PORTAL_SIZE = 0x1C


def _decode_vertex(data: bytes, offset: int, posoffset: tuple[float, float, float], aabb_size: tuple[float, float, float]) -> tuple[float, float, float]:
    scale = 65535.0
    x = posoffset[0] + ((u16(data, offset + 0x00) / scale) * aabb_size[0])
    y = posoffset[1] + ((u16(data, offset + 0x02) / scale) * aabb_size[1])
    z = posoffset[2] + ((u16(data, offset + 0x04) / scale) * aabb_size[2])
    return (x, y, z)


def _decode_point(data: bytes, offset: int, posoffset: tuple[float, float, float], aabb_size: tuple[float, float, float]) -> YnvPoint:
    return YnvPoint(
        position=_decode_vertex(data, offset, posoffset, aabb_size),
        angle=data[offset + 0x06],
        type=data[offset + 0x07],
    )


def _read_list_header(system_data: bytes, pointer: int) -> tuple[YnvListInfo, int, int, int]:
    offset = checked_virtual_offset(pointer, system_data)
    (
        vft,
        unknown_04h,
        item_count,
        unknown_0ch,
        list_parts_pointer,
        list_offsets_pointer,
        list_parts_count,
        unknown_24h,
        unknown_28h,
        unknown_2ch,
    ) = struct.unpack_from("<IIIIQQIIII", system_data, offset)
    return (
        YnvListInfo(
            vft=vft,
            unknown_04h=unknown_04h,
            unknown_0ch=unknown_0ch,
            unknown_24h=unknown_24h,
            unknown_28h=unknown_28h,
            unknown_2ch=unknown_2ch,
        ),
        int(item_count),
        int(list_parts_pointer),
        int(list_parts_count),
    )


def _read_list_items(
    system_data: bytes,
    *,
    list_parts_pointer: int,
    list_parts_count: int,
    item_size: int,
    decode_item,
) -> list[object]:
    if not list_parts_pointer or not list_parts_count:
        return []
    parts_offset = checked_virtual_offset(list_parts_pointer, system_data)
    items: list[object] = []
    for part_index in range(int(list_parts_count)):
        entry_offset = parts_offset + (part_index * _LIST_PART_SIZE)
        items_pointer, count, _unknown_0ch = struct.unpack_from("<QII", system_data, entry_offset)
        if not items_pointer or not count:
            continue
        items_offset = checked_virtual_offset(items_pointer, system_data)
        for item_index in range(int(count)):
            item_offset = items_offset + (item_index * item_size)
            items.append(decode_item(system_data, item_offset))
    return items


def _read_sector(system_data: bytes, pointer: int, posoffset: tuple[float, float, float], aabb_size: tuple[float, float, float]) -> YnvSector:
    offset = checked_virtual_offset(pointer, system_data)
    aabb_min = vec4(system_data, offset + 0x00)
    aabb_max = vec4(system_data, offset + 0x10)
    cell_aabb = YnvAabb.from_packed(
        i16(system_data, offset + 0x20),
        i16(system_data, offset + 0x22),
        i16(system_data, offset + 0x24),
        i16(system_data, offset + 0x26),
        i16(system_data, offset + 0x28),
        i16(system_data, offset + 0x2A),
    )
    data_pointer = u64(system_data, offset + 0x2C)
    subtree1_pointer = u64(system_data, offset + 0x34)
    subtree2_pointer = u64(system_data, offset + 0x3C)
    subtree3_pointer = u64(system_data, offset + 0x44)
    subtree4_pointer = u64(system_data, offset + 0x4C)
    sector_data: YnvSectorData | None = None
    if data_pointer:
        data_offset = checked_virtual_offset(data_pointer, system_data)
        points_start_id = u32(system_data, data_offset + 0x00)
        unused_04h = u32(system_data, data_offset + 0x04)
        poly_ids_pointer = u64(system_data, data_offset + 0x08)
        points_pointer = u64(system_data, data_offset + 0x10)
        poly_ids_count = u16(system_data, data_offset + 0x18)
        points_count = u16(system_data, data_offset + 0x1A)
        unused_1ch = u32(system_data, data_offset + 0x1C)
        poly_ids: list[int] = []
        if poly_ids_pointer and poly_ids_count:
            poly_ids_offset = checked_virtual_offset(poly_ids_pointer, system_data)
            poly_ids = [u16(system_data, poly_ids_offset + (index * 2)) for index in range(int(poly_ids_count))]
        points: list[YnvPoint] = []
        if points_pointer and points_count:
            points_offset = checked_virtual_offset(points_pointer, system_data)
            for index in range(int(points_count)):
                points.append(_decode_point(system_data, points_offset + (index * _POINT_SIZE), posoffset, aabb_size))
        sector_data = YnvSectorData(
            points_start_id=points_start_id,
            unused_04h=unused_04h,
            poly_ids=poly_ids,
            points=points,
            unused_1ch=unused_1ch,
        )
    return YnvSector(
        aabb_min=(float(aabb_min[0]), float(aabb_min[1]), float(aabb_min[2])),
        aabb_max=(float(aabb_max[0]), float(aabb_max[1]), float(aabb_max[2])),
        aabb_min_w=float(aabb_min[3]),
        aabb_max_w=float(aabb_max[3]),
        cell_aabb=cell_aabb,
        data=sector_data,
        subtree1=_read_sector(system_data, subtree1_pointer, posoffset, aabb_size) if subtree1_pointer else None,
        subtree2=_read_sector(system_data, subtree2_pointer, posoffset, aabb_size) if subtree2_pointer else None,
        subtree3=_read_sector(system_data, subtree3_pointer, posoffset, aabb_size) if subtree3_pointer else None,
        subtree4=_read_sector(system_data, subtree4_pointer, posoffset, aabb_size) if subtree4_pointer else None,
        unused_54h=u32(system_data, offset + 0x54),
        unused_58h=u32(system_data, offset + 0x58),
        unused_5ch=u32(system_data, offset + 0x5C),
    )


def read_ynv(source: bytes | bytearray | memoryview | str | Path, *, path: str | Path = "") -> Ynv:
    data = Path(source).read_bytes() if isinstance(source, (str, Path)) else bytes(source)
    if len(data) < 0x10:
        raise ValueError("YNV data is too short")
    if int.from_bytes(data[:4], "little") != RSC7_MAGIC:
        raise ValueError("YNV data must be a standalone RSC7 resource")

    header, system_data, _ = split_rsc7_sections(data)
    if len(system_data) < _ROOT_SIZE:
        raise ValueError("YNV system section is too short")

    content_flags = YnvContentFlags(u32(system_data, 0x10))
    version_unk1 = u32(system_data, 0x14)
    unused_018h = u32(system_data, 0x18)
    unused_01ch = u32(system_data, 0x1C)
    transform = struct.unpack_from("<16f", system_data, 0x20)
    aabb_size = vec3(system_data, 0x60)
    aabb_unk = u32(system_data, 0x6C)
    vertices_pointer = u64(system_data, 0x70)
    indices_pointer = u64(system_data, 0x80)
    edges_pointer = u64(system_data, 0x88)
    edges_indices_count = u32(system_data, 0x90)
    adjacent_area_ids_count = u32(system_data, 0x94)
    adjacent_area_ids = [u32(system_data, 0x98 + (index * 4)) for index in range(min(int(adjacent_area_ids_count), 32))]
    polys_pointer = u64(system_data, 0x118)
    sector_tree_pointer = u64(system_data, 0x120)
    portals_pointer = u64(system_data, 0x128)
    portal_links_pointer = u64(system_data, 0x130)
    vertices_count = u32(system_data, 0x138)
    polys_count = u32(system_data, 0x13C)
    area_id = u32(system_data, 0x140)
    total_bytes = u32(system_data, 0x144)
    points_count = u32(system_data, 0x148)
    portals_count = u32(system_data, 0x14C)
    portal_links_count = u32(system_data, 0x150)
    unused_154h = u32(system_data, 0x154)
    unused_158h = u32(system_data, 0x158)
    unused_15ch = u32(system_data, 0x15C)
    version_unk2 = u32(system_data, 0x160)
    unused_164h = u32(system_data, 0x164)
    unused_168h = u32(system_data, 0x168)
    unused_16ch = u32(system_data, 0x16C)

    posoffset = (0.0, 0.0, 0.0)
    if sector_tree_pointer:
        sector_tree_offset = checked_virtual_offset(sector_tree_pointer, system_data)
        posoffset = vec3(system_data, sector_tree_offset + 0x00)

    vertices_info, vertex_header_count, vertex_parts_pointer, vertex_parts_count = _read_list_header(system_data, vertices_pointer)
    vertices = _read_list_items(
        system_data,
        list_parts_pointer=vertex_parts_pointer,
        list_parts_count=vertex_parts_count,
        item_size=_VERTEX_SIZE,
        decode_item=lambda payload, offset: _decode_vertex(payload, offset, posoffset, aabb_size),
    )
    if vertex_header_count != int(vertices_count) and int(vertices_count):
        vertices = vertices[: int(vertices_count)]

    indices_info, index_header_count, index_parts_pointer, index_parts_count = _read_list_header(system_data, indices_pointer)
    indices = _read_list_items(
        system_data,
        list_parts_pointer=index_parts_pointer,
        list_parts_count=index_parts_count,
        item_size=2,
        decode_item=lambda payload, offset: u16(payload, offset),
    )
    if index_header_count != int(edges_indices_count) and int(edges_indices_count):
        indices = indices[: int(edges_indices_count)]

    edges_info, _edge_header_count, edge_parts_pointer, edge_parts_count = _read_list_header(system_data, edges_pointer)
    edges = _read_list_items(
        system_data,
        list_parts_pointer=edge_parts_pointer,
        list_parts_count=edge_parts_count,
        item_size=_EDGE_SIZE,
        decode_item=lambda payload, offset: YnvEdge(
            poly1=YnvEdgePart.from_value(u32(payload, offset + 0x00), adjacent_area_ids),
            poly2=YnvEdgePart.from_value(u32(payload, offset + 0x04), adjacent_area_ids),
        ),
    )
    if int(edges_indices_count):
        edges = edges[: int(edges_indices_count)]

    polys_info, poly_header_count, poly_parts_pointer, poly_parts_count = _read_list_header(system_data, polys_pointer)
    polys = _read_list_items(
        system_data,
        list_parts_pointer=poly_parts_pointer,
        list_parts_count=poly_parts_count,
        item_size=_POLY_SIZE,
        decode_item=lambda payload, offset: YnvPoly.from_packed(
            poly_flags0=u16(payload, offset + 0x00),
            index_flags=u16(payload, offset + 0x02),
            index_id=u16(payload, offset + 0x04),
            area_id=u16(payload, offset + 0x06),
            unknown_08h=u32(payload, offset + 0x08),
            unknown_0ch=u32(payload, offset + 0x0C),
            unknown_10h=u32(payload, offset + 0x10),
            unknown_14h=u32(payload, offset + 0x14),
            cell_aabb=YnvAabb.from_packed(
                i16(payload, offset + 0x18),
                i16(payload, offset + 0x1A),
                i16(payload, offset + 0x1C),
                i16(payload, offset + 0x1E),
                i16(payload, offset + 0x20),
                i16(payload, offset + 0x22),
            ),
            poly_flags1=u32(payload, offset + 0x24),
            poly_flags2=u32(payload, offset + 0x28),
            part_flags=u32(payload, offset + 0x2C),
        ),
    )
    if poly_header_count != int(polys_count) and int(polys_count):
        polys = polys[: int(polys_count)]

    sector_tree = _read_sector(system_data, sector_tree_pointer, posoffset, aabb_size) if sector_tree_pointer else None

    portals: list[YnvPortal] = []
    if portals_pointer and portals_count:
        portals_offset = checked_virtual_offset(portals_pointer, system_data)
        for index in range(int(portals_count)):
            offset = portals_offset + (index * _PORTAL_SIZE)
            area_flags = u32(system_data, offset + 0x18)
            portals.append(
                YnvPortal(
                    type=system_data[offset + 0x00],
                    angle=system_data[offset + 0x01],
                    flags_unk=u16(system_data, offset + 0x02),
                    position_from=_decode_vertex(system_data, offset + 0x04, posoffset, aabb_size),
                    position_to=_decode_vertex(system_data, offset + 0x0A, posoffset, aabb_size),
                    poly_id_from1=u16(system_data, offset + 0x10),
                    poly_id_from2=u16(system_data, offset + 0x12),
                    poly_id_to1=u16(system_data, offset + 0x14),
                    poly_id_to2=u16(system_data, offset + 0x16),
                    area_id_from=area_flags & 0x3FFF,
                    area_id_to=(area_flags >> 14) & 0x3FFF,
                    area_unk=(area_flags >> 28) & 0xF,
                )
            )

    portal_links: list[int] = []
    if portal_links_pointer and portal_links_count:
        portal_links_offset = checked_virtual_offset(portal_links_pointer, system_data)
        portal_links = [u16(system_data, portal_links_offset + (index * 2)) for index in range(int(portal_links_count))]

    ynv = Ynv(
        version=int(header.version),
        path=str(path or source) if isinstance(source, (str, Path)) or path else "",
        content_flags=content_flags,
        version_unk1=version_unk1,
        unused_018h=unused_018h,
        unused_01ch=unused_01ch,
        transform=tuple(float(value) for value in transform),
        aabb_size=(float(aabb_size[0]), float(aabb_size[1]), float(aabb_size[2])),
        aabb_unk=aabb_unk,
        vertices=vertices,
        indices=indices,
        edges=edges,
        polys=polys,
        sector_tree=sector_tree,
        portals=portals,
        portal_links=portal_links,
        adjacent_area_ids=adjacent_area_ids,
        vertices_info=vertices_info,
        indices_info=indices_info,
        edges_info=edges_info,
        polys_info=polys_info,
        area_id=area_id,
        total_bytes=total_bytes,
        points_count=points_count,
        unused_154h=unused_154h,
        unused_158h=unused_158h,
        unused_15ch=unused_15ch,
        version_unk2=version_unk2,
        unused_164h=unused_164h,
        unused_168h=unused_168h,
        unused_16ch=unused_16ch,
        system_pages_count=get_resource_total_page_count(header.system_flags),
        graphics_pages_count=get_resource_total_page_count(header.graphics_flags),
    )
    return ynv.build()


__all__ = ["read_ynv"]
