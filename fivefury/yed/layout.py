from __future__ import annotations

import struct

from ..authoring.diagnostics import ValidationReport
from ..resource import (
    ResourceBlockSpan,
    checked_virtual_offset,
    get_resource_total_page_count,
    read_resource_pages_info,
    validate_resource_block_layout,
)
from .constants import EXPRESSION_BLOCK_SIZE, SPRING_BLOCK_SIZE
from .model import ResourceListInfo, Yed


def validate_yed_resource_layout(source: Yed) -> ValidationReport:
    """Inspect the serialized layout of an unchanged, decoded YED."""
    report = ValidationReport()
    blocks = {"dictionary": ResourceBlockSpan(0, 0x40)}
    data = source.system_data

    def block(pointer: int, size: int, path: str, alignment: int = 1) -> int | None:
        if not pointer and not size:
            return None
        try:
            offset = checked_virtual_offset(pointer, data)
            if offset + size > len(data):
                raise ValueError("Owned block is truncated")
        except ValueError as exc:
            report.issue("yed.resource.pointer", str(exc), path=path)
            return None
        if offset % alignment:
            report.issue(
                "yed.resource.alignment",
                f"Owned block requires {alignment}-byte alignment",
                path=path,
            )
        blocks[path] = ResourceBlockSpan(offset, size)
        return offset

    def array(info: ResourceListInfo, stride: int, count: int, path: str) -> None:
        if info.count != count or info.capacity < info.count:
            report.issue(
                "yed.resource.count",
                "Serialized list count/capacity does not match its decoded entries",
                path=path,
            )
        block(info.pointer, info.capacity * stride, path, min(stride, 16))

    dictionary = source.dictionary
    array(
        dictionary.expression_name_hashes,
        4,
        len(source.expressions),
        "dictionary.expression_name_hashes",
    )
    array(
        dictionary.expressions_info,
        8,
        len(source.expressions),
        "dictionary.expressions",
    )
    pages_path = "dictionary.pages_info"
    if block(dictionary.pages_info_pointer, 0x10, pages_path) is not None:
        pages = read_resource_pages_info(dictionary.pages_info_pointer, data)
        assert pages is not None
        if pages.system_pages_count < get_resource_total_page_count(
            source.system_flags
        ) or pages.graphics_pages_count < get_resource_total_page_count(
            source.graphics_flags
        ):
            report.issue(
                "yed.resource.pages.count",
                "Page metadata does not reserve every resource chunk",
                path=pages_path,
            )
        block(
            dictionary.pages_info_pointer, 0x10 + 8 * pages.total_page_count, pages_path
        )

    for index, expression in enumerate(source.expressions):
        path = f"expressions[{index}]"
        offset = block(expression.pointer, EXPRESSION_BLOCK_SIZE, path, 16)
        for field, stride in (
            ("streams", 8),
            ("tracks", 4),
            ("springs", SPRING_BLOCK_SIZE),
            ("variables", 4),
        ):
            array(
                getattr(expression, field + "_info"),
                stride,
                len(getattr(expression, field)),
                f"{path}.{field}",
            )
        for si, stream in enumerate(expression.streams):
            block(
                stream.pointer,
                0x10 + len(stream.data1) + len(stream.data2) + len(stream.data3),
                f"{path}.streams[{si}]",
                16,
            )
        if offset is not None:
            pointer, length, capacity = struct.unpack_from("<QHH", data, offset + 0x60)
            name_offset = block(pointer, max(capacity, length + 1), f"{path}.name")
            if name_offset is not None:
                terminator = data.find(b"\0", name_offset, name_offset + capacity)
                if capacity < length or terminator < 0:
                    report.issue(
                        "yed.resource.name.capacity",
                        "Name capacity must contain the string terminator",
                        path=f"{path}.name",
                    )
    report.extend(validate_resource_block_layout(blocks, source.system_flags))
    return report
