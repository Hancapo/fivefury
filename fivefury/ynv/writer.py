from __future__ import annotations

import dataclasses
import struct
from pathlib import Path

from ..resource import (
    ResourceBlockSpan,
    ResourceWriter,
    build_rsc7,
    get_resource_total_page_count,
    layout_resource_sections,
    write_resource_pages_info,
)
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


def _pack_vertex(
    position: tuple[float, float, float],
    posoffset: tuple[float, float, float],
    aabb_size: tuple[float, float, float],
) -> bytes:
    values: list[int] = []
    for component, base, size in zip(position, posoffset, aabb_size, strict=True):
        if abs(size) < 1e-8:
            normalized = 0.0
        else:
            normalized = (float(component) - float(base)) / float(size)
        normalized = max(0.0, min(1.0, normalized))
        values.append(int(round(normalized * 65535.0)) & 0xFFFF)
    return struct.pack("<HHH", values[0], values[1], values[2])


def _pack_point(
    point: YnvPoint,
    posoffset: tuple[float, float, float],
    aabb_size: tuple[float, float, float],
) -> bytes:
    return _pack_vertex(point.position, posoffset, aabb_size) + bytes(
        (int(point.angle) & 0xFF, int(point.type) & 0xFF)
    )


def _pack_portal(
    portal: YnvPortal,
    posoffset: tuple[float, float, float],
    aabb_size: tuple[float, float, float],
) -> bytes:
    return (
        struct.pack(
            "<BBH",
            int(portal.type) & 0xFF,
            int(portal.angle) & 0xFF,
            int(portal.flags_unk) & 0xFFFF,
        )
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
    return struct.pack(
        "<II", edge.poly1.to_value(area_lookup), edge.poly2.to_value(area_lookup)
    )


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
    if len(adjacent_area_ids) > 32:
        raise ValueError("YNV supports at most 32 adjacent area ids")
    return adjacent_area_ids


def _list_byte_count(item_count: int, item_size: int) -> int:
    if item_count <= 0:
        return 0x30
    items_per_part = max(1, _LIST_MAX_PART_BYTES // item_size)
    parts_count = (int(item_count) + items_per_part - 1) // items_per_part
    return (
        0x30
        + (parts_count * _LIST_PART_SIZE)
        + (parts_count * 4)
        + (int(item_count) * item_size)
    )


def _sector_metrics(sector: YnvSector | None) -> tuple[int, int]:
    if sector is None:
        return (0, 0)
    sector = sector.build()
    total_bytes = _SECTOR_SIZE
    total_points = 0
    if sector.data is not None:
        sector_data = sector.data.build()
        total_bytes += (
            _SECTOR_DATA_SIZE
            + (len(sector_data.poly_ids) * 2)
            + (len(sector_data.points) * _POINT_SIZE)
        )
        total_points += len(sector_data.points)
    for child in (sector.subtree1, sector.subtree2, sector.subtree3, sector.subtree4):
        child_bytes, child_points = _sector_metrics(child)
        total_bytes += child_bytes
        total_points += child_points
    return (total_bytes, total_points)


def _write_list(
    writer: ResourceWriter, *, items: list[bytes], info, item_size: int
) -> tuple[int, int]:
    items_per_part = max(1, _LIST_MAX_PART_BYTES // item_size)
    part_offsets: list[int] = []
    list_parts: list[tuple[int, int, int]] = []
    cumulative_offset = 0
    for start in range(0, len(items), items_per_part):
        chunk = items[start : start + items_per_part]
        part_offsets.append(cumulative_offset)
        cumulative_offset += len(chunk)
        items_offset = writer.alloc(len(chunk) * item_size, 16, relocate_pointers=False)
        writer.write(items_offset, b"".join(chunk))
        list_parts.append((items_offset, len(chunk), 0))
    parts_offset = (
        writer.alloc(len(list_parts) * _LIST_PART_SIZE, 16) if list_parts else 0
    )
    for index, (items_offset, count, unknown_0ch) in enumerate(list_parts):
        writer.pack_into(
            "QII",
            parts_offset + (index * _LIST_PART_SIZE),
            _virtual(items_offset),
            count,
            unknown_0ch,
        )
    offsets_offset = (
        writer.alloc(len(part_offsets) * 4, 16, relocate_pointers=False)
        if part_offsets
        else 0
    )
    for index, value in enumerate(part_offsets):
        writer.pack_into("I", offsets_offset + (index * 4), value)
    header_offset = writer.alloc(0x30, 16)
    writer.pack_into(
        "IIIIQQIIII",
        header_offset,
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
    writer: ResourceWriter,
    sector_data: YnvSectorData,
    posoffset: tuple[float, float, float],
    aabb_size: tuple[float, float, float],
) -> int:
    sector_data = sector_data.build()
    poly_ids_offset = 0
    if sector_data.poly_ids:
        poly_ids_offset = writer.alloc(
            len(sector_data.poly_ids) * 2, 16, relocate_pointers=False
        )
        for index, poly_id in enumerate(sector_data.poly_ids):
            writer.pack_into("H", poly_ids_offset + (index * 2), poly_id)
    points_offset = 0
    if sector_data.points:
        points_offset = writer.alloc(
            len(sector_data.points) * _POINT_SIZE, 16, relocate_pointers=False
        )
        for index, point in enumerate(sector_data.points):
            writer.write(
                points_offset + (index * _POINT_SIZE),
                _pack_point(point, posoffset, aabb_size),
            )
    data_offset = writer.alloc(_SECTOR_DATA_SIZE, 16)
    writer.pack_into(
        "IIQQHHI",
        data_offset,
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
    writer: ResourceWriter,
    sector: YnvSector,
    posoffset: tuple[float, float, float],
    aabb_size: tuple[float, float, float],
) -> int:
    sector = sector.build()
    data_offset = (
        _write_sector_data(writer, sector.data, posoffset, aabb_size)
        if sector.data is not None
        else 0
    )
    subtree1_offset = (
        _write_sector(writer, sector.subtree1, posoffset, aabb_size)
        if sector.subtree1 is not None
        else 0
    )
    subtree2_offset = (
        _write_sector(writer, sector.subtree2, posoffset, aabb_size)
        if sector.subtree2 is not None
        else 0
    )
    subtree3_offset = (
        _write_sector(writer, sector.subtree3, posoffset, aabb_size)
        if sector.subtree3 is not None
        else 0
    )
    subtree4_offset = (
        _write_sector(writer, sector.subtree4, posoffset, aabb_size)
        if sector.subtree4 is not None
        else 0
    )
    packed_cell_aabb = sector.cell_aabb.to_packed()
    sector_offset = writer.alloc(_SECTOR_SIZE, 16)
    writer.pack_into(
        "4f4fhhhhhhQQQQQIII",
        sector_offset,
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


def build_ynv_system_layout(
    ynv: Ynv, *, page_count: int
) -> tuple[bytes, list[ResourceBlockSpan]]:
    assert ynv.sector_tree is not None
    posoffset = tuple(float(component) for component in ynv.sector_tree.aabb_min)
    aabb_size = tuple(float(component) for component in ynv.aabb_size)
    adjacent_area_ids = _ensure_adjacent_area_ids(ynv)
    area_lookup = {
        int(area_id): index for index, area_id in enumerate(adjacent_area_ids)
    }

    writer = ResourceWriter(initial_size=_ROOT_SIZE)

    vertex_items = [
        _pack_vertex(vertex, posoffset, aabb_size) for vertex in ynv.vertices
    ]
    vertices_offset, vertices_bytes = _write_list(
        writer,
        items=vertex_items,
        info=ynv.vertices_info,
        item_size=_VERTEX_SIZE,
    )

    index_items = [struct.pack("<H", index) for index in ynv.indices]
    indices_offset, indices_bytes = _write_list(
        writer, items=index_items, info=ynv.indices_info, item_size=2
    )

    edge_items = [_pack_edge(edge, area_lookup) for edge in ynv.edges]
    edges_offset, edges_bytes = _write_list(
        writer, items=edge_items, info=ynv.edges_info, item_size=_EDGE_SIZE
    )

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
    polys_offset, polys_bytes = _write_list(
        writer, items=poly_items, info=ynv.polys_info, item_size=_POLY_SIZE
    )

    portals_offset = 0
    if ynv.portals:
        portals_offset = writer.alloc(
            len(ynv.portals) * _PORTAL_SIZE, 16, relocate_pointers=False
        )
        for index, portal in enumerate(ynv.portals):
            writer.write(
                portals_offset + (index * _PORTAL_SIZE),
                _pack_portal(portal.build(), posoffset, aabb_size),
            )

    portal_links_offset = 0
    if ynv.portal_links:
        portal_links_offset = writer.alloc(
            len(ynv.portal_links) * 2, 16, relocate_pointers=False
        )
        for index, portal_link in enumerate(ynv.portal_links):
            writer.pack_into(
                "H", portal_links_offset + (index * 2), int(portal_link) & 0xFFFF
            )

    sector_tree_offset = _write_sector(writer, ynv.sector_tree, posoffset, aabb_size)

    sector_bytes, points_count = _sector_metrics(ynv.sector_tree)
    total_bytes = (
        vertices_bytes
        + indices_bytes
        + edges_bytes
        + polys_bytes
        + sector_bytes
        + (len(ynv.portals) * _PORTAL_SIZE)
        + (len(ynv.portal_links) * 2)
    )
    pages_info = dataclasses.replace(
        ynv.pages_info,
        system_pages_count=int(page_count),
        graphics_pages_count=0,
    )
    pages_info_offset = write_resource_pages_info(writer, pages_info)
    adjacent_area_ids_raw = adjacent_area_ids + ([0] * (32 - len(adjacent_area_ids)))
    writer.pack_into(
        "IIQ",
        0x00,
        int(ynv.file_vft),
        int(ynv.file_unknown),
        _virtual(pages_info_offset),
    )
    writer.pack_into("I", 0x10, int(ynv.content_flags) & 0xFFFFFFFF)
    writer.pack_into("I", 0x14, int(ynv.version_unk1) & 0xFFFFFFFF)
    writer.pack_into("I", 0x18, int(ynv.unused_018h) & 0xFFFFFFFF)
    writer.pack_into("I", 0x1C, int(ynv.unused_01ch) & 0xFFFFFFFF)
    writer.pack_into("16f", 0x20, *[float(value) for value in ynv.transform])
    writer.pack_into(
        "3f", 0x60, float(aabb_size[0]), float(aabb_size[1]), float(aabb_size[2])
    )
    writer.pack_into("I", 0x6C, int(ynv.aabb_unk) & 0xFFFFFFFF)
    writer.pack_into("Q", 0x70, _virtual(vertices_offset))
    writer.pack_into("I", 0x78, 0)
    writer.pack_into("I", 0x7C, 0)
    writer.pack_into("Q", 0x80, _virtual(indices_offset))
    writer.pack_into("Q", 0x88, _virtual(edges_offset))
    writer.pack_into("I", 0x90, len(ynv.indices))
    writer.pack_into("I", 0x94, len(adjacent_area_ids))
    for index, area_id in enumerate(adjacent_area_ids_raw):
        writer.pack_into("I", 0x98 + (index * 4), int(area_id) & 0xFFFFFFFF)
    writer.pack_into("Q", 0x118, _virtual(polys_offset))
    writer.pack_into("Q", 0x120, _virtual(sector_tree_offset))
    writer.pack_into("Q", 0x128, _virtual(portals_offset) if portals_offset else 0)
    writer.pack_into(
        "Q", 0x130, _virtual(portal_links_offset) if portal_links_offset else 0
    )
    writer.pack_into("I", 0x138, len(ynv.vertices))
    writer.pack_into("I", 0x13C, len(ynv.polys))
    writer.pack_into("I", 0x140, int(ynv.area_id) & 0xFFFFFFFF)
    writer.pack_into("I", 0x144, int(total_bytes) & 0xFFFFFFFF)
    writer.pack_into("I", 0x148, int(points_count) & 0xFFFFFFFF)
    writer.pack_into("I", 0x14C, len(ynv.portals))
    writer.pack_into("I", 0x150, len(ynv.portal_links))
    writer.pack_into("I", 0x154, int(ynv.unused_154h) & 0xFFFFFFFF)
    writer.pack_into("I", 0x158, int(ynv.unused_158h) & 0xFFFFFFFF)
    writer.pack_into("I", 0x15C, int(ynv.unused_15ch) & 0xFFFFFFFF)
    writer.pack_into("I", 0x160, int(ynv.version_unk2) & 0xFFFFFFFF)
    writer.pack_into("I", 0x164, int(ynv.unused_164h) & 0xFFFFFFFF)
    writer.pack_into("I", 0x168, int(ynv.unused_168h) & 0xFFFFFFFF)
    writer.pack_into("I", 0x16C, int(ynv.unused_16ch) & 0xFFFFFFFF)

    ynv.total_bytes = int(total_bytes) & 0xFFFFFFFF
    ynv.points_count = int(points_count) & 0xFFFFFFFF
    return writer.finish(), writer.block_spans


def build_ynv_bytes(source: Ynv) -> bytes:
    storage_errors = source._validate_storage_limits()
    if storage_errors:
        raise ValueError("Invalid YNV:\n- " + "\n- ".join(storage_errors))
    ynv = source.build()
    if ynv.sector_tree is None:
        raise ValueError("YNV requires a sector tree")
    ynv.pages_info.system_pages_count = int(ynv.system_pages_count)
    ynv.pages_info.graphics_pages_count = int(ynv.graphics_pages_count)
    validation_errors = ynv.validate()
    if validation_errors:
        raise ValueError("Invalid YNV:\n- " + "\n- ".join(validation_errors))

    page_count = 1
    system_data = b""
    system_flags = None
    graphics_flags = None
    for _ in range(16):
        raw_system_data, block_spans = build_ynv_system_layout(
            ynv, page_count=page_count
        )
        system_data, _, system_flags, graphics_flags = layout_resource_sections(
            raw_system_data,
            block_spans,
            version=int(ynv.version),
        )
        next_page_count = get_resource_total_page_count(system_flags)
        if next_page_count == page_count:
            break
        page_count = next_page_count
    else:
        raise RuntimeError("YNV page-info sizing did not converge")

    assert system_flags is not None
    assert graphics_flags is not None
    ynv.system_pages_count = get_resource_total_page_count(system_flags)
    ynv.graphics_pages_count = get_resource_total_page_count(graphics_flags)
    ynv.pages_info.system_pages_count = ynv.system_pages_count
    ynv.pages_info.graphics_pages_count = ynv.graphics_pages_count
    return build_rsc7(
        system_data,
        version=int(ynv.version),
        system_flags=system_flags,
        graphics_flags=graphics_flags,
    )


def save_ynv(source: Ynv, destination: str | Path) -> Path:
    target = Path(destination)
    target.write_bytes(build_ynv_bytes(source))
    return target


__all__ = ["build_ynv_bytes", "build_ynv_system_layout", "save_ynv"]
