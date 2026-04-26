from __future__ import annotations

import struct
from pathlib import Path

from ..binary import ByteWriter
from ..resource import build_rsc7, get_resource_total_page_count
from .model import Ynv, YnvEdge, YnvPoint, YnvPortal, YnvSector, YnvSectorData

_ROOT_SIZE = 0x170
_LIST_PART_SIZE = 0x10
_LIST_MAX_PART_BYTES = 0x4000
_VERTEX_SIZE = 0x06
_EDGE_SIZE = 0x08
_POLY_SIZE = 0x30
_SECTOR_SIZE = 0x60
_SECTOR_DATA_SIZE = 0x20
_POINT_SIZE = 0x08
_PORTAL_SIZE = 0x1C
_VIRTUAL_BASE = 0x50000000


def _virtual(offset: int) -> int:
    return _VIRTUAL_BASE + int(offset)


def _pack_vertex(position: tuple[float, float, float], posoffset: tuple[float, float, float], aabb_size: tuple[float, float, float]) -> bytes:
    values: list[int] = []
    for component, base, size in zip(position, posoffset, aabb_size, strict=True):
        if abs(size) < 1e-8:
            normalized = 0.0
        else:
            normalized = (float(component) - float(base)) / float(size)
        normalized = max(0.0, min(1.0, normalized))
        values.append(int(round(normalized * 65535.0)) & 0xFFFF)
    return struct.pack("<HHH", values[0], values[1], values[2])


def _pack_point(point: YnvPoint, posoffset: tuple[float, float, float], aabb_size: tuple[float, float, float]) -> bytes:
    return _pack_vertex(point.position, posoffset, aabb_size) + bytes((int(point.angle) & 0xFF, int(point.type) & 0xFF))


def _pack_portal(portal: YnvPortal, posoffset: tuple[float, float, float], aabb_size: tuple[float, float, float]) -> bytes:
    return (
        struct.pack("<BBH", int(portal.type) & 0xFF, int(portal.angle) & 0xFF, int(portal.flags_unk) & 0xFFFF)
        + _pack_vertex(portal.position_from, posoffset, aabb_size)
        + _pack_vertex(portal.position_to, posoffset, aabb_size)
        + struct.pack(
            "<HHHHI",
            int(portal.poly_id_from1) & 0xFFFF,
            int(portal.poly_id_from2) & 0xFFFF,
            int(portal.poly_id_to1) & 0xFFFF,
            int(portal.poly_id_to2) & 0xFFFF,
            int(portal.area_flags) & 0xFFFFFFFF,
        )
    )


def _pack_edge(edge: YnvEdge, area_lookup: dict[int, int]) -> bytes:
    edge = edge.build()
    return struct.pack("<II", edge.poly1.to_value(area_lookup), edge.poly2.to_value(area_lookup))


def _ensure_adjacent_area_ids(ynv: Ynv) -> list[int]:
    adjacent_area_ids = list(ynv.adjacent_area_ids)
    for required in (int(ynv.area_id) & 0xFFFFFFFF, 0x3FFF):
        if required not in adjacent_area_ids:
            adjacent_area_ids.append(required)
    for edge in ynv.edges:
        for part in (edge.poly1, edge.poly2):
            if int(part.area_id) not in adjacent_area_ids:
                adjacent_area_ids.append(int(part.area_id))
    for portal in ynv.portals:
        if int(portal.area_id_from) not in adjacent_area_ids:
            adjacent_area_ids.append(int(portal.area_id_from))
        if int(portal.area_id_to) not in adjacent_area_ids:
            adjacent_area_ids.append(int(portal.area_id_to))
    adjacent_area_ids = adjacent_area_ids[:32]
    if len(adjacent_area_ids) > 32:
        raise ValueError("YNV supports at most 32 adjacent area ids")
    return adjacent_area_ids


