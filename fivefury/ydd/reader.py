from __future__ import annotations

import dataclasses
import struct
from pathlib import Path

from ..binary import u16 as _u16
from ..binary import u32 as _u32
from ..binary import u64 as _u64
from ..common import ByteSource, read_source_bytes
from ..resolver import resolve_hash
from ..resource import (
    RSC7_MAGIC,
    checked_virtual_offset,
    read_virtual_pointer_array,
    split_rsc7_sections,
    virtual_to_offset,
)
from ..ydr.defs import LOD_ORDER, LOD_POINTER_OFFSETS
from ..ydr.reader import _read_ydr_from_sections
from ..ydr.shaders import ShaderLibrary
from .model import Ydd, YddDrawable
from .runtime_headers import get_ydd_runtime_profile_for_version

_DAT_VIRTUAL_BASE = 0x50000000
_DRAWABLE_FIELDS_OFFSET = 0x10
_HASHES_POINTER_OFFSET = 0x20
_HASHES_COUNT_OFFSET = 0x28
_DRAWABLES_POINTER_OFFSET = 0x30
_DRAWABLES_COUNT_OFFSET = 0x38


def _record_pointed_vft(
    system_data: bytes,
    pointer: int,
    values: set[int],
) -> int | None:
    if not pointer:
        return None
    try:
        offset = checked_virtual_offset(pointer, system_data, base=_DAT_VIRTUAL_BASE)
    except ValueError:
        return None
    if offset + 4 > len(system_data):
        return None
    values.add(int(_u32(system_data, offset)))
    return offset


def _collect_drawable_runtime_headers(
    system_data: bytes,
    drawable_root_offset: int,
    values: dict[str, set[int]],
) -> None:
    root_offset = drawable_root_offset + _DRAWABLE_FIELDS_OFFSET

    shader_group_offset = _record_pointed_vft(
        system_data,
        _u64(system_data, root_offset + 0x00),
        values["shader_group"],
    )
    if shader_group_offset is not None:
        shaders_pointer = _u64(system_data, shader_group_offset + 0x10)
        shader_count = _u16(system_data, shader_group_offset + 0x18)
        for shader_pointer in _read_pointer_array(
            system_data,
            shaders_pointer,
            shader_count,
        ):
            try:
                shader_offset = checked_virtual_offset(
                    shader_pointer,
                    system_data,
                    base=_DAT_VIRTUAL_BASE,
                )
            except ValueError:
                continue
            parameters_pointer = _u64(system_data, shader_offset + 0x00)
            parameter_count = system_data[shader_offset + 0x10]
            if not parameters_pointer or not parameter_count:
                continue
            try:
                parameters_offset = checked_virtual_offset(
                    parameters_pointer,
                    system_data,
                    base=_DAT_VIRTUAL_BASE,
                )
            except ValueError:
                continue
            for parameter_index in range(parameter_count):
                entry_offset = parameters_offset + parameter_index * 16
                if entry_offset + 16 > len(system_data):
                    break
                if system_data[entry_offset] != 0:
                    continue
                texture_offset = _record_pointed_vft(
                    system_data,
                    _u64(system_data, entry_offset + 0x08),
                    set(),
                )
                if texture_offset is None or texture_offset + 0x33 > len(system_data):
                    continue
                if system_data[texture_offset + 0x32] & 0x03 == 2:
                    values["texture_base"].add(
                        int(_u32(system_data, texture_offset))
                    )

    _record_pointed_vft(
        system_data,
        _u64(system_data, root_offset + 0x08),
        values["skeleton"],
    )
    _record_pointed_vft(
        system_data,
        _u64(system_data, root_offset + 0x80),
        values["joints"],
    )

    for lod in LOD_ORDER:
        lod_pointer = _u64(system_data, root_offset + LOD_POINTER_OFFSETS[lod])
        if not lod_pointer:
            continue
        try:
            lod_offset = checked_virtual_offset(
                lod_pointer,
                system_data,
                base=_DAT_VIRTUAL_BASE,
            )
        except ValueError:
            continue
        model_pointers = _read_pointer_array(
            system_data,
            _u64(system_data, lod_offset + 0x00),
            _u16(system_data, lod_offset + 0x08),
        )
        for model_pointer in model_pointers:
            model_offset = _record_pointed_vft(
                system_data,
                model_pointer,
                values["model"],
            )
            if model_offset is None:
                continue
            geometry_pointers = _read_pointer_array(
                system_data,
                _u64(system_data, model_offset + 0x08),
                _u16(system_data, model_offset + 0x10),
            )
            for geometry_pointer in geometry_pointers:
                geometry_offset = _record_pointed_vft(
                    system_data,
                    geometry_pointer,
                    values["geometry"],
                )
                if geometry_offset is None:
                    continue
                _record_pointed_vft(
                    system_data,
                    _u64(system_data, geometry_offset + 0x18),
                    values["vertex_buffer"],
                )
                _record_pointed_vft(
                    system_data,
                    _u64(system_data, geometry_offset + 0x38),
                    values["index_buffer"],
                )


