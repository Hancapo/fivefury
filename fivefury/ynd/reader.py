from __future__ import annotations

from pathlib import Path

from ..binary import i16, u16, u32, u64
from ..resource import (
    RSC7_MAGIC,
    checked_virtual_offset,
    get_resource_total_page_count,
    read_resource_pages_info,
    split_rsc7_sections,
)
from .model import Ynd, YndJunction, YndLink, YndNode, YndResourcePagesInfo

_ROOT_SIZE = 0x70
_NODE_SIZE = 0x28
_LINK_SIZE = 0x08
_JUNCTION_SIZE = 0x0C
_JUNCTION_REF_SIZE = 0x08


def read_ynd(source: bytes | bytearray | memoryview | str | Path, *, path: str | Path = "") -> Ynd:
    data = Path(source).read_bytes() if isinstance(source, (str, Path)) else bytes(source)
    if len(data) < 0x10:
        raise ValueError("YND data is too short")
    if int.from_bytes(data[:4], "little") != RSC7_MAGIC:
        raise ValueError("YND data must be a standalone RSC7 resource")

    header, system_data, _ = split_rsc7_sections(data)
    if len(system_data) < _ROOT_SIZE:
        raise ValueError("YND system section is too short")

    pages_info_pointer = u64(system_data, 0x08)
    nodes_pointer = u64(system_data, 0x10)
    nodes_count = u32(system_data, 0x18)
    nodes_count_vehicle = u32(system_data, 0x1C)
    nodes_count_ped = u32(system_data, 0x20)
    links_pointer = u64(system_data, 0x28)
    links_count = u32(system_data, 0x30)
    junctions_pointer = u64(system_data, 0x38)
    junction_heightmap_pointer = u64(system_data, 0x40)
    junction_refs_pointer = u64(system_data, 0x50)
    junction_refs_count = u16(system_data, 0x58)
    junctions_count = u32(system_data, 0x60)
    junction_heightmap_bytes_count = u32(system_data, 0x64)

    nodes_offset = checked_virtual_offset(nodes_pointer, system_data) if nodes_pointer and nodes_count else 0
    links_offset = checked_virtual_offset(links_pointer, system_data) if links_pointer and links_count else 0
    junctions_offset = checked_virtual_offset(junctions_pointer, system_data) if junctions_pointer and junctions_count else 0
    junction_refs_offset = (
        checked_virtual_offset(junction_refs_pointer, system_data) if junction_refs_pointer and junction_refs_count else 0
    )
    junction_heightmap_offset = (
        checked_virtual_offset(junction_heightmap_pointer, system_data)
        if junction_heightmap_pointer and junction_heightmap_bytes_count
        else 0
    )

    links: list[YndLink] = []
    for index in range(int(links_count)):
        offset = links_offset + (index * _LINK_SIZE)
        links.append(
            YndLink.from_packed(
                area_id=u16(system_data, offset + 0x00),
                node_id=u16(system_data, offset + 0x02),
                flags0=system_data[offset + 0x04],
                flags1=system_data[offset + 0x05],
                flags2=system_data[offset + 0x06],
                link_length=system_data[offset + 0x07],
            )
        )

    raw_junctions: list[tuple[YndJunction, int, int, int]] = []
    for index in range(int(junctions_count)):
        offset = junctions_offset + (index * _JUNCTION_SIZE)
        max_z = i16(system_data, offset + 0x00) / 32.0
        position_x = i16(system_data, offset + 0x02) / 4.0
        position_y = i16(system_data, offset + 0x04) / 4.0
        min_z = i16(system_data, offset + 0x06) / 32.0
        heightmap_ptr = u16(system_data, offset + 0x08)
        dim_x = system_data[offset + 0x0A]
        dim_y = system_data[offset + 0x0B]
        hm_count = int(dim_x) * int(dim_y)
        hm_start = junction_heightmap_offset + int(heightmap_ptr)
        heightmap = system_data[hm_start : hm_start + hm_count] if hm_count else b""
        raw_junctions.append(
            (
                YndJunction(
                    position=(position_x, position_y),
                    min_z=min_z,
                    max_z=max_z,
                    heightmap_dim_x=dim_x,
                    heightmap_dim_y=dim_y,
                    heightmap=heightmap,
                ),
                0,
                0,
                0,
            )
        )

    junction_refs: list[tuple[int, int, int, int]] = []
    for index in range(int(junction_refs_count)):
        offset = junction_refs_offset + (index * _JUNCTION_REF_SIZE)
        junction_refs.append(
            (
                u16(system_data, offset + 0x00),
                u16(system_data, offset + 0x02),
                u16(system_data, offset + 0x04),
                u16(system_data, offset + 0x06),
            )
        )

    junctions_by_node: dict[tuple[int, int], YndJunction] = {}
    for area_id, node_id, junction_id, unk0 in junction_refs:
        if junction_id >= len(raw_junctions):
            continue
        junction = raw_junctions[junction_id][0]
        junction.junction_ref_unk0 = int(unk0)
        junctions_by_node[(int(area_id), int(node_id))] = junction

    nodes: list[YndNode] = []
    for index in range(int(nodes_count)):
        offset = nodes_offset + (index * _NODE_SIZE)
        area_id = u16(system_data, offset + 0x10)
        node_id = u16(system_data, offset + 0x12)
        link_id = u16(system_data, offset + 0x1A)
        link_count_flags = system_data[offset + 0x25]
        link_count = int(link_count_flags) >> 3
        node_links = [links[link_id + link_index] for link_index in range(link_count)] if link_count else []
        node = YndNode.from_packed(
            unused0=u32(system_data, offset + 0x00),
            unused1=u32(system_data, offset + 0x04),
            unused2=u32(system_data, offset + 0x08),
            unused3=u32(system_data, offset + 0x0C),
            area_id=area_id,
            node_id=node_id,
            street_name_hash=u32(system_data, offset + 0x14),
            unused4=u16(system_data, offset + 0x18),
            position=(
                i16(system_data, offset + 0x1C) / 4.0,
                i16(system_data, offset + 0x1E) / 4.0,
                i16(system_data, offset + 0x22) / 32.0,
            ),
            flags0=system_data[offset + 0x20],
            flags1=system_data[offset + 0x21],
            flags2=system_data[offset + 0x24],
            link_count_flags=link_count_flags,
            flags3=system_data[offset + 0x26],
            flags4=system_data[offset + 0x27],
            links=node_links,
            junction=junctions_by_node.get((int(area_id), int(node_id))),
        )
        nodes.append(node)

    ynd = Ynd(
        version=int(header.version),
        path=str(path or source) if isinstance(source, (str, Path)) or path else "",
        area_id=(int(nodes[0].area_id) if nodes and all(node.area_id == nodes[0].area_id for node in nodes) else None),
        nodes=nodes,
        file_vft=u32(system_data, 0x00),
        file_unknown=u32(system_data, 0x04),
        pages_info=read_resource_pages_info(pages_info_pointer, system_data) or YndResourcePagesInfo(),
        unknown_24h=u32(system_data, 0x24),
        unknown_34h=u32(system_data, 0x34),
        unknown_48h=u32(system_data, 0x48),
        unknown_4ch=u32(system_data, 0x4C),
        unknown_5ch=u32(system_data, 0x5C),
        unknown_68h=u32(system_data, 0x68),
        unknown_6ch=u32(system_data, 0x6C),
        system_pages_count=get_resource_total_page_count(header.system_flags),
        graphics_pages_count=get_resource_total_page_count(header.graphics_flags),
    )
    if ynd.vehicle_node_count != int(nodes_count_vehicle) or ynd.ped_node_count != int(nodes_count_ped):
        ynd.build()
    return ynd