def _list_byte_count(item_count: int, item_size: int) -> int:
    if item_count <= 0:
        return 0x30
    items_per_part = max(1, _LIST_MAX_PART_BYTES // item_size)
    parts_count = (int(item_count) + items_per_part - 1) // items_per_part
    return 0x30 + (parts_count * _LIST_PART_SIZE) + (parts_count * 4) + (int(item_count) * item_size)


def _sector_metrics(sector: YnvSector | None) -> tuple[int, int]:
    if sector is None:
        return (0, 0)
    sector = sector.build()
    total_bytes = _SECTOR_SIZE
    total_points = 0
    if sector.data is not None:
        sector_data = sector.data.build()
        total_bytes += _SECTOR_DATA_SIZE + (len(sector_data.poly_ids) * 2) + (len(sector_data.points) * _POINT_SIZE)
        total_points += len(sector_data.points)
    for child in (sector.subtree1, sector.subtree2, sector.subtree3, sector.subtree4):
        child_bytes, child_points = _sector_metrics(child)
        total_bytes += child_bytes
        total_points += child_points
    return (total_bytes, total_points)


def _write_list(buffer: ByteWriter, *, items: list[bytes], info, item_size: int) -> tuple[int, int]:
    items_per_part = max(1, _LIST_MAX_PART_BYTES // item_size)
    part_offsets: list[int] = []
    part_counts: list[int] = []
    list_parts: list[tuple[int, int, int]] = []
    cumulative_offset = 0
    for start in range(0, len(items), items_per_part):
        chunk = items[start : start + items_per_part]
        part_offsets.append(cumulative_offset)
        part_counts.append(len(chunk))
        cumulative_offset += len(chunk)
        buffer.pad(16)
        items_offset = buffer.tell()
        for item in chunk:
            buffer.write(item)
        list_parts.append((items_offset, len(chunk), 0))
    buffer.pad(16)
    parts_offset = buffer.tell()
    for items_offset, count, unknown_0ch in list_parts:
        buffer.pack("QII", _virtual(items_offset), count, unknown_0ch)
    buffer.pad(16)
    offsets_offset = buffer.tell()
    for value in part_offsets:
        buffer.pack("I", value)
    buffer.pad(16)
    header_offset = buffer.tell()
    buffer.pack(
        "IIIIQQIIII",
        int(info.vft) & 0xFFFFFFFF,
        int(info.unknown_04h) & 0xFFFFFFFF,
        len(items),
        int(info.unknown_0ch) & 0xFFFFFFFF,
        _virtual(parts_offset) if list_parts else 0,
        _virtual(offsets_offset) if list_parts else 0,
        len(list_parts),
        int(info.unknown_24h) & 0xFFFFFFFF,
        int(info.unknown_28h) & 0xFFFFFFFF,
        int(info.unknown_2ch) & 0xFFFFFFFF,
    )
    return (header_offset, _list_byte_count(len(items), item_size))


def _write_sector_data(
    buffer: ByteWriter,
    sector_data: YnvSectorData,
    posoffset: tuple[float, float, float],
    aabb_size: tuple[float, float, float],
) -> int:
    sector_data = sector_data.build()
    poly_ids_offset = 0
    if sector_data.poly_ids:
        buffer.pad(16)
        poly_ids_offset = buffer.tell()
        for poly_id in sector_data.poly_ids:
            buffer.pack("H", poly_id)
    points_offset = 0
    if sector_data.points:
        buffer.pad(16)
        points_offset = buffer.tell()
        for point in sector_data.points:
            buffer.write(_pack_point(point, posoffset, aabb_size))
    buffer.pad(16)
    data_offset = buffer.tell()
    buffer.pack(
        "IIQQHHI",
        int(sector_data.points_start_id) & 0xFFFFFFFF,
        int(sector_data.unused_04h) & 0xFFFFFFFF,
        _virtual(poly_ids_offset) if poly_ids_offset else 0,
        _virtual(points_offset) if points_offset else 0,
        len(sector_data.poly_ids),
        len(sector_data.points),
        int(sector_data.unused_1ch) & 0xFFFFFFFF,
    )
    return data_offset


def _write_sector(
    buffer: ByteWriter,
    sector: YnvSector,
    posoffset: tuple[float, float, float],
    aabb_size: tuple[float, float, float],
) -> int:
    sector = sector.build()
    data_offset = _write_sector_data(buffer, sector.data, posoffset, aabb_size) if sector.data is not None else 0
    subtree1_offset = _write_sector(buffer, sector.subtree1, posoffset, aabb_size) if sector.subtree1 is not None else 0
    subtree2_offset = _write_sector(buffer, sector.subtree2, posoffset, aabb_size) if sector.subtree2 is not None else 0
    subtree3_offset = _write_sector(buffer, sector.subtree3, posoffset, aabb_size) if sector.subtree3 is not None else 0
    subtree4_offset = _write_sector(buffer, sector.subtree4, posoffset, aabb_size) if sector.subtree4 is not None else 0
    packed_cell_aabb = sector.cell_aabb.to_packed()
    buffer.pad(16)
    sector_offset = buffer.tell()
    buffer.pack(
        "4f4fhhhhhhQQQQQIII",
        float(sector.aabb_min[0]),
        float(sector.aabb_min[1]),
        float(sector.aabb_min[2]),
        float(sector.aabb_min_w),
        float(sector.aabb_max[0]),
        float(sector.aabb_max[1]),
        float(sector.aabb_max[2]),
        float(sector.aabb_max_w),
        packed_cell_aabb[0],
        packed_cell_aabb[1],
        packed_cell_aabb[2],
        packed_cell_aabb[3],
        packed_cell_aabb[4],
        packed_cell_aabb[5],
        _virtual(data_offset) if data_offset else 0,
        _virtual(subtree1_offset) if subtree1_offset else 0,
        _virtual(subtree2_offset) if subtree2_offset else 0,
        _virtual(subtree3_offset) if subtree3_offset else 0,
        _virtual(subtree4_offset) if subtree4_offset else 0,
        int(sector.unused_54h) & 0xFFFFFFFF,
        int(sector.unused_58h) & 0xFFFFFFFF,
        int(sector.unused_5ch) & 0xFFFFFFFF,
    )
    return sector_offset


def build_ynv_bytes(source: Ynv) -> bytes:
    ynv = source.build()
    if ynv.sector_tree is None:
        raise ValueError("YNV requires a sector tree")
    validation_errors = ynv.validate()
    if validation_errors:
        raise ValueError("Invalid YNV:\n- " + "\n- ".join(validation_errors))

    posoffset = tuple(float(component) for component in ynv.sector_tree.aabb_min)
    aabb_size = tuple(float(component) for component in ynv.aabb_size)
    adjacent_area_ids = _ensure_adjacent_area_ids(ynv)
    area_lookup = {int(area_id): index for index, area_id in enumerate(adjacent_area_ids)}

    buffer = ByteWriter()
    buffer.write(b"\x00" * _ROOT_SIZE)

    vertex_items = [_pack_vertex(vertex, posoffset, aabb_size) for vertex in ynv.vertices]
    vertices_offset, vertices_bytes = _write_list(buffer, items=vertex_items, info=ynv.vertices_info, item_size=_VERTEX_SIZE)

    index_items = [struct.pack("<H", index) for index in ynv.indices]
    indices_offset, indices_bytes = _write_list(buffer, items=index_items, info=ynv.indices_info, item_size=2)

    edge_items = [_pack_edge(edge, area_lookup) for edge in ynv.edges]
    edges_offset, edges_bytes = _write_list(buffer, items=edge_items, info=ynv.edges_info, item_size=_EDGE_SIZE)

    poly_items: list[bytes] = []
    for poly in ynv.polys:
        poly = poly.build()
        packed_aabb = poly.cell_aabb.to_packed()
        poly_items.append(
            struct.pack(
                "<HHHHIIIIhhhhhhIII",
                int(poly.poly_flags0) & 0xFFFF,
                int(poly.index_flags) & 0xFFFF,
                int(poly.index_id) & 0xFFFF,
                int(poly.area_id) & 0xFFFF,
                int(poly.unknown_08h) & 0xFFFFFFFF,
                int(poly.unknown_0ch) & 0xFFFFFFFF,
                int(poly.unknown_10h) & 0xFFFFFFFF,
                int(poly.unknown_14h) & 0xFFFFFFFF,
                packed_aabb[0],
                packed_aabb[1],
                packed_aabb[2],
                packed_aabb[3],
                packed_aabb[4],
                packed_aabb[5],
                int(poly.poly_flags1) & 0xFFFFFFFF,
                int(poly.poly_flags2) & 0xFFFFFFFF,
                int(poly.part_flags) & 0xFFFFFFFF,
            )
        )
    polys_offset, polys_bytes = _write_list(buffer, items=poly_items, info=ynv.polys_info, item_size=_POLY_SIZE)

    portals_offset = 0
    if ynv.portals:
        buffer.pad(16)
        portals_offset = buffer.tell()
        for portal in ynv.portals:
            buffer.write(_pack_portal(portal.build(), posoffset, aabb_size))

    portal_links_offset = 0
    if ynv.portal_links:
        buffer.pad(16)
        portal_links_offset = buffer.tell()
        for portal_link in ynv.portal_links:
            buffer.pack("H", int(portal_link) & 0xFFFF)

    sector_tree_offset = _write_sector(buffer, ynv.sector_tree, posoffset, aabb_size)

    sector_bytes, points_count = _sector_metrics(ynv.sector_tree)
    total_bytes = vertices_bytes + indices_bytes + edges_bytes + polys_bytes + sector_bytes + (len(ynv.portals) * _PORTAL_SIZE) + (len(ynv.portal_links) * 2)

    system_data = bytearray(buffer.getvalue())
    adjacent_area_ids_raw = adjacent_area_ids + ([0] * (32 - len(adjacent_area_ids)))
    struct.pack_into("<I", system_data, 0x10, int(ynv.content_flags) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x14, int(ynv.version_unk1) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x18, int(ynv.unused_018h) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x1C, int(ynv.unused_01ch) & 0xFFFFFFFF)
    struct.pack_into("<16f", system_data, 0x20, *[float(value) for value in ynv.transform])
    struct.pack_into("<3f", system_data, 0x60, float(aabb_size[0]), float(aabb_size[1]), float(aabb_size[2]))
    struct.pack_into("<I", system_data, 0x6C, int(ynv.aabb_unk) & 0xFFFFFFFF)
    struct.pack_into("<Q", system_data, 0x70, _virtual(vertices_offset))
    struct.pack_into("<I", system_data, 0x78, 0)
    struct.pack_into("<I", system_data, 0x7C, 0)
    struct.pack_into("<Q", system_data, 0x80, _virtual(indices_offset))
    struct.pack_into("<Q", system_data, 0x88, _virtual(edges_offset))
    struct.pack_into("<I", system_data, 0x90, len(ynv.indices))
    struct.pack_into("<I", system_data, 0x94, len(adjacent_area_ids))
    for index, area_id in enumerate(adjacent_area_ids_raw):
        struct.pack_into("<I", system_data, 0x98 + (index * 4), int(area_id) & 0xFFFFFFFF)
    struct.pack_into("<Q", system_data, 0x118, _virtual(polys_offset))
    struct.pack_into("<Q", system_data, 0x120, _virtual(sector_tree_offset))
    struct.pack_into("<Q", system_data, 0x128, _virtual(portals_offset) if portals_offset else 0)
    struct.pack_into("<Q", system_data, 0x130, _virtual(portal_links_offset) if portal_links_offset else 0)
    struct.pack_into("<I", system_data, 0x138, len(ynv.vertices))
    struct.pack_into("<I", system_data, 0x13C, len(ynv.polys))
    struct.pack_into("<I", system_data, 0x140, int(ynv.area_id) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x144, int(total_bytes) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x148, int(points_count) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x14C, len(ynv.portals))
    struct.pack_into("<I", system_data, 0x150, len(ynv.portal_links))
    struct.pack_into("<I", system_data, 0x154, int(ynv.unused_154h) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x158, int(ynv.unused_158h) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x15C, int(ynv.unused_15ch) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x160, int(ynv.version_unk2) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x164, int(ynv.unused_164h) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x168, int(ynv.unused_168h) & 0xFFFFFFFF)
    struct.pack_into("<I", system_data, 0x16C, int(ynv.unused_16ch) & 0xFFFFFFFF)

    resource = build_rsc7(bytes(system_data), version=int(ynv.version))
    header_system_flags = int.from_bytes(resource[8:12], "little")
    header_graphics_flags = int.from_bytes(resource[12:16], "little")
    ynv.system_pages_count = get_resource_total_page_count(header_system_flags)
    ynv.graphics_pages_count = get_resource_total_page_count(header_graphics_flags)
    ynv.total_bytes = int(total_bytes) & 0xFFFFFFFF
    ynv.points_count = int(points_count) & 0xFFFFFFFF
    return resource


def save_ynv(source: Ynv, destination: str | Path) -> Path:
    target = Path(destination)
    target.write_bytes(build_ynv_bytes(source))
    return target


__all__ = ["build_ynv_bytes", "save_ynv"]
