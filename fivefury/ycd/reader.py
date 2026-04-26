from __future__ import annotations

from pathlib import Path

from ..binary import f32 as _f32, read_c_string, u16 as _u16, u32 as _u32, u64 as _u64
from ..common import clip_short_name
from ..metahash import MetaHash
from ..resource import checked_virtual_offset, read_virtual_pointer_array, split_rsc7_sections
from ..resolver import register_name
from .model import (
    Ycd,
    YcdAnimation,
    YcdAnimationBoneId,
    YcdClip,
    YcdClipAnimation,
    YcdClipAnimationEntry,
    YcdClipAnimationList,
    YcdClipProperty,
    YcdClipPropertyAttribute,
    YcdClipPropertyAttributeType,
    YcdClipTag,
    YcdClipType,
    YcdSequence,
)
from .sequences import parse_sequence_data

DAT_VIRTUAL_BASE = 0x50000000


class _YcdReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.animation_cache: dict[int, YcdAnimation] = {}
        self.clip_cache: dict[int, YcdClip] = {}
        self.property_cache: dict[int, YcdClipProperty] = {}
        self.tag_cache: dict[int, YcdClipTag] = {}
        self.sequence_cache: dict[int, YcdSequence] = {}
        self.active_tag_pointers: set[int] = set()

    def virtual_offset(self, pointer: int) -> int:
        return checked_virtual_offset(pointer, self.data, base=DAT_VIRTUAL_BASE)

    def read_c_string_at(self, pointer: int) -> str:
        if not pointer:
            return ""
        return read_c_string(self.data, self.virtual_offset(pointer))

    def read_pointer_array(self, pointer: int, count: int) -> list[int]:
        return read_virtual_pointer_array(self.data, pointer, count, base=DAT_VIRTUAL_BASE)

    def read_inline_list_header(self, offset: int) -> tuple[int, int, int]:
        return _u64(self.data, offset), _u16(self.data, offset + 8), _u16(self.data, offset + 10)

    def walk_chain(self, first_pointer: int, parser):
        items = []
        visited: set[int] = set()
        pointer = int(first_pointer)
        while pointer:
            if pointer in visited:
                break
            visited.add(pointer)
            item, pointer = parser(pointer)
            items.append(item)
        return items

    def parse_sequence(self, pointer: int) -> YcdSequence:
        pointer = int(pointer)
        cached = self.sequence_cache.get(pointer)
        if cached is not None:
            return cached

        offset = self.virtual_offset(pointer)
        data_length = _u32(self.data, offset + 0x04)
        raw_data = self.data[offset + 0x20 : offset + 0x20 + data_length]
        sequence = YcdSequence(
            hash=MetaHash(_u32(self.data, offset + 0x00)),
            data_length=data_length,
            frame_offset=_u32(self.data, offset + 0x0C),
            root_motion_refs_offset=_u32(self.data, offset + 0x10),
            num_frames=_u16(self.data, offset + 0x16),
            frame_length=_u16(self.data, offset + 0x18),
            indirect_quantize_float_num_ints=_u16(self.data, offset + 0x1A),
            quantize_float_value_bits=_u16(self.data, offset + 0x1C),
            chunk_size=int(self.data[offset + 0x1E]),
            root_motion_ref_counts=int(self.data[offset + 0x1F]),
            raw_data=bytes(raw_data),
            vft=_u32(self.data, offset + 0x00),
            unused_08h=_u32(self.data, offset + 0x08),
            unused_14h=_u16(self.data, offset + 0x14),
        )
        anim_sequences, root_position_refs, root_rotation_refs = parse_sequence_data(
            sequence.raw_data,
            num_frames=sequence.num_frames,
            chunk_size=sequence.chunk_size,
            frame_offset=sequence.frame_offset,
            frame_length=sequence.frame_length,
            root_motion_ref_counts=sequence.root_motion_ref_counts,
        )
        sequence.anim_sequences = anim_sequences
        sequence.root_position_refs = root_position_refs
        sequence.root_rotation_refs = root_rotation_refs
        self.sequence_cache[pointer] = sequence
        return sequence

    def parse_animation(self, pointer: int) -> YcdAnimation:
        pointer = int(pointer)
        cached = self.animation_cache.get(pointer)
        if cached is not None:
            return cached

        offset = self.virtual_offset(pointer)
        sequences_pointer, sequence_count, _ = self.read_inline_list_header(offset + 0x40)
        bone_ids_pointer, bone_id_count, _ = self.read_inline_list_header(offset + 0x50)
        sequence_pointers = self.read_pointer_array(sequences_pointer, sequence_count) if sequences_pointer and sequence_count else []
        sequences = [self.parse_sequence(item_pointer) for item_pointer in sequence_pointers]

        bone_ids: list[YcdAnimationBoneId] = []
        if bone_ids_pointer and bone_id_count:
            base = self.virtual_offset(bone_ids_pointer)
            for index in range(bone_id_count):
                entry_offset = base + (index * 4)
                bone_ids.append(
                    YcdAnimationBoneId(
                        bone_id=_u16(self.data, entry_offset + 0x00),
                        format=int(self.data[entry_offset + 0x02]),
                        track=int(self.data[entry_offset + 0x03]),
                    )
                )

        animation = YcdAnimation(
            hash=MetaHash(0),
            frames=_u16(self.data, offset + 0x14),
            sequence_frame_limit=_u16(self.data, offset + 0x16),
            duration=_f32(self.data, offset + 0x18),
            usage_count=_u32(self.data, offset + 0x3C),
            sequence_count=sequence_count,
            bone_id_count=bone_id_count,
            vft=_u32(self.data, offset + 0x00),
            flags=int(self.data[offset + 0x10]),
            max_seq_block_length=_u32(self.data, offset + 0x38),
            raw_unknown_hash=MetaHash(_u32(self.data, offset + 0x1C)),
            sequences=sequences,
            bone_ids=bone_ids,
        )
        for sequence in animation.sequences:
            for index, anim_sequence in enumerate(sequence.anim_sequences):
                if index < len(animation.bone_ids):
                    anim_sequence.bone_id = animation.bone_ids[index]
        self.animation_cache[pointer] = animation
        return animation

    def parse_animation_map_entry(self, pointer: int) -> tuple[tuple[int, MetaHash, YcdAnimation], int]:
        offset = self.virtual_offset(pointer)
        hash_value = MetaHash(_u32(self.data, offset + 0x00))
        animation_pointer = _u64(self.data, offset + 0x08)
        next_pointer = _u64(self.data, offset + 0x10)
        animation = self.parse_animation(animation_pointer) if animation_pointer else YcdAnimation(
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

    def parse_animation_map(self, pointer: int) -> tuple[dict[int, YcdAnimation], dict[int, YcdAnimation]]:
        if not pointer:
            return {}, {}
        offset = self.virtual_offset(pointer)
        buckets_pointer = _u64(self.data, offset + 0x18)
        bucket_capacity = _u16(self.data, offset + 0x20)
        animation_map: dict[int, YcdAnimation] = {}
        animation_pointer_map: dict[int, YcdAnimation] = {}
        for bucket_pointer in self.read_pointer_array(buckets_pointer, bucket_capacity):
            for animation_pointer, hash_value, animation in self.walk_chain(bucket_pointer, self.parse_animation_map_entry):
                animation_map[hash_value.uint] = animation
                animation_pointer_map[animation_pointer] = animation
        return animation_map, animation_pointer_map

    def parse_clip_property_attribute(self, pointer: int) -> YcdClipPropertyAttribute:
        offset = self.virtual_offset(pointer)
        attribute_type = YcdClipPropertyAttributeType(int(self.data[offset + 0x08]))
        value_offset = offset + 0x20
        value: object
        extra: float | int | None = None
        if attribute_type is YcdClipPropertyAttributeType.FLOAT:
            value = _f32(self.data, value_offset)
        elif attribute_type is YcdClipPropertyAttributeType.INT:
            value = int.from_bytes(self.data[value_offset : value_offset + 4], "little", signed=True)
        elif attribute_type is YcdClipPropertyAttributeType.BOOL:
            value = bool(_u32(self.data, value_offset))
        elif attribute_type is YcdClipPropertyAttributeType.STRING:
            value = self.read_c_string_at(_u64(self.data, value_offset))
        elif attribute_type is YcdClipPropertyAttributeType.VECTOR3:
            value = (
                _f32(self.data, value_offset + 0x00),
                _f32(self.data, value_offset + 0x04),
                _f32(self.data, value_offset + 0x08),
            )
            extra = _f32(self.data, value_offset + 0x0C)
        elif attribute_type is YcdClipPropertyAttributeType.VECTOR4:
            value = (
                _f32(self.data, value_offset + 0x00),
                _f32(self.data, value_offset + 0x04),
                _f32(self.data, value_offset + 0x08),
                _f32(self.data, value_offset + 0x0C),
            )
        elif attribute_type is YcdClipPropertyAttributeType.HASH_STRING:
            value = MetaHash(_u32(self.data, value_offset))
        else:  # pragma: no cover
            value = bytes(self.data[value_offset : value_offset + 0x10])
        return YcdClipPropertyAttribute(
            name_hash=MetaHash(_u32(self.data, offset + 0x18)),
            attribute_type=attribute_type,
            value=value,
            vft=_u32(self.data, offset + 0x00),
            unknown_04h=_u32(self.data, offset + 0x04),
            unknown_09h=int(self.data[offset + 0x09]),
            unknown_0ah=_u16(self.data, offset + 0x0A),
            unknown_0ch=_u32(self.data, offset + 0x0C),
            unknown_10h=_u32(self.data, offset + 0x10),
            unknown_14h=_u32(self.data, offset + 0x14),
            unknown_1ch=_u32(self.data, offset + 0x1C),
            extra=extra,
        )

    def parse_clip_property(self, pointer: int) -> YcdClipProperty:
        pointer = int(pointer)
        cached = self.property_cache.get(pointer)
        if cached is not None:
            return cached

        offset = self.virtual_offset(pointer)
        attributes_pointer = _u64(self.data, offset + 0x20)
        attribute_count = _u16(self.data, offset + 0x28)
        attribute_pointers = self.read_pointer_array(attributes_pointer, attribute_count) if attributes_pointer and attribute_count else []
        attributes = [self.parse_clip_property_attribute(item_pointer) for item_pointer in attribute_pointers]
        prop = YcdClipProperty(
            name_hash=MetaHash(_u32(self.data, offset + 0x18)),
            attributes=attributes,
            vft=_u32(self.data, offset + 0x00),
            unknown_04h=_u32(self.data, offset + 0x04),
            unknown_08h=_u32(self.data, offset + 0x08),
            unknown_0ch=_u32(self.data, offset + 0x0C),
            unknown_10h=_u32(self.data, offset + 0x10),
            unknown_14h=_u32(self.data, offset + 0x14),
            unknown_1ch=_u32(self.data, offset + 0x1C),
            unknown_2ch=_u32(self.data, offset + 0x2C),
            unknown_30h=_u32(self.data, offset + 0x30),
            unknown_34h=_u32(self.data, offset + 0x34),
            unknown_hash=MetaHash(_u32(self.data, offset + 0x38)),
            unknown_3ch=_u32(self.data, offset + 0x3C),
        )
        self.property_cache[pointer] = prop
        return prop

    def parse_clip_property_map_entry(self, pointer: int) -> tuple[tuple[MetaHash, YcdClipProperty], int]:
        offset = self.virtual_offset(pointer)
        prop_hash = MetaHash(_u32(self.data, offset + 0x00))
        data_pointer = _u64(self.data, offset + 0x08)
        next_pointer = _u64(self.data, offset + 0x10)
        prop = self.parse_clip_property(data_pointer)
        prop.name_hash = prop_hash
        return (prop_hash, prop), next_pointer

    def parse_clip_property_map(self, pointer: int) -> tuple[list[YcdClipProperty], int]:
        if not pointer:
            return [], 0
        offset = self.virtual_offset(pointer)
        bucket_pointer = _u64(self.data, offset + 0x00)
        bucket_capacity = _u16(self.data, offset + 0x08)
        reserved_0ch = _u32(self.data, offset + 0x0C)
        properties: list[YcdClipProperty] = []
        seen: set[int] = set()
        for chain_pointer in self.read_pointer_array(bucket_pointer, bucket_capacity):
            for prop_hash, prop in self.walk_chain(chain_pointer, self.parse_clip_property_map_entry):
                if prop_hash.uint in seen:
                    continue
                seen.add(prop_hash.uint)
                properties.append(prop)
        return properties, reserved_0ch

    def parse_clip_tag(self, pointer: int) -> YcdClipTag:
        pointer = int(pointer)
        cached = self.tag_cache.get(pointer)
        if cached is not None:
            return cached
        if pointer in self.active_tag_pointers:
            return YcdClipTag(name_hash=MetaHash(0))

        self.active_tag_pointers.add(pointer)
        offset = self.virtual_offset(pointer)
        attributes_pointer = _u64(self.data, offset + 0x20)
        attribute_count = _u16(self.data, offset + 0x28)
        attribute_pointers = self.read_pointer_array(attributes_pointer, attribute_count) if attributes_pointer and attribute_count else []
        attributes = [self.parse_clip_property_attribute(item_pointer) for item_pointer in attribute_pointers]
        nested_pointer = _u64(self.data, offset + 0x48)
        nested_tags, has_block_tag, tag_list_header = self.parse_clip_tag_list(nested_pointer)
        tag = YcdClipTag(
            name_hash=MetaHash(_u32(self.data, offset + 0x18)),
            attributes=attributes,
            vft=_u32(self.data, offset + 0x00),
            unknown_04h=_u32(self.data, offset + 0x04),
            unknown_08h=_u32(self.data, offset + 0x08),
            unknown_0ch=_u32(self.data, offset + 0x0C),
            unknown_10h=_u32(self.data, offset + 0x10),
            unknown_14h=_u32(self.data, offset + 0x14),
            unknown_1ch=_u32(self.data, offset + 0x1C),
            unknown_2ch=_u32(self.data, offset + 0x2C),
            unknown_30h=_u32(self.data, offset + 0x30),
            unknown_34h=_u32(self.data, offset + 0x34),
            unknown_hash=MetaHash(_u32(self.data, offset + 0x38)),
            unknown_3ch=_u32(self.data, offset + 0x3C),
            start_phase=_f32(self.data, offset + 0x40),
            end_phase=_f32(self.data, offset + 0x44),
            tags=nested_tags,
            has_block_tag=has_block_tag,
            **tag_list_header,
        )
        self.active_tag_pointers.discard(pointer)
        self.tag_cache[pointer] = tag
        return tag

    def parse_clip_tag_list(self, pointer: int) -> tuple[list[YcdClipTag], bool, dict[str, int]]:
        if not pointer:
            return [], False, {
                "tag_list_reserved_0ch": 0,
                "tag_list_reserved_14h": 0,
                "tag_list_reserved_18h": 0,
                "tag_list_reserved_1ch": 0,
            }
        offset = self.virtual_offset(pointer)
        tags_pointer = _u64(self.data, offset + 0x00)
        tag_count = _u16(self.data, offset + 0x08)
        has_block_tag = bool(_u32(self.data, offset + 0x10))
        tag_pointers = self.read_pointer_array(tags_pointer, tag_count) if tags_pointer and tag_count else []
        return [self.parse_clip_tag(item_pointer) for item_pointer in tag_pointers], has_block_tag, {
            "tag_list_reserved_0ch": _u32(self.data, offset + 0x0C),
            "tag_list_reserved_14h": _u32(self.data, offset + 0x14),
            "tag_list_reserved_18h": _u32(self.data, offset + 0x18),
            "tag_list_reserved_1ch": _u32(self.data, offset + 0x1C),
        }

    def parse_clip_base(self, pointer: int) -> tuple[dict[str, object], int]:
        offset = self.virtual_offset(pointer)
        name_pointer = _u64(self.data, offset + 0x18)
        tags_pointer = _u64(self.data, offset + 0x38)
        properties_pointer = _u64(self.data, offset + 0x40)
        name = self.read_c_string_at(name_pointer)
        if name:
            register_name(name)
            register_name(clip_short_name(name))
        tags, has_block_tag, tag_list_header = self.parse_clip_tag_list(tags_pointer)
        properties, property_map_reserved_0ch = self.parse_clip_property_map(properties_pointer)
        return (
            {
                "hash": MetaHash(0),
                "name": name,
                "short_name": clip_short_name(name),
                "clip_type": YcdClipType(_u32(self.data, offset + 0x10)),
                "property_count": len(properties),
                "tag_count": len(tags),
                "flags": _u32(self.data, offset + 0x30),
                "vft": _u32(self.data, offset + 0x00),
                "tags": tags,
                "properties": properties,
                "unknown_04h": _u32(self.data, offset + 0x04),
                "unknown_08h": _u32(self.data, offset + 0x08),
                "unknown_0ch": _u32(self.data, offset + 0x0C),
                "unknown_14h": _u32(self.data, offset + 0x14),
                "unknown_24h": _u32(self.data, offset + 0x24),
                "reserved_34h": _u32(self.data, offset + 0x34),
                "unknown_48h": _u32(self.data, offset + 0x48),
                "unknown_4ch": _u32(self.data, offset + 0x4C),
                "has_block_tag": has_block_tag,
                "property_map_reserved_0ch": property_map_reserved_0ch,
                **tag_list_header,
            },
            offset,
        )

    def parse_clip(self, pointer: int, animation_map: dict[int, YcdAnimation], animation_pointer_map: dict[int, YcdAnimation]) -> YcdClip:
        pointer = int(pointer)
        cached = self.clip_cache.get(pointer)
        if cached is not None:
            return cached

        base, offset = self.parse_clip_base(pointer)
        clip_type = base["clip_type"]
        if clip_type is YcdClipType.ANIMATION:
            animation_pointer = _u64(self.data, offset + 0x50)
            animation = animation_pointer_map.get(animation_pointer)
            if animation is None and animation_pointer:
                animation = self.parse_animation(animation_pointer)
                animation_pointer_map[animation_pointer] = animation
                if animation.hash:
                    animation_map[animation.hash.uint] = animation
            animation_hash = animation.hash if animation is not None else MetaHash(0)
            clip: YcdClip = YcdClipAnimation(
                **base,
                animation_hash=animation_hash,
                start_time=_f32(self.data, offset + 0x58),
                end_time=_f32(self.data, offset + 0x5C),
                rate=_f32(self.data, offset + 0x60),
                animation=animation,
                reserved_64h=_u32(self.data, offset + 0x64),
                reserved_68h=_u32(self.data, offset + 0x68),
                reserved_6ch=_u32(self.data, offset + 0x6C),
            )
        elif clip_type is YcdClipType.ANIMATION_LIST:
            animations_pointer = _u64(self.data, offset + 0x50)
            animation_count = _u16(self.data, offset + 0x58)
            entries: list[YcdClipAnimationEntry] = []
            if animations_pointer and animation_count:
                base_pointer = self.virtual_offset(animations_pointer)
                for index in range(animation_count):
                    entry_offset = base_pointer + (index * 24)
                    animation_pointer = _u64(self.data, entry_offset + 0x10)
                    animation = animation_pointer_map.get(animation_pointer)
                    if animation is None and animation_pointer:
                        animation = self.parse_animation(animation_pointer)
                        animation_pointer_map[animation_pointer] = animation
                        if animation.hash:
                            animation_map[animation.hash.uint] = animation
                    animation_hash = animation.hash if animation is not None else MetaHash(0)
                    entries.append(
                        YcdClipAnimationEntry(
                            start_time=_f32(self.data, entry_offset + 0x00),
                            end_time=_f32(self.data, entry_offset + 0x04),
                            rate=_f32(self.data, entry_offset + 0x08),
                            alignment_padding_0ch=_u32(self.data, entry_offset + 0x0C),
                            animation_hash=animation_hash,
                            animation=animation,
                        )
                    )
            clip = YcdClipAnimationList(
                **base,
                total_duration=_f32(self.data, offset + 0x60),
                animations=entries,
                unknown_5ch=_u32(self.data, offset + 0x5C),
                parallel=bool(self.data[offset + 0x64]),
                parallel_padding=bytes(self.data[offset + 0x65 : offset + 0x68]),
                reserved_68h=_u32(self.data, offset + 0x68),
                reserved_6ch=_u32(self.data, offset + 0x6C),
            )
        else:
            clip = YcdClip(**base)
        self.clip_cache[pointer] = clip
        return clip

    def parse_clip_map_entry(self, pointer: int, animation_map: dict[int, YcdAnimation], animation_pointer_map: dict[int, YcdAnimation]) -> tuple[tuple[MetaHash, YcdClip], int]:
        offset = self.virtual_offset(pointer)
        hash_value = MetaHash(_u32(self.data, offset + 0x00))
        clip_pointer = _u64(self.data, offset + 0x08)
        next_pointer = _u64(self.data, offset + 0x10)
        clip = self.parse_clip(clip_pointer, animation_map, animation_pointer_map)
        clip.hash = hash_value
        return (hash_value, clip), next_pointer

    def parse_clip_map(self, pointer: int, bucket_capacity: int, animation_map: dict[int, YcdAnimation], animation_pointer_map: dict[int, YcdAnimation]) -> dict[int, YcdClip]:
        clip_map: dict[int, YcdClip] = {}
        for bucket_pointer in self.read_pointer_array(pointer, bucket_capacity):
            for hash_value, clip in self.walk_chain(
                bucket_pointer,
                lambda current_pointer: self.parse_clip_map_entry(current_pointer, animation_map, animation_pointer_map),
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

    reader = _YcdReader(system_data)
    root_offset = 0x10
    animations_pointer = _u64(system_data, root_offset + 0x08)
    clips_pointer = _u64(system_data, root_offset + 0x18)
    clips_map_capacity = _u16(system_data, root_offset + 0x20)
    clips_entry_count = _u16(system_data, root_offset + 0x22)
    animation_map, animation_pointer_map = reader.parse_animation_map(animations_pointer)
    clip_map = reader.parse_clip_map(clips_pointer, clips_map_capacity, animation_map, animation_pointer_map)
    animations = sorted(animation_map.values(), key=lambda animation: animation.hash.uint)
    clips = sorted(clip_map.values(), key=lambda clip: clip.hash.uint)

    animation_bucket_capacity = 0
    animation_entry_count = 0
    if animations_pointer:
        animation_map_offset = reader.virtual_offset(animations_pointer)
        animation_bucket_capacity = _u16(system_data, animation_map_offset + 0x20)
        animation_entry_count = _u16(system_data, animation_map_offset + 0x22)

    return Ycd(
        header=header,
        clips=clips,
        animations=animations,
        path=str(path) if path is not None else None,
        clip_map=clip_map,
        animation_map=animation_map,
        clip_bucket_capacity=clips_map_capacity,
        clip_entry_count=clips_entry_count,
        animation_bucket_capacity=animation_bucket_capacity,
        animation_entry_count=animation_entry_count,
    )


__all__ = ["read_ycd"]
