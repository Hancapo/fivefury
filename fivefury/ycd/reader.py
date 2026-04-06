from __future__ import annotations

from pathlib import Path

from ..binary import read_c_string, u16 as _u16, u32 as _u32, u64 as _u64, f32 as _f32
from ..metahash import MetaHash
from ..resource import split_rsc7_sections, virtual_to_offset
from ..resolver import register_name
from .model import (
    Ycd,
    YcdAnimation,
    YcdClip,
    YcdClipAnimation,
    YcdClipAnimationEntry,
    YcdClipAnimationList,
    YcdClipType,
)

DAT_VIRTUAL_BASE = 0x50000000


def _virtual_offset(pointer: int, data: bytes) -> int:
    offset = virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE)
    if offset < 0 or offset >= len(data):
        raise ValueError("virtual pointer is out of range")
    return offset


def _read_c_string_at(pointer: int, data: bytes) -> str:
    if not pointer:
        return ""
    return read_c_string(data, _virtual_offset(pointer, data))


def _read_pointer_array(pointer: int, count: int, data: bytes) -> list[int]:
    if not pointer or count <= 0:
        return []
    offset = _virtual_offset(pointer, data)
    return [_u64(data, offset + (index * 8)) for index in range(count)]


def _read_list_header(pointer: int, data: bytes) -> tuple[int, int, int]:
    if not pointer:
        return 0, 0, 0
    offset = _virtual_offset(pointer, data)
    entries_pointer = _u64(data, offset)
    entries_count = _u16(data, offset + 8)
    entries_capacity = _u16(data, offset + 10)
    return entries_pointer, entries_count, entries_capacity


def _clip_short_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    return normalized.lower()


def _walk_chain(first_pointer: int, parser, data: bytes):
    items = []
    visited: set[int] = set()
    pointer = int(first_pointer)
    while pointer:
        if pointer in visited:
            break
        visited.add(pointer)
        item, pointer = parser(pointer, data)
        items.append(item)
    return items


def _parse_animation(pointer: int, data: bytes) -> YcdAnimation:
    offset = _virtual_offset(pointer, data)
    hash_value = MetaHash(0)
    frames = _u16(data, offset + 0x14)
    sequence_frame_limit = _u16(data, offset + 0x16)
    duration = _f32(data, offset + 0x18)
    unknown_hash = MetaHash(_u32(data, offset + 0x1C))
    usage_count = _u32(data, offset + 0x3C)

    sequences_pointer, sequence_count, _ = _read_list_header(_u64(data, offset + 0x40), data)
    _ = sequences_pointer
    bone_ids_pointer, bone_id_count, _ = _read_list_header(_u64(data, offset + 0x50), data)
    _ = bone_ids_pointer

    return YcdAnimation(
        hash=hash_value,
        frames=frames,
        sequence_frame_limit=sequence_frame_limit,
        duration=duration,
        usage_count=usage_count,
        sequence_count=sequence_count,
        bone_id_count=bone_id_count,
        vft=_u32(data, offset + 0x00),
        flags=int(data[offset + 0x10]),
        raw_unknown_hash=unknown_hash,
    )


def _parse_animation_map_entry(pointer: int, data: bytes) -> tuple[tuple[int, MetaHash, YcdAnimation], int]:
    offset = _virtual_offset(pointer, data)
    hash_value = MetaHash(_u32(data, offset + 0x00))
    animation_pointer = _u64(data, offset + 0x08)
    next_pointer = _u64(data, offset + 0x10)
    animation = _parse_animation(animation_pointer, data) if animation_pointer else YcdAnimation(
        hash=hash_value,
        frames=0,
        sequence_frame_limit=0,
        duration=0.0,
        usage_count=0,
        sequence_count=0,
        bone_id_count=0,
    )
    animation.hash = hash_value
    return (animation_pointer, hash_value, animation), next_pointer


def _parse_clip_animation_entry(pointer: int, data: bytes, animation_map: dict[int, YcdAnimation], animation_pointer_map: dict[int, YcdAnimation]) -> YcdClipAnimationEntry:
    offset = _virtual_offset(pointer, data)
    animation_pointer = _u64(data, offset + 0x10)
    animation = animation_pointer_map.get(animation_pointer)
    if animation is None and animation_pointer:
        animation = _parse_animation(animation_pointer, data)
        animation_pointer_map[animation_pointer] = animation
        if animation.hash:
            animation_map[animation.hash.uint] = animation
    animation_hash = animation.hash if animation is not None else MetaHash(0)
    return YcdClipAnimationEntry(
        start_time=_f32(data, offset + 0x00),
        end_time=_f32(data, offset + 0x04),
        rate=_f32(data, offset + 0x08),
        animation_hash=animation_hash,
        animation=animation,
    )


def _parse_clip_base(pointer: int, data: bytes) -> tuple[dict[str, object], int]:
    offset = _virtual_offset(pointer, data)
    name_pointer = _u64(data, offset + 0x18)
    tags_pointer = _u64(data, offset + 0x38)
    properties_pointer = _u64(data, offset + 0x40)
    name = _read_c_string_at(name_pointer, data)
    if name:
        register_name(name)
        register_name(_clip_short_name(name))
    _, tag_count, _ = _read_list_header(tags_pointer, data)
    _, property_count, _ = _read_list_header(properties_pointer, data)
    return (
        {
            "hash": MetaHash(0),
            "name": name,
            "short_name": _clip_short_name(name),
            "clip_type": YcdClipType(_u32(data, offset + 0x10)),
            "property_count": property_count,
            "tag_count": tag_count,
            "unknown_30h": _u32(data, offset + 0x30),
            "vft": _u32(data, offset + 0x00),
        },
        offset,
    )


