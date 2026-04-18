from __future__ import annotations

from pathlib import Path
from typing import Any

from ..metahash import MetaHash
from ..resource import ResourceBlockSpan, ResourceWriter, build_rsc7, get_resource_total_page_count, layout_resource_sections
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
    _resolve_ycd_clip_hash,
)
from .sequences import build_sequence_data
from .sequence_tracks import get_ycd_track_format

DAT_VIRTUAL_BASE = 0x50000000
_RESOURCE_FILE_VFT = 1079444200
_ANIMATION_MAP_VFT = 1079671816
_DEFAULT_ROOT_UNKNOWN_20H = 0x00000101
_DEFAULT_ROOT_UNKNOWN_34H = 0x01000000
_DEFAULT_PROPERTY_MAP_UNKNOWN_0CH = 0x01000000


def _clip_short_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    return normalized.lower()


def _get_num_hash_buckets(n_hashes: int) -> int:
    if n_hashes < 11:
        return 11
    if n_hashes < 29:
        return 29
    if n_hashes < 59:
        return 59
    if n_hashes < 107:
        return 107
    if n_hashes < 191:
        return 191
    if n_hashes < 331:
        return 331
    if n_hashes < 563:
        return 563
    if n_hashes < 953:
        return 953
    if n_hashes < 1609:
        return 1609
    if n_hashes < 2729:
        return 2729
    if n_hashes < 4621:
        return 4621
    if n_hashes < 7841:
        return 7841
    if n_hashes < 13297:
        return 13297
    if n_hashes < 22571:
        return 22571
    if n_hashes < 38351:
        return 38351
    if n_hashes < 65167:
        return 65167
    return 65521


def _resolve_hash(value: MetaHash | int | str | None, *, fallback_text: str | None = None) -> MetaHash:
    if isinstance(value, MetaHash):
        if value.uint != 0:
            return value
        if fallback_text:
            return MetaHash(fallback_text)
        return value
    if value not in (None, "", 0):
        return MetaHash(value)
    if fallback_text:
        return MetaHash(fallback_text)
    return MetaHash(0)


def _resolve_clip_hash(clip: YcdClip) -> MetaHash:
    resolved = _resolve_ycd_clip_hash(clip)
    if resolved.uint:
        return resolved
    return MetaHash(clip.short_name or _clip_short_name(clip.name))