def _read_uint_array(system_data: bytes, pointer: int, count: int) -> list[int]:
    if not pointer or count <= 0:
        return []
    start = checked_virtual_offset(pointer, system_data, base=_DAT_VIRTUAL_BASE)
    end = start + (count * 4)
    if end > len(system_data):
        raise ValueError("uint array is truncated")
    return [int(_u32(system_data, start + index * 4)) for index in range(count)]


def _read_pointer_array(system_data: bytes, pointer: int, count: int) -> list[int]:
    return read_virtual_pointer_array(system_data, pointer, count, base=_DAT_VIRTUAL_BASE)


def _name_from_hash(name_hash: int) -> str:
    resolved = resolve_hash(name_hash)
    if resolved:
        return resolved
    return f"hash_{int(name_hash) & 0xFFFFFFFF:08X}"


def _internal_drawable_path(container_path: str, name: str, index: int) -> str:
    clean_name = str(name or f"drawable_{index}")
    if not container_path:
        return f"{clean_name}.ydr"
    return f"{Path(container_path).stem}/{clean_name}.ydr"


def read_ydd(
    source: ByteSource,
    *,
    path: str | Path = "",
    shader_library: ShaderLibrary | None = None,
) -> Ydd:
    data = read_source_bytes(source)
    if len(data) < 16:
        raise ValueError("YDD data is too short")
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != RSC7_MAGIC:
        raise ValueError("YDD data must be a standalone RSC7 resource")

    header, system_data, graphics_data = split_rsc7_sections(data)
    hashes_pointer = _u64(system_data, _HASHES_POINTER_OFFSET)
    hashes_count = _u16(system_data, _HASHES_COUNT_OFFSET)
    drawables_pointer = _u64(system_data, _DRAWABLES_POINTER_OFFSET)
    drawables_count = _u16(system_data, _DRAWABLES_COUNT_OFFSET)

    hashes = _read_uint_array(system_data, hashes_pointer, hashes_count)
    drawable_pointers = _read_pointer_array(system_data, drawables_pointer, drawables_count)
    resource_path = str(path or source) if isinstance(source, (str, Path)) or path else ""

    entries: list[YddDrawable] = []
    drawable_vfts: set[int] = set()
    runtime_header_vfts = {
        name: set()
        for name in (
            "shader_group",
            "texture_base",
            "model",
            "geometry",
            "vertex_buffer",
            "index_buffer",
            "skeleton",
            "joints",
        )
    }
    for index, drawable_pointer in enumerate(drawable_pointers):
        if not drawable_pointer:
            continue
        name_hash = hashes[index] if index < len(hashes) else 0
        name = _name_from_hash(name_hash)
        drawable_root_offset = virtual_to_offset(drawable_pointer, base=_DAT_VIRTUAL_BASE)
        root_offset = drawable_root_offset + _DRAWABLE_FIELDS_OFFSET
        if root_offset < 0 or root_offset >= len(system_data):
            raise ValueError("YDD drawable pointer is out of range")
        drawable_vfts.add(int(_u32(system_data, drawable_root_offset)))
        _collect_drawable_runtime_headers(
            system_data,
            drawable_root_offset,
            runtime_header_vfts,
        )
        drawable = _read_ydr_from_sections(
            header,
            system_data,
            graphics_data,
            root_offset=root_offset,
            path=_internal_drawable_path(resource_path, name, index),
            shader_library=shader_library,
        )
        entries.append(YddDrawable(name_hash=name_hash, name=name, drawable=drawable))

    runtime_profile = None
    if len(drawable_vfts) > 1:
        observed = ", ".join(f"0x{value:08X}" for value in sorted(drawable_vfts))
        raise ValueError(f"YDD contains mixed drawable runtime headers: {observed}")
    if len(drawable_vfts) == 1:
        default_profile = get_ydd_runtime_profile_for_version(int(header.version))
        default_headers = default_profile.drawable_headers
        mixed_headers = {
            name: observed
            for name, observed in runtime_header_vfts.items()
            if len(observed) > 1
        }
        if mixed_headers:
            details = "; ".join(
                f"{name}=" + ",".join(
                    f"0x{value:08X}" for value in sorted(observed)
                )
                for name, observed in sorted(mixed_headers.items())
            )
            raise ValueError(f"YDD contains mixed runtime headers: {details}")
        preserved_headers = {
            name: next(iter(observed)) if len(observed) == 1 else getattr(default_headers, name)
            for name, observed in runtime_header_vfts.items()
        }
        runtime_profile = dataclasses.replace(
            default_profile,
            dictionary_vft=int(_u32(system_data, 0)),
            drawable_headers=dataclasses.replace(
                default_headers,
                drawable=next(iter(drawable_vfts)),
                **preserved_headers,
            ),
        )

    return Ydd(
        version=int(header.version),
        path=resource_path,
        drawables=entries,
        runtime_profile=runtime_profile,
    )


__all__ = [
    "read_ydd",
]