def _parse_clip(pointer: int, data: bytes, animation_map: dict[int, YcdAnimation], animation_pointer_map: dict[int, YcdAnimation]) -> YcdClip:
    base, offset = _parse_clip_base(pointer, data)
    clip_type = base["clip_type"]
    if clip_type is YcdClipType.ANIMATION:
        animation_pointer = _u64(data, offset + 0x50)
        animation = animation_pointer_map.get(animation_pointer)
        if animation is None and animation_pointer:
            animation = _parse_animation(animation_pointer, data)
            animation_pointer_map[animation_pointer] = animation
            if animation.hash:
                animation_map[animation.hash.uint] = animation
        animation_hash = animation.hash if animation is not None else MetaHash(0)
        return YcdClipAnimation(
            **base,
            animation_hash=animation_hash,
            start_time=_f32(data, offset + 0x58),
            end_time=_f32(data, offset + 0x5C),
            rate=_f32(data, offset + 0x60),
            animation=animation,
        )
    if clip_type is YcdClipType.ANIMATION_LIST:
        animations_pointer = _u64(data, offset + 0x50)
        animation_count = _u16(data, offset + 0x58)
        entries: list[YcdClipAnimationEntry] = []
        if animations_pointer and animation_count:
            entries = [
                _parse_clip_animation_entry(entry_pointer, data, animation_map, animation_pointer_map)
                for entry_pointer in _iter_simple_array_pointers(animations_pointer, animation_count, 24, data)
            ]
        return YcdClipAnimationList(
            **base,
            duration=_f32(data, offset + 0x60),
            animations=entries,
        )
    return YcdClip(**base)


def _iter_simple_array_pointers(pointer: int, count: int, stride: int, data: bytes) -> list[int]:
    if not pointer or count <= 0:
        return []
    base = _virtual_offset(pointer, data)
    return [DAT_VIRTUAL_BASE + base + (index * stride) for index in range(count)]


def _parse_clip_map_entry(pointer: int, data: bytes, animation_map: dict[int, YcdAnimation], animation_pointer_map: dict[int, YcdAnimation]) -> tuple[tuple[MetaHash, YcdClip], int]:
    offset = _virtual_offset(pointer, data)
    hash_value = MetaHash(_u32(data, offset + 0x00))
    clip_pointer = _u64(data, offset + 0x08)
    next_pointer = _u64(data, offset + 0x10)
    clip = _parse_clip(clip_pointer, data, animation_map, animation_pointer_map)
    clip.hash = hash_value
    return (hash_value, clip), next_pointer


def _parse_animation_map(pointer: int, data: bytes) -> tuple[dict[int, YcdAnimation], dict[int, YcdAnimation]]:
    if not pointer:
        return {}, {}
    offset = _virtual_offset(pointer, data)
    buckets_pointer = _u64(data, offset + 0x18)
    bucket_capacity = _u16(data, offset + 0x20)
    animation_map: dict[int, YcdAnimation] = {}
    animation_pointer_map: dict[int, YcdAnimation] = {}
    for bucket_pointer in _read_pointer_array(buckets_pointer, bucket_capacity, data):
        for animation_pointer, hash_value, animation in _walk_chain(bucket_pointer, _parse_animation_map_entry, data):
            animation_map[hash_value.uint] = animation
            animation_pointer_map[animation_pointer] = animation
    return animation_map, animation_pointer_map


def _parse_clip_map(pointer: int, bucket_capacity: int, data: bytes, animation_map: dict[int, YcdAnimation], animation_pointer_map: dict[int, YcdAnimation]) -> dict[int, YcdClip]:
    clip_map: dict[int, YcdClip] = {}
    for bucket_pointer in _read_pointer_array(pointer, bucket_capacity, data):
        for hash_value, clip in _walk_chain(
            bucket_pointer,
            lambda current_pointer, current_data: _parse_clip_map_entry(current_pointer, current_data, animation_map, animation_pointer_map),
            data,
        ):
            clip_map[hash_value.uint] = clip
    return clip_map


def read_ycd(source: bytes | str | Path, *, path: str | Path | None = None) -> Ycd:
    if isinstance(source, (str, Path)):
        path = source
        source = Path(source).read_bytes()
    header, system_data, graphics_data = split_rsc7_sections(bytes(source))
    if graphics_data:
        raise ValueError("graphics-backed YCD resources are not supported yet")
    root_offset = 0x10
    animations_pointer = _u64(system_data, root_offset + 0x08)
    clips_pointer = _u64(system_data, root_offset + 0x18)
    clips_map_capacity = _u16(system_data, root_offset + 0x20)
    animation_map, animation_pointer_map = _parse_animation_map(animations_pointer, system_data)
    clip_map = _parse_clip_map(clips_pointer, clips_map_capacity, system_data, animation_map, animation_pointer_map)
    animations = sorted(animation_map.values(), key=lambda animation: animation.hash.uint)
    clips = sorted(clip_map.values(), key=lambda clip: clip.hash.uint)
    return Ycd(
        header=header,
        clips=clips,
        animations=animations,
        path=str(path) if path is not None else None,
        clip_map=clip_map,
        animation_map=animation_map,
    )


__all__ = ["read_ycd"]
