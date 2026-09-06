import struct

_DAT_VIRTUAL_BASE = 0x50000000


def _parse_meta_layout(data: bytes) -> dict[str, object]:
    from fivefury.resource import split_rsc7_sections

    header, system_data, _ = split_rsc7_sections(data)
    root = struct.unpack_from("<ihbbiiqqqqqhhhh8I", system_data, 16)
    pages_info = struct.unpack_from("<IIBBHI", system_data, 112)
    data_block_pointer = int(root[8])
    data_block_count = int(root[13])
    data_block_offset = (
        data_block_pointer - _DAT_VIRTUAL_BASE if data_block_pointer else 0
    )
    data_blocks: list[tuple[int, int, int]] = []
    for index in range(data_block_count):
        name_hash, length, pointer = struct.unpack_from(
            "<IIq", system_data, data_block_offset + index * 16
        )
        data_blocks.append((name_hash, length, pointer))
    return {
        "header": header,
        "pages_info": pages_info,
        "struct_ptr": int(root[6]),
        "enum_ptr": int(root[7]),
        "data_block_ptr": data_block_pointer,
        "data_block_count": data_block_count,
        "data_blocks": data_blocks,
    }
