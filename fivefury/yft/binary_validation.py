from __future__ import annotations

import struct

from ..common import ByteSource, read_source_bytes
from ..resource import (
    RSC7_VIRTUAL_BASE,
    ResourceChunk,
    ResourceHeader,
    parse_rsc7,
)
from ..ydr.fixups import audit_legacy_fragment_drawable_fixups
from .constants import (
    DRAWABLE_ARRAY_COUNT_OFFSET,
    FRAGMENT_ROOT_SIZE,
)
from .resource_headers import (
    FRAG_PHYS_ARCHETYPE_DAMP_VFT,
    FRAG_PHYS_TRANSFORMS_VFT,
    FRAG_PHYSICS_LOD_VFT,
    FRAG_TYPE_CHILD_VFT,
    FRAGMENT_TYPE_VFT,
    PH_JOINT_1DOF_TYPE_VFT,
    PH_JOINT_3DOF_TYPE_VFT,
    RESOURCE_STATE,
)
from .validation import (
    YftValidationIssue,
    YftValidationSeverity,
)

_PHYSICS_LOD_SIZE = 0x130
_PHYSICS_GROUP_SIZE = 0xB0
_PHYSICS_CHILD_SIZE = 0x100
_ARCHETYPE_DAMP_SIZE = 0xE0
_ARTICULATED_BODY_SIZE = 0xA4
_JOINT_SIZES = {0: 0xB0, 1: 0xF0}
_JOINT_VFTS = {0: PH_JOINT_1DOF_TYPE_VFT, 1: PH_JOINT_3DOF_TYPE_VFT}


