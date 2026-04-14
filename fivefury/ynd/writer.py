from __future__ import annotations

import dataclasses
from pathlib import Path

from ..binary import pack_struct
from ..resource import (
    ResourceBlockSpan,
    ResourceWriter,
    build_rsc7,
    get_resource_total_page_count,
    layout_resource_sections,
    write_resource_pages_info,
)
from .model import Ynd, YndResourcePagesInfo

_ROOT_SIZE = 0x70
_NODE_SIZE = 0x28
_LINK_SIZE = 0x08
_JUNCTION_SIZE = 0x0C
_JUNCTION_REF_SIZE = 0x08
_SYSTEM_BASE = 0x50000000


def _virtual(offset: int) -> int:
    return _SYSTEM_BASE + int(offset)


def build_ynd_system_layout(source: Ynd, *, page_count: int = 1) -> tuple[bytes, list[ResourceBlockSpan]]:
    ynd = dataclasses.replace(source, nodes=[dataclasses.replace(node) for node in source.nodes]).build()
    issues = ynd.validate()
    if issues:
        issue_lines = "\n".join(f"- {issue}" for issue in issues)
        raise ValueError(f"cannot build invalid YND:\n{issue_lines}")

    writer = ResourceWriter(initial_size=_ROOT_SIZE)

    all_links = []
    for node in ynd.nodes:
        all_links.extend(node.links)

    nodes_offset = writer.alloc(len(ynd.nodes) * _NODE_SIZE, 16, relocate_pointers=False) if ynd.nodes else 0
    links_offset = writer.alloc(len(all_links) * _LINK_SIZE, 16, relocate_pointers=False) if all_links else 0

    junction_records: list[tuple[int, object]] = []
    for node_index, node in enumerate(ynd.nodes):
        if node.junction is not None:
            junction_records.append((node_index, node.junction))

    junctions_offset = (
        writer.alloc(len(junction_records) * _JUNCTION_SIZE, 16, relocate_pointers=False) if junction_records else 0
    )
    junction_refs_offset = (
        writer.alloc(len(junction_records) * _JUNCTION_REF_SIZE, 16, relocate_pointers=False) if junction_records else 0
    )
    heightmap_bytes = b"".join(junction.heightmap for _, junction in junction_records)
    junction_heightmap_offset = (
        writer.alloc(len(heightmap_bytes), 16, relocate_pointers=False) if heightmap_bytes else 0
    )

    pages_info = dataclasses.replace(
        ynd.pages_info,
        system_pages_count=int(page_count),
        graphics_pages_count=0,
    )
    pages_info_offset = write_resource_pages_info(writer, pages_info)

    writer.pack_into("IIQ", 0x00, int(ynd.file_vft), int(ynd.file_unknown), _virtual(pages_info_offset))
    writer.pack_into(
        "QIIIIQIIQQIIQHHIIIII",
        0x10,
        _virtual(nodes_offset) if nodes_offset else 0,
        len(ynd.nodes),
        ynd.vehicle_node_count,
        ynd.ped_node_count,
        int(ynd.unknown_24h),
        _virtual(links_offset) if links_offset else 0,
        len(all_links),
        int(ynd.unknown_34h),
        _virtual(junctions_offset) if junctions_offset else 0,
        _virtual(junction_heightmap_offset) if junction_heightmap_offset else 0,
        int(ynd.unknown_48h),
        int(ynd.unknown_4ch),
        _virtual(junction_refs_offset) if junction_refs_offset else 0,
        len(junction_records),
        len(junction_records),
        int(ynd.unknown_5ch),
        len(junction_records),
        len(heightmap_bytes),
        int(ynd.unknown_68h),
        int(ynd.unknown_6ch),
    )

    if links_offset:
        for index, link in enumerate(all_links):
            writer.pack_into(
                "HHBBBB",
                links_offset + (index * _LINK_SIZE),
                int(link.area_id),
                int(link.node_id),
                link.flags0,
                link.flags1,
                link.flags2,
                link.link_length,
            )

    current_link_index = 0
    for index, node in enumerate(ynd.nodes):
        offset = nodes_offset + (index * _NODE_SIZE) if nodes_offset else 0
        link_id = current_link_index if node.links else 0
        current_link_index += len(node.links)
        position_x = int(round(node.position[0] * 4.0))
        position_y = int(round(node.position[1] * 4.0))
        position_z = int(round(node.position[2] * 32.0))
        writer.write(
            offset,
            pack_struct(
                "IIIIHHIHHhhBBhBBBB",
                int(node.unused0),
                int(node.unused1),
                int(node.unused2),
                int(node.unused3),
                int(node.area_id),
                int(node.node_id),
                int(node.street_name_hash),
                int(node.unused4),
                int(link_id),
                position_x,
                position_y,
                node.flags0,
                node.flags1,
                position_z,
                node.flags2,
                node.link_count_flags,
                node.flags3,
                node.flags4,
            ),
        )

    if junctions_offset:
        heightmap_cursor = 0
        for junction_index, (node_index, junction) in enumerate(junction_records):
            junction_offset = junctions_offset + (junction_index * _JUNCTION_SIZE)
            writer.pack_into(
                "hhhhHBB",
                junction_offset,
                int(round(junction.max_z * 32.0)),
                int(round(junction.position[0] * 4.0)),
                int(round(junction.position[1] * 4.0)),
                int(round(junction.min_z * 32.0)),
                int(heightmap_cursor),
                int(junction.heightmap_dim_x),
                int(junction.heightmap_dim_y),
            )
            ref_offset = junction_refs_offset + (junction_index * _JUNCTION_REF_SIZE)
            owner_node = ynd.nodes[node_index]
            writer.pack_into(
                "HHHH",
                ref_offset,
                int(owner_node.area_id),
                int(owner_node.node_id),
                int(junction_index),
                int(junction.junction_ref_unk0),
            )
            heightmap_cursor += len(junction.heightmap)
        if heightmap_bytes:
            writer.write(junction_heightmap_offset, heightmap_bytes)

    return writer.finish(), writer.block_spans


def build_ynd_bytes(source: Ynd) -> bytes:
    ynd = source.build()
    page_count = 1
    system_flags = None
    graphics_flags = None
    system_data = b""
    for _ in range(16):
        raw_system_data, block_spans = build_ynd_system_layout(ynd, page_count=page_count)
        system_data, _, system_flags, graphics_flags = layout_resource_sections(
            raw_system_data,
            block_spans,
            version=ynd.version,
        )
        next_page_count = get_resource_total_page_count(system_flags)
        if next_page_count == page_count:
            break
        page_count = next_page_count
    assert system_flags is not None
    assert graphics_flags is not None
    ynd.system_pages_count = get_resource_total_page_count(system_flags)
    ynd.graphics_pages_count = get_resource_total_page_count(graphics_flags)
    ynd.pages_info.system_pages_count = ynd.system_pages_count
    ynd.pages_info.graphics_pages_count = ynd.graphics_pages_count
    return build_rsc7(system_data, version=ynd.version, system_flags=system_flags, graphics_flags=graphics_flags)


def save_ynd(source: Ynd, destination: str | Path) -> Path:
    target = Path(destination)
    target.write_bytes(build_ynd_bytes(source))
    source.path = str(target)
    return target