class _YcdWriter:
    def __init__(self, ycd: Ycd) -> None:
        self.ycd = ycd
        self.writer = ResourceWriter(0x80)
        self.string_offsets: dict[str, int] = {}
        self.sequence_offsets: dict[int, int] = {}
        self.animation_offsets: dict[int, int] = {}
        self.clip_offsets: dict[int, int] = {}
        self.property_offsets: dict[int, int] = {}
        self.tag_offsets: dict[int, int] = {}
        self.animation_usage_counts = self._compute_animation_usage_counts()

    def vptr(self, offset: int) -> int:
        return DAT_VIRTUAL_BASE + int(offset)

    def _identity(self, value: Any) -> int:
        return id(value)

    def _compute_animation_usage_counts(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for animation in self.ycd.animations:
            animation_hash = _resolve_hash(animation.hash, fallback_text=animation.name).uint
            if animation_hash:
                counts[animation_hash] = counts.get(animation_hash, 0) + 1
        for clip in self.ycd.clips:
            if isinstance(clip, YcdClipAnimation):
                animation_hash = _resolve_hash(
                    clip.animation.hash if clip.animation is not None else clip.animation_hash,
                    fallback_text=clip.animation.name if clip.animation is not None else None,
                ).uint
                if animation_hash:
                    counts[animation_hash] = counts.get(animation_hash, 0) + 1
            elif isinstance(clip, YcdClipAnimationList):
                for entry in clip.animations:
                    animation_hash = _resolve_hash(
                        entry.animation.hash if entry.animation is not None else entry.animation_hash,
                    fallback_text=entry.animation.name if entry.animation is not None else None,
                ).uint
                if animation_hash:
                    counts[animation_hash] = counts.get(animation_hash, 0) + 1
        return counts

    def _synchronize_animation_bone_ids(self, animation: YcdAnimation) -> None:
        expected_count = max((len(sequence.anim_sequences) for sequence in animation.sequences), default=0)
        if expected_count <= 0:
            animation.bone_ids = []
            animation.bone_id_count = 0
            animation.sequence_count = len(animation.sequences)
            return

        resolved_bone_ids: list[YcdAnimationBoneId] = []
        existing_bone_ids = list(animation.bone_ids)

        for index in range(expected_count):
            resolved = existing_bone_ids[index] if index < len(existing_bone_ids) else None
            for sequence in animation.sequences:
                if index >= len(sequence.anim_sequences):
                    continue
                anim_sequence = sequence.anim_sequences[index]
                bone_id = anim_sequence.bone_id
                if bone_id is None:
                    if resolved is not None:
                        anim_sequence.bone_id = resolved
                    continue
                if resolved is None:
                    resolved = YcdAnimationBoneId(
                        bone_id=int(bone_id.bone_id),
                        track=int(bone_id.track),
                        format=int(bone_id.format),
                    )
                elif (
                    int(resolved.bone_id) != int(bone_id.bone_id)
                    or int(resolved.track) != int(bone_id.track)
                    or int(resolved.format) != int(bone_id.format)
                ):
                    raise ValueError(
                        f"YCD animation '{animation.name or animation.hash.uint:#x}' has inconsistent bone binding at sequence index {index}"
                    )
                anim_sequence.bone_id = resolved
            if resolved is None:
                raise ValueError(
                    f"YCD animation '{animation.name or animation.hash.uint:#x}' is missing bone binding metadata for sequence index {index}"
                )
            resolved_bone_ids.append(resolved)

        animation.bone_ids = resolved_bone_ids
        for bone_id in animation.bone_ids:
            bone_id.format = get_ycd_track_format(bone_id.track)
        animation.bone_id_count = len(resolved_bone_ids)
        animation.sequence_count = len(animation.sequences)

    def write_string(self, value: str) -> int:
        key = str(value)
        cached = self.string_offsets.get(key)
        if cached is not None:
            return cached
        offset = self.writer.c_string(key, encoding="utf-8", alignment=8)
        self.string_offsets[key] = offset
        return offset

    def write_pointer_array(self, offsets: list[int], *, alignment: int = 16) -> int:
        if not offsets:
            return 0
        array_offset = self.writer.alloc(len(offsets) * 8, alignment)
        for index, item_offset in enumerate(offsets):
            self.writer.pack_into("Q", array_offset + (index * 8), self.vptr(item_offset) if item_offset else 0)
        return array_offset

    def write_sequence(self, sequence: YcdSequence) -> int:
        key = self._identity(sequence)
        cached = self.sequence_offsets.get(key)
        if cached is not None:
            return cached
        raw_data = build_sequence_data(sequence)
        offset = self.writer.alloc(0x20 + len(raw_data), 16, relocate_pointers=False)
        self.writer.pack_into(
            "IIIIIHHHHHBB",
            offset,
            _resolve_hash(sequence.hash).uint,
            len(raw_data),
            int(sequence.unused_08h),
            int(sequence.frame_offset),
            int(sequence.root_motion_refs_offset),
            int(sequence.unused_14h),
            int(sequence.num_frames),
            int(sequence.frame_length),
            int(sequence.indirect_quantize_float_num_ints),
            int(sequence.quantize_float_value_bits),
            int(sequence.chunk_size),
            int(sequence.root_motion_ref_counts),
        )
        self.writer.write(offset + 0x20, raw_data)
        self.sequence_offsets[key] = offset
        return offset

    def write_animation(self, animation: YcdAnimation) -> int:
        key = self._identity(animation)
        cached = self.animation_offsets.get(key)
        if cached is not None:
            return cached

        self._synchronize_animation_bone_ids(animation)
        sequence_offsets = [self.write_sequence(sequence) for sequence in animation.sequences]
        sequences_array_offset = self.write_pointer_array(sequence_offsets)

        bone_ids_offset = 0
        if animation.bone_ids:
            bone_ids_offset = self.writer.alloc(len(animation.bone_ids) * 4, 16, relocate_pointers=False)
            for index, bone_id in enumerate(animation.bone_ids):
                entry_offset = bone_ids_offset + (index * 4)
                self.writer.pack_into(
                    "HBB",
                    entry_offset,
                    int(bone_id.bone_id),
                    int(bone_id.format),
                    int(bone_id.track),
                )

        offset = self.writer.alloc(0x60, 16)
        max_seq_block_length = max((0x20 + len(sequence.raw_data) for sequence in animation.sequences), default=0)
        animation_hash = _resolve_hash(animation.hash, fallback_text=animation.name)
        self.writer.pack_into(
            "IIIIBBHHHfIIIIIIIII",
            offset,
            int(animation.vft),
            1,
            0,
            0,
            int(animation.flags),
            1,
            0,
            int(animation.frames),
            int(animation.sequence_frame_limit),
            float(animation.duration),
            animation.raw_unknown_hash.uint,
            0,
            0,
            0,
            0,
            0,
            0,
            int(animation.max_seq_block_length or max_seq_block_length),
            int(self.animation_usage_counts.get(animation_hash.uint, animation.usage_count)),
        )
        self.writer.pack_into(
            "QHHI",
            offset + 0x40,
            self.vptr(sequences_array_offset) if sequences_array_offset else 0,
            len(animation.sequences),
            len(animation.sequences),
            0,
        )
        self.writer.pack_into(
            "QHHI",
            offset + 0x50,
            self.vptr(bone_ids_offset) if bone_ids_offset else 0,
            len(animation.bone_ids),
            len(animation.bone_ids),
            0,
        )
        self.animation_offsets[key] = offset
        return offset

    def write_clip_property_attribute(self, attribute: YcdClipPropertyAttribute) -> int:
        offset = self.writer.alloc(
            0x30,
            16,
            relocate_pointers=attribute.attribute_type is YcdClipPropertyAttributeType.STRING,
        )
        self.writer.pack_into(
            "IIBBHIIIII",
            offset,
            int(attribute.vft),
            int(attribute.unknown_04h),
            int(attribute.attribute_type),
            int(attribute.unknown_09h),
            int(attribute.unknown_0ah),
            int(attribute.unknown_0ch),
            int(attribute.unknown_10h),
            int(attribute.unknown_14h),
            _resolve_hash(attribute.name_hash).uint,
            int(attribute.unknown_1ch),
        )
        value_offset = offset + 0x20
        attr_type = attribute.attribute_type
        if attr_type is YcdClipPropertyAttributeType.FLOAT:
            self.writer.pack_into("fIII", value_offset, float(attribute.value), 0, 0, 0)
        elif attr_type is YcdClipPropertyAttributeType.INT:
            self.writer.pack_into("iIII", value_offset, int(attribute.value), 0, 0, 0)
        elif attr_type is YcdClipPropertyAttributeType.BOOL:
            self.writer.pack_into("IIII", value_offset, 1 if bool(attribute.value) else 0, 0, 0, 0)
        elif attr_type is YcdClipPropertyAttributeType.STRING:
            text = str(attribute.value)
            string_offset = self.write_string(text) if text else 0
            self.writer.pack_into("QHHI", value_offset, self.vptr(string_offset) if string_offset else 0, len(text), len(text) + 1 if text else 0, 0)
        elif attr_type is YcdClipPropertyAttributeType.VECTOR3:
            x, y, z = tuple(float(component) for component in attribute.value)
            extra = 0.0 if attribute.extra is None else float(attribute.extra)
            self.writer.pack_into("ffff", value_offset, x, y, z, extra)
        elif attr_type is YcdClipPropertyAttributeType.VECTOR4:
            x, y, z, w = tuple(float(component) for component in attribute.value)
            self.writer.pack_into("ffff", value_offset, x, y, z, w)
        elif attr_type is YcdClipPropertyAttributeType.HASH_STRING:
            self.writer.pack_into("IIII", value_offset, _resolve_hash(attribute.value).uint, 0, 0, 0)
        else:  # pragma: no cover - guarded by current enum
            raise ValueError(f"Unsupported YCD clip property attribute type: {attr_type!r}")
        return offset

    def write_clip_property(self, prop: YcdClipProperty) -> int:
        key = self._identity(prop)
        cached = self.property_offsets.get(key)
        if cached is not None:
            return cached
        attribute_offsets = [self.write_clip_property_attribute(attribute) for attribute in prop.attributes]
        attributes_array_offset = self.write_pointer_array(attribute_offsets)
        offset = self.writer.alloc(0x40, 16)
        self.writer.pack_into(
            "IIIIIIIIQHHIIIII",
            offset,
            int(prop.vft),
            int(prop.unknown_04h),
            int(prop.unknown_08h),
            int(prop.unknown_0ch),
            int(prop.unknown_10h),
            int(prop.unknown_14h),
            _resolve_hash(prop.name_hash).uint,
            int(prop.unknown_1ch),
            self.vptr(attributes_array_offset) if attributes_array_offset else 0,
            len(prop.attributes),
            len(prop.attributes),
            int(prop.unknown_2ch),
            int(prop.unknown_30h),
            int(prop.unknown_34h),
            _resolve_hash(prop.unknown_hash).uint,
            int(prop.unknown_3ch),
        )
        self.property_offsets[key] = offset
        return offset

    def write_clip_property_map(self, properties: list[YcdClipProperty], *, reserved_0ch: int = _DEFAULT_PROPERTY_MAP_UNKNOWN_0CH) -> int:
        if not properties:
            return 0
        property_offsets = {self._identity(prop): self.write_clip_property(prop) for prop in properties}
        capacity = _get_num_hash_buckets(len(properties))
        buckets: list[list[YcdClipProperty]] = [[] for _ in range(capacity)]
        for prop in properties:
            buckets[_resolve_hash(prop.name_hash).uint % capacity].append(prop)

        bucket_head_offsets: list[int] = []
        for bucket in buckets:
            next_offset = 0
            for prop in reversed(bucket):
                entry_offset = self.writer.alloc(0x20, 16)
                self.writer.pack_into(
                    "IIQQII",
                    entry_offset,
                    _resolve_hash(prop.name_hash).uint,
                    0,
                    self.vptr(property_offsets[self._identity(prop)]),
                    self.vptr(next_offset) if next_offset else 0,
                    0,
                    0,
                )
                next_offset = entry_offset
            bucket_head_offsets.append(next_offset)

        buckets_array_offset = self.write_pointer_array(bucket_head_offsets)
        offset = self.writer.alloc(0x10, 16)
        self.writer.pack_into(
            "QHHI",
            offset,
            self.vptr(buckets_array_offset) if buckets_array_offset else 0,
            capacity,
            len(properties),
            int(reserved_0ch),
        )
        return offset

    def write_clip_tag(self, tag: YcdClipTag) -> int:
        key = self._identity(tag)
        cached = self.tag_offsets.get(key)
        if cached is not None:
            return cached
        attribute_offsets = [self.write_clip_property_attribute(attribute) for attribute in tag.attributes]
        attributes_array_offset = self.write_pointer_array(attribute_offsets)
        nested_tag_list_offset = self.write_clip_tag_list(
            tag.tags,
            has_block_tag=tag.has_block_tag,
            reserved_0ch=tag.tag_list_reserved_0ch,
            reserved_14h=tag.tag_list_reserved_14h,
            reserved_18h=tag.tag_list_reserved_18h,
            reserved_1ch=tag.tag_list_reserved_1ch,
        )
        offset = self.writer.alloc(0x50, 16)
        self.writer.pack_into(
            "IIIIIIIIQHHIIIIIffQ",
            offset,
            int(tag.vft),
            int(tag.unknown_04h),
            int(tag.unknown_08h),
            int(tag.unknown_0ch),
            int(tag.unknown_10h),
            int(tag.unknown_14h),
            _resolve_hash(tag.name_hash).uint,
            int(tag.unknown_1ch),
            self.vptr(attributes_array_offset) if attributes_array_offset else 0,
            len(tag.attributes),
            len(tag.attributes),
            int(tag.unknown_2ch),
            int(tag.unknown_30h),
            int(tag.unknown_34h),
            _resolve_hash(tag.unknown_hash).uint,
            int(tag.unknown_3ch),
            float(tag.start_phase),
            float(tag.end_phase),
            self.vptr(nested_tag_list_offset) if nested_tag_list_offset else 0,
        )
        self.tag_offsets[key] = offset
        return offset

    def write_clip_tag_list(
        self,
        tags: list[YcdClipTag],
        *,
        has_block_tag: bool | None = None,
        reserved_0ch: int = 0,
        reserved_14h: int = 0,
        reserved_18h: int = 0,
        reserved_1ch: int = 0,
    ) -> int:
        if not tags:
            return 0
        tag_offsets = [self.write_clip_tag(tag) for tag in tags]
        tags_array_offset = self.write_pointer_array(tag_offsets)
        if has_block_tag is None:
            has_block_tag = any(_resolve_hash(tag.name_hash).uint == MetaHash("block").uint for tag in tags)
        offset = self.writer.alloc(0x20, 16)
        self.writer.pack_into(
            "QHHIIIII",
            offset,
            self.vptr(tags_array_offset) if tags_array_offset else 0,
            len(tags),
            len(tags),
            int(reserved_0ch),
            1 if has_block_tag else 0,
            int(reserved_14h),
            int(reserved_18h),
            int(reserved_1ch),
        )
        return offset

    def write_clip_animation_entry_array(self, entries: list[YcdClipAnimationEntry]) -> int:
        if not entries:
            return 0
        offset = self.writer.alloc(len(entries) * 24, 16)
        for index, entry in enumerate(entries):
            animation = entry.animation
            animation_offset = self.write_animation(animation) if animation is not None else 0
            entry_offset = offset + (index * 24)
            self.writer.pack_into(
                "fffIQ",
                entry_offset,
                float(entry.start_time),
                float(entry.end_time),
                float(entry.rate),
                int(entry.alignment_padding_0ch),
                self.vptr(animation_offset) if animation_offset else 0,
            )
        return offset

    def write_clip(self, clip: YcdClip) -> int:
        key = self._identity(clip)
        cached = self.clip_offsets.get(key)
        if cached is not None:
            return cached
        name = str(clip.name or "")
        tag_list_offset = self.write_clip_tag_list(
            clip.tags,
            has_block_tag=clip.has_block_tag,
            reserved_0ch=clip.tag_list_reserved_0ch,
            reserved_14h=clip.tag_list_reserved_14h,
            reserved_18h=clip.tag_list_reserved_18h,
            reserved_1ch=clip.tag_list_reserved_1ch,
        )
        property_map_offset = self.write_clip_property_map(clip.properties, reserved_0ch=clip.property_map_reserved_0ch)
        name_offset = self.write_string(name) if name else 0

        offset = self.writer.alloc(0x70, 16)
        self.writer.pack_into(
            "IIIIIIQHHIQIIQQII",
            offset,
            int(clip.vft),
            int(clip.unknown_04h),
            int(clip.unknown_08h),
            int(clip.unknown_0ch),
            int(clip.clip_type),
            int(clip.unknown_14h),
            self.vptr(name_offset) if name_offset else 0,
            len(name),
            len(name) + 1 if name else 0,
            int(clip.unknown_24h),
            DAT_VIRTUAL_BASE,
            int(clip.flags),
            int(clip.reserved_34h),
            self.vptr(tag_list_offset) if tag_list_offset else 0,
            self.vptr(property_map_offset) if property_map_offset else 0,
            int(clip.unknown_48h),
            int(clip.unknown_4ch),
        )

        if isinstance(clip, YcdClipAnimation):
            animation_offset = self.write_animation(clip.animation) if clip.animation is not None else 0
            self.writer.pack_into(
                "QfffIII",
                offset + 0x50,
                self.vptr(animation_offset) if animation_offset else 0,
                float(clip.start_time),
                float(clip.end_time),
                float(clip.rate),
                int(clip.reserved_64h),
                int(clip.reserved_68h),
                int(clip.reserved_6ch),
            )
        elif isinstance(clip, YcdClipAnimationList):
            entries_offset = self.write_clip_animation_entry_array(clip.animations)
            self.writer.pack_into(
                "QHHIfIII",
                offset + 0x50,
                self.vptr(entries_offset) if entries_offset else 0,
                len(clip.animations),
                len(clip.animations),
                int(clip.unknown_5ch),
                float(clip.total_duration),
                (1 if clip.parallel else 0) | (int.from_bytes(bytes(clip.parallel_padding[:3]).ljust(3, b"\x00"), "little") << 8),
                int(clip.reserved_68h),
                int(clip.reserved_6ch),
            )
        self.clip_offsets[key] = offset
        return offset

    def write_animation_map(self, animations: list[YcdAnimation], bucket_capacity: int) -> int:
        buckets: list[list[YcdAnimation]] = [[] for _ in range(bucket_capacity)]
        for animation in animations:
            animation_hash = _resolve_hash(animation.hash, fallback_text=animation.name)
            buckets[animation_hash.uint % bucket_capacity].append(animation)

        bucket_head_offsets: list[int] = []
        for bucket in buckets:
            next_offset = 0
            for animation in reversed(bucket):
                animation_offset = self.write_animation(animation)
                entry_offset = self.writer.alloc(0x20, 16)
                self.writer.pack_into(
                    "IIQQII",
                    entry_offset,
                    _resolve_hash(animation.hash, fallback_text=animation.name).uint,
                    0,
                    self.vptr(animation_offset),
                    self.vptr(next_offset) if next_offset else 0,
                    0,
                    0,
                )
                next_offset = entry_offset
            bucket_head_offsets.append(next_offset)

        buckets_array_offset = self.write_pointer_array(bucket_head_offsets)
        offset = self.writer.alloc(0x30, 16)
        self.writer.pack_into(
            "IIIIIIQHHIII",
            offset,
            _ANIMATION_MAP_VFT,
            1,
            0,
            0,
            0,
            0,
            self.vptr(buckets_array_offset) if buckets_array_offset else 0,
            bucket_capacity,
            len(animations),
            0x01000000,
            1,
            0,
        )
        return offset

    def write_clip_map_buckets(self, clips: list[YcdClip], bucket_capacity: int) -> int:
        buckets: list[list[YcdClip]] = [[] for _ in range(bucket_capacity)]
        for clip in clips:
            clip_hash = _resolve_clip_hash(clip)
            buckets[clip_hash.uint % bucket_capacity].append(clip)

        bucket_head_offsets: list[int] = []
        for bucket in buckets:
            next_offset = 0
            for clip in reversed(bucket):
                clip_offset = self.write_clip(clip)
                entry_offset = self.writer.alloc(0x20, 16)
                self.writer.pack_into(
                    "IIQQII",
                    entry_offset,
                    _resolve_clip_hash(clip).uint,
                    0,
                    self.vptr(clip_offset),
                    self.vptr(next_offset) if next_offset else 0,
                    0,
                    0,
                )
                next_offset = entry_offset
            bucket_head_offsets.append(next_offset)
        return self.write_pointer_array(bucket_head_offsets)

    def write_pages_info(self, page_counts: tuple[int, int]) -> int:
        total_page_count = int(page_counts[0]) + int(page_counts[1])
        offset = self.writer.alloc(0x10 + (total_page_count * 8), 16, relocate_pointers=False)
        self.writer.pack_into("IIBBHI", offset, 0, 0, int(page_counts[0]) & 0xFF, int(page_counts[1]) & 0xFF, 0, 0)
        return offset

    def build_system_data(self, page_counts: tuple[int, int] = (0, 0)) -> tuple[bytes, list[ResourceBlockSpan]]:
        clips = list(self.ycd.clips)
        animations = list(self.ycd.animations)
        clip_bucket_capacity = self.ycd.clip_bucket_capacity or _get_num_hash_buckets(len(clips))
        animation_bucket_capacity = self.ycd.animation_bucket_capacity or _get_num_hash_buckets(len(animations))

        animation_map_offset = self.write_animation_map(animations, animation_bucket_capacity)
        clip_map_offset = self.write_clip_map_buckets(clips, clip_bucket_capacity)
        pages_info_offset = self.write_pages_info(page_counts)

        self.writer.pack_into("IIQ", 0x00, _RESOURCE_FILE_VFT, 1, self.vptr(pages_info_offset))
        self.writer.pack_into(
            "IIQIIQHHIII",
            0x10,
            0,
            0,
            self.vptr(animation_map_offset),
            _DEFAULT_ROOT_UNKNOWN_20H,
            0,
            self.vptr(clip_map_offset) if clip_map_offset else 0,
            clip_bucket_capacity,
            len(clips),
            _DEFAULT_ROOT_UNKNOWN_34H,
            0,
            0,
        )
        return self.writer.finish(), self.writer.block_spans


def build_ycd_bytes(ycd: Ycd) -> bytes:
    source = ycd.build()
    page_counts = (0, 0)
    system_data = b""
    system_flags = None
    graphics_flags = None
    for _ in range(16):
        raw_system_data, system_blocks = _YcdWriter(source).build_system_data(page_counts)
        system_data, _, system_flags, graphics_flags = layout_resource_sections(
            raw_system_data,
            system_blocks,
            version=ycd.header.version,
        )
        next_counts = (get_resource_total_page_count(system_flags), get_resource_total_page_count(graphics_flags))
        if next_counts == page_counts:
            break
        page_counts = next_counts
    else:
        raise RuntimeError("YCD writer page-info sizing did not converge")
    assert system_flags is not None
    assert graphics_flags is not None
    return build_rsc7(system_data, version=ycd.header.version, system_flags=system_flags, graphics_flags=graphics_flags)


def save_ycd(ycd: Ycd, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_ycd_bytes(ycd))
    return target


__all__ = ["build_ycd_bytes", "save_ycd"]