class _YftBinaryValidator:
    def __init__(
        self,
        header: ResourceHeader,
        system_data: bytes,
        graphics_data: bytes,
    ):
        self.header = header
        self.chunks = header.chunks
        self.system_data = system_data
        self.graphics_data = graphics_data
        self.issues: list[YftValidationIssue] = []
        self._validated_drawables: set[int] = set()
        self._common_drawable: int = 0

    def error(self, path: str, message: str) -> None:
        self.issues.append(
            YftValidationIssue(YftValidationSeverity.ERROR, path, message)
        )

    def _section_data(self, chunk: ResourceChunk) -> bytes:
        return self.system_data if chunk.section == "system" else self.graphics_data

    def pointer(
        self,
        pointer: int,
        path: str,
        *,
        size: int = 1,
        section: str | None = "system",
        nullable: bool = True,
    ) -> int | None:
        if not pointer:
            if not nullable:
                self.error(path, "required resource pointer is null")
            return None
        chunk = next(
            (candidate for candidate in self.chunks if candidate.contains(pointer)),
            None,
        )
        if chunk is None:
            self.error(
                path,
                f"0x{pointer:08X} is outside the virtual and physical resource chunks",
            )
            return None
        if section is not None and chunk.section != section:
            self.error(path, f"points into {chunk.section} data instead of {section} data")
            return None
        offset = chunk.section_offset + pointer - chunk.address
        data = self._section_data(chunk)
        if offset < 0 or offset + size > len(data):
            self.error(path, f"requires 0x{size:X} bytes beyond the decoded resource data")
            return None
        return offset

    def u8(self, offset: int) -> int:
        return self.system_data[offset]

    def u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.system_data, offset)[0]

    def u16(self, offset: int) -> int:
        return struct.unpack_from("<H", self.system_data, offset)[0]

    def u64(self, offset: int) -> int:
        return struct.unpack_from("<Q", self.system_data, offset)[0]

    def class_header(
        self,
        pointer: int,
        path: str,
        *,
        size: int,
        expected_vft: int | tuple[int, ...] | None,
        nullable: bool = False,
    ) -> int | None:
        offset = self.pointer(pointer, path, size=size, nullable=nullable)
        if offset is None:
            return None
        vft, state = struct.unpack_from("<II", self.system_data, offset)
        if not vft:
            self.error(f"{path}.vft", "runtime VFT is zero")
        elif expected_vft is not None:
            expected = (
                expected_vft
                if isinstance(expected_vft, tuple)
                else (expected_vft,)
            )
            if vft not in expected:
                choices = " or ".join(f"0x{value:08X}" for value in expected)
                self.error(
                    f"{path}.vft",
                    f"expected {choices}, found 0x{vft:08X}",
                )
        if state != RESOURCE_STATE:
            self.error(
                f"{path}.resource_state",
                f"expected {RESOURCE_STATE}, found {state}",
            )
        return offset

    def pointer_array(
        self,
        pointer: int,
        count: int,
        path: str,
        *,
        nullable: bool | None = None,
    ) -> tuple[int, ...]:
        if nullable is None:
            nullable = count == 0
        offset = self.pointer(
            pointer,
            path,
            size=count * 8,
            nullable=nullable,
        )
        if offset is None or count == 0:
            return ()
        return struct.unpack_from(f"<{count}Q", self.system_data, offset)

    def string(self, pointer: int, path: str) -> None:
        offset = self.pointer(pointer, path)
        if offset is None:
            return
        if self.system_data.find(b"\0", offset) < 0:
            self.error(path, "string is not null terminated")

    def validate_drawable(
        self,
        pointer: int,
        path: str,
        *,
        require_shader_group: bool = True,
        inherited_shader_count: int | None = None,
    ) -> None:
        if (
            inherited_shader_count is not None
            and pointer != self._common_drawable
        ):
            root = self.pointer(pointer, path, size=0x150, nullable=False)
            if root is not None:
                shader_group = self.u64(root + 0x10)
                if shader_group:
                    self.error(
                        f"{path}.shader_group",
                        "secondary fragment drawables must inherit the common "
                        "drawable shader group; the private pointer must be null",
                    )
                self.validate_inherited_shader_mappings(
                    root,
                    path,
                    inherited_shader_count,
                )
            require_shader_group = False
        if pointer in self._validated_drawables:
            return
        self._validated_drawables.add(pointer)
        audit_legacy_fragment_drawable_fixups(
            self,
            pointer,
            path,
            require_shader_group=require_shader_group,
        )

    def drawable_shader_count(self, pointer: int, path: str) -> int:
        root = self.pointer(pointer, path, size=0x20, nullable=False)
        if root is None:
            return 0
        shader_group = self.u64(root + 0x10)
        shader_group_offset = self.pointer(
            shader_group,
            f"{path}.shader_group",
            size=0x1A,
            nullable=True,
        )
        if shader_group_offset is None:
            return 0
        return self.u16(shader_group_offset + 0x18)

    def validate_inherited_shader_mappings(
        self,
        root: int,
        path: str,
        shader_count: int,
    ) -> None:
        for field_offset, label in (
            (0x50, "high"),
            (0x58, "medium"),
            (0x60, "low"),
            (0x68, "very_low"),
        ):
            lod_pointer = self.u64(root + field_offset)
            if not lod_pointer:
                continue
            lod = self.pointer(
                lod_pointer,
                f"{path}.lods.{label}",
                size=0x10,
                nullable=False,
            )
            if lod is None:
                continue
            model_count = self.u16(lod + 0x08)
            models = self.pointer_array(
                self.u64(lod),
                model_count,
                f"{path}.lods.{label}.models",
            )
            for model_index, model_pointer in enumerate(models):
                model_path = f"{path}.lods.{label}.models[{model_index}]"
                model = self.pointer(
                    model_pointer,
                    model_path,
                    size=0x30,
                    nullable=False,
                )
                if model is None:
                    continue
                geometry_count = self.u16(model + 0x10)
                mapping = self.pointer(
                    self.u64(model + 0x20),
                    f"{model_path}.shader_mapping",
                    size=geometry_count * 2,
                    nullable=geometry_count == 0,
                )
                if mapping is None:
                    continue
                for geometry_index in range(geometry_count):
                    shader_index = self.u16(mapping + geometry_index * 2)
                    if shader_index >= shader_count:
                        self.error(
                            f"{model_path}.shader_mapping[{geometry_index}]",
                            f"shader index {shader_index} is outside the common "
                            f"shader group with {shader_count} entries",
                        )

    def validate_child(
        self,
        pointer: int,
        path: str,
        *,
        inherited_shader_count: int,
    ) -> None:
        offset = self.class_header(
            pointer,
            path,
            size=_PHYSICS_CHILD_SIZE,
            expected_vft=FRAG_TYPE_CHILD_VFT,
        )
        if offset is None:
            return
        for field_offset, label in (
            (0xA0, "undamaged_entity"),
            (0xA8, "damaged_entity"),
        ):
            entity = self.u64(offset + field_offset)
            if entity:
                self.validate_drawable(
                    entity,
                    f"{path}.{label}",
                    require_shader_group=False,
                    inherited_shader_count=inherited_shader_count,
                )
        for field_offset, label in (
            (0xB0, "continuous_event_set"),
            (0xB8, "collision_event_set"),
            (0xC0, "break_event_set"),
            (0xC8, "break_from_root_event_set"),
            (0xD0, "collision_event_player"),
            (0xD8, "break_event_player"),
            (0xE0, "break_from_root_event_player"),
        ):
            event_pointer = self.u64(offset + field_offset)
            if event_pointer:
                self.pointer(event_pointer, f"{path}.{label}")

    def validate_damp(self, pointer: int, path: str) -> None:
        offset = self.class_header(
            pointer,
            path,
            size=_ARCHETYPE_DAMP_SIZE,
            expected_vft=FRAG_PHYS_ARCHETYPE_DAMP_VFT,
        )
        if offset is None:
            return
        filename = self.u64(offset + 0x18)
        if filename:
            self.string(filename, f"{path}.filename")
        self.pointer(
            self.u64(offset + 0x20),
            f"{path}.bound",
            nullable=False,
        )

    def validate_body(self, pointer: int, path: str, num_children: int) -> None:
        offset = self.class_header(
            pointer,
            path,
            size=_ARTICULATED_BODY_SIZE,
            expected_vft=None,
        )
        if offset is None:
            return
        num_links = self.u8(offset + 0x88)
        num_joints = self.u8(offset + 0x89)
        if num_links > 23:
            self.error(f"{path}.num_links", f"{num_links} exceeds the native limit of 23")
        if num_joints > 22:
            self.error(
                f"{path}.num_joints",
                f"{num_joints} exceeds the native limit of 22",
            )
        if num_children and num_links not in (0, num_children):
            self.error(
                f"{path}.num_links",
                f"{num_links} links do not match {num_children} physics children",
            )
        joint_pointers = self.pointer_array(
            self.u64(offset + 0x78),
            num_joints,
            f"{path}.joints",
        )
        for index, joint_pointer in enumerate(joint_pointers):
            joint_type = self.u8(offset + 0x8A + index)
            joint_size = _JOINT_SIZES.get(joint_type)
            if joint_size is None:
                self.error(
                    f"{path}.joints[{index}]",
                    f"unsupported joint type {joint_type}",
                )
                continue
            self.class_header(
                joint_pointer,
                f"{path}.joints[{index}]",
                size=joint_size,
                expected_vft=_JOINT_VFTS[joint_type],
            )
        inertia = self.u64(offset + 0x80)
        if inertia:
            self.pointer(
                inertia,
                f"{path}.resourced_ang_inertia",
                size=num_links * 16,
            )

    def validate_transforms(self, pointer: int, path: str, num_children: int) -> None:
        offset = self.class_header(
            pointer,
            path,
            size=0x20,
            expected_vft=FRAG_PHYS_TRANSFORMS_VFT,
        )
        if offset is None:
            return
        count = self.u32(offset + 0x10)
        self.pointer(pointer, path, size=0x20 + count * 64, nullable=False)
        if count != num_children:
            self.error(
                f"{path}.count",
                f"{count} transforms do not match {num_children} physics children",
            )

    def validate_lod(
        self,
        pointer: int,
        path: str,
        *,
        inherited_shader_count: int,
    ) -> None:
        offset = self.class_header(
            pointer,
            path,
            size=_PHYSICS_LOD_SIZE,
            expected_vft=FRAG_PHYSICS_LOD_VFT,
        )
        if offset is None:
            return
        num_self_collisions = self.u8(offset + 0x118)
        num_groups = self.u8(offset + 0x11A)
        num_children = self.u8(offset + 0x11E)

        body = self.u64(offset + 0x20)
        if body:
            self.validate_body(body, f"{path}.body_type", num_children)
        for field_offset, item_size, label in (
            (0x28, 4, "min_breaking_impulses"),
            (0xF0, 16, "undamaged_ang_inertia"),
            (0xF8, 16, "damaged_ang_inertia"),
        ):
            self.pointer(
                self.u64(offset + field_offset),
                f"{path}.{label}",
                size=num_children * item_size,
                nullable=num_children == 0,
            )

        name_pointers = self.pointer_array(
            self.u64(offset + 0xC0),
            num_groups + 1,
            f"{path}.group_names",
            nullable=False,
        )
        for index, name_pointer in enumerate(name_pointers[:num_groups]):
            self.string(name_pointer, f"{path}.group_names[{index}]")

        groups = self.pointer_array(
            self.u64(offset + 0xC8),
            num_groups,
            f"{path}.groups",
        )
        for index, group in enumerate(groups):
            self.pointer(
                group,
                f"{path}.groups[{index}]",
                size=_PHYSICS_GROUP_SIZE,
                nullable=False,
            )

        children = self.pointer_array(
            self.u64(offset + 0xD0),
            num_children,
            f"{path}.children",
        )
        for index, child in enumerate(children):
            self.validate_child(
                child,
                f"{path}.children[{index}]",
                inherited_shader_count=inherited_shader_count,
            )

        for field_offset, label in (
            (0xD8, "undamaged_damp_archetype"),
            (0xE0, "damaged_damp_archetype"),
        ):
            damp = self.u64(offset + field_offset)
            if damp:
                self.validate_damp(damp, f"{path}.{label}")
        self.pointer(
            self.u64(offset + 0xE8),
            f"{path}.composite_bound",
            nullable=False,
        )

        transforms = self.u64(offset + 0x100)
        if transforms:
            self.validate_transforms(
                transforms,
                f"{path}.link_attachments",
                num_children,
            )
        for field_offset, label in (
            (0x108, "self_collision_a"),
            (0x110, "self_collision_b"),
        ):
            self.pointer(
                self.u64(offset + field_offset),
                f"{path}.{label}",
                size=num_self_collisions,
                nullable=num_self_collisions == 0,
            )

    def validate(self) -> list[YftValidationIssue]:
        root = RSC7_VIRTUAL_BASE
        root_offset = self.class_header(
            root,
            "root",
            size=FRAGMENT_ROOT_SIZE,
            expected_vft=FRAGMENT_TYPE_VFT,
        )
        if root_offset is None:
            return self.issues

        pages_info = self.u64(root_offset + 0x08)
        pages_offset = self.pointer(
            pages_info,
            "root.resource_pages",
            size=0x10,
            nullable=False,
        )
        if pages_offset is not None:
            expected_system = len(
                [chunk for chunk in self.chunks if chunk.section == "system"]
            )
            expected_graphics = len(
                [chunk for chunk in self.chunks if chunk.section == "graphics"]
            )
            actual_system = self.u8(pages_offset + 0x08)
            actual_graphics = self.u8(pages_offset + 0x09)
            if (actual_system, actual_graphics) != (
                expected_system,
                expected_graphics,
            ):
                self.error(
                    "root.resource_pages",
                    "page counts do not match the RSC7 resource map "
                    f"({actual_system}, {actual_graphics}) != "
                    f"({expected_system}, {expected_graphics})",
                )

        common_drawable = self.u64(root_offset + 0x30)
        self._common_drawable = common_drawable
        self.validate_drawable(common_drawable, "root.common_drawable")
        common_shader_count = self.drawable_shader_count(
            common_drawable,
            "root.common_drawable",
        )
        drawable_count = self.u32(root_offset + DRAWABLE_ARRAY_COUNT_OFFSET)
        drawables = self.pointer_array(
            self.u64(root_offset + 0x38),
            drawable_count,
            "root.extra_drawables",
        )
        names = self.pointer_array(
            self.u64(root_offset + 0x40),
            drawable_count,
            "root.extra_drawable_names",
        )
        for index, drawable in enumerate(drawables):
            self.validate_drawable(
                drawable,
                f"root.extra_drawables[{index}]",
                inherited_shader_count=common_shader_count,
            )
        for index, name in enumerate(names):
            self.string(name, f"root.extra_drawable_names[{index}]")

        root_child = self.u64(root_offset + 0x50)
        if root_child:
            self.validate_child(
                root_child,
                "root.child",
                inherited_shader_count=common_shader_count,
            )
        tune_name = self.u64(root_offset + 0x58)
        if tune_name:
            self.string(tune_name, "root.tune_name")

        physics_group = self.u64(root_offset + 0xF0)
        if physics_group:
            group_offset = self.pointer(
                physics_group,
                "root.physics_lod_group",
                size=0x30,
                nullable=False,
            )
            if group_offset is not None:
                for index, label in enumerate(("high", "medium", "low")):
                    lod = self.u64(group_offset + 0x10 + index * 8)
                    if lod:
                        self.validate_lod(
                            lod,
                            f"physics_lods.{label}",
                            inherited_shader_count=common_shader_count,
                        )

        cloth_drawable = self.u64(root_offset + 0xF8)
        if cloth_drawable:
            self.validate_drawable(cloth_drawable, "root.cloth_drawable")
        return self.issues


def validate_yft_bytes(source: ByteSource) -> list[YftValidationIssue]:
    try:
        data = read_source_bytes(source)
        header, payload = parse_rsc7(data)
    except (OSError, ValueError, struct.error) as exc:
        return [
            YftValidationIssue(
                YftValidationSeverity.ERROR,
                "resource",
                str(exc),
            )
        ]
    if len(payload) != header.total_size:
        return [
            YftValidationIssue(
                YftValidationSeverity.ERROR,
                "resource.payload",
                f"decoded size 0x{len(payload):X} does not match "
                f"RSC7 size 0x{header.total_size:X}",
            )
        ]
    system_data = payload[: header.system_size]
    graphics_data = payload[header.system_size :]
    return _YftBinaryValidator(header, system_data, graphics_data).validate()


def assert_valid_yft_bytes(source: ByteSource) -> None:
    errors = [issue for issue in validate_yft_bytes(source) if issue.is_error]
    if errors:
        details = "\n".join(issue.format() for issue in errors)
        raise ValueError(f"Invalid binary YFT:\n{details}")


__all__ = [
    "assert_valid_yft_bytes",
    "validate_yft_bytes",
]
