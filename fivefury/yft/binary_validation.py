from __future__ import annotations

import math
import struct
from pathlib import Path

from ..authoring.diagnostics import DiagnosticSeverity, ValidationReport
from ..bounds import GEN9_BOUND_FILE_VFTS, BoundType
from ..common import ByteSource, read_source_bytes
from ..resource import (
    RSC7_VIRTUAL_BASE,
    ResourceChunk,
    ResourceHeader,
    parse_rsc7,
    resolve_resource_pointer,
)
from ..ydr.fixups import audit_fragment_drawable_fixups
from .bound_profiles import (
    YftPhysicsBoundProfile,
    coerce_yft_physics_bound_profile,
    expected_profile_vft,
)
from .constants import (
    DRAWABLE_ARRAY_COUNT_OFFSET,
    FRAGMENT_ROOT_SIZE,
)
from .geometry import (
    MAX_FRAGMENT_BOUND_MATERIALS,
    MAX_FRAGMENT_BOUND_POLYGONS,
    MAX_FRAGMENT_BOUND_VERTICES,
)
from .resource_headers import RESOURCE_STATE, yft_runtime_headers

_PHYSICS_LOD_SIZE = 0x130
_PHYSICS_GROUP_SIZE = 0xB0
_PHYSICS_CHILD_SIZE = 0x100
_ARCHETYPE_DAMP_SIZE = 0xE0
_ARTICULATED_BODY_SIZE = 0xA4
_JOINT_SIZES = {0: 0xB0, 1: 0xF0}
_BOUND_BASE_SIZE = 0x70
_BOUND_COMPOSITE_SIZE = 0xB0
_BOUND_GEOMETRY_SIZE = 0x130
_BOUND_BVH_SIZE = 0x150


class _YftBinaryValidator:
    def __init__(
        self,
        header: ResourceHeader,
        system_data: bytes,
        graphics_data: bytes,
        *,
        profile: YftPhysicsBoundProfile,
    ):
        self.header = header
        self.chunks = header.chunks
        self.system_data = system_data
        self.graphics_data = graphics_data
        self.profile = profile
        self.runtime_headers = yft_runtime_headers(header.version)
        self.report = ValidationReport()
        self._validated_drawables: set[int] = set()
        self._common_drawable: int = 0

    def error(self, path: str, message: str, *, code: str) -> None:
        self.report.issue(
            code,
            message,
            severity=DiagnosticSeverity.ERROR,
            path=path,
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
                self.error(
                    path,
                    "required resource pointer is null",
                    code="yft.binary.pointer.required_resource_pointer_null",
                )
            return None
        try:
            chunk = resolve_resource_pointer(
                self.header,
                pointer,
                size=size,
                section=section,
                nullable=nullable,
            )
        except ValueError as exc:
            self.error(path, str(exc), code="yft.binary.pointer.invalid")
            return None
        assert chunk is not None
        offset = chunk.section_offset + pointer - chunk.address
        data = self._section_data(chunk)
        if offset < 0 or offset + size > len(data):
            self.error(
                path,
                f"requires 0x{size:X} bytes beyond the decoded resource data",
                code="yft.binary.pointer.requires_0x_x_bytes_beyond_decoded_resource_data",
            )
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
        # Runtime class addresses vary between GTA V executable families.
        # Profile-specific bound VFTs are checked separately and exactly.
        if not vft:
            self.error(
                f"{path}.vft",
                "runtime VFT is zero",
                code="yft.binary.class_header.runtime_vft_zero",
            )
        if state != RESOURCE_STATE:
            self.error(
                f"{path}.resource_state",
                f"expected {RESOURCE_STATE}, found {state}",
                code="yft.binary.class_header.expected_found",
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
            self.error(
                path,
                "string is not null terminated",
                code="yft.binary.string.string_not_null_terminated",
            )

    def validate_drawable(
        self,
        pointer: int,
        path: str,
        *,
        require_shader_group: bool = True,
        inherited_shader_count: int | None = None,
    ) -> None:
        if inherited_shader_count is not None and pointer != self._common_drawable:
            root = self.pointer(pointer, path, size=0x150, nullable=False)
            if root is not None:
                shader_group = self.u64(root + 0x10)
                if shader_group:
                    self.error(
                        f"{path}.shader_group",
                        "secondary fragment drawables must inherit the common "
                        "drawable shader group; the private pointer must be null",
                        code="yft.binary.drawable.secondary_fragment_drawables_must_inherit_common_drawable_shader_group",
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
        audit_fragment_drawable_fixups(
            self,
            pointer,
            path,
            require_shader_group=require_shader_group,
            runtime_headers=self.runtime_headers.drawable,
            enhanced=self.runtime_headers.enhanced,
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
                            code="yft.binary.inherited_shader_mappings.shader_index_outside_common_shader_group_entries",
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
            expected_vft=self.runtime_headers.physics_child,
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
        ):
            event_pointer = self.u64(offset + field_offset)
            if event_pointer:
                self.validate_event_set(event_pointer, f"{path}.{label}")
        for field_offset, label in (
            (0xD0, "collision_event_player"),
            (0xD8, "break_event_player"),
            (0xE0, "break_from_root_event_player"),
        ):
            event_pointer = self.u64(offset + field_offset)
            if event_pointer:
                self.pointer(event_pointer, f"{path}.{label}")

    def validate_event_set(self, pointer: int, path: str) -> None:
        offset = self.class_header(
            pointer,
            path,
            size=0x30,
            expected_vft=self.runtime_headers.event_set,
        )
        if offset is None:
            return
        count = self.u16(offset + 0x10)
        capacity = self.u16(offset + 0x12)
        if count > capacity:
            self.error(
                f"{path}.instances",
                f"count {count} exceeds capacity {capacity}",
                code="yft.binary.event_set.count_exceeds_capacity",
            )
        instances = self.pointer_array(
            self.u64(offset + 0x08),
            count,
            f"{path}.instances",
        )
        for index, instance in enumerate(instances):
            self.pointer(
                instance,
                f"{path}.instances[{index}]",
                nullable=False,
            )

    def validate_damp(self, pointer: int, path: str) -> int:
        offset = self.class_header(
            pointer,
            path,
            size=_ARCHETYPE_DAMP_SIZE,
            expected_vft=self.runtime_headers.damp_archetype,
        )
        if offset is None:
            return 0
        filename = self.u64(offset + 0x18)
        if filename:
            self.string(filename, f"{path}.filename")
        bound = self.u64(offset + 0x20)
        self.pointer(
            bound,
            f"{path}.bound",
            nullable=False,
        )
        ref_count = self.u16(offset + 0x32)
        if ref_count != 1:
            self.error(
                f"{path}.ref_count",
                f"expected 1 owner, found {ref_count}",
                code="yft.binary.damp.expected_1_owner_found",
            )
        return bound

    def _validate_geometry_bound(
        self,
        pointer: int,
        offset: int,
        path: str,
        *,
        with_bvh: bool,
    ) -> None:
        size = _BOUND_BVH_SIZE if with_bvh else _BOUND_GEOMETRY_SIZE
        if (
            self.pointer(
                pointer,
                path,
                size=size,
                nullable=False,
            )
            is None
        ):
            return
        vertex_count = self.u32(offset + 0xD0)
        polygon_count = self.u32(offset + 0xD4)
        material_count = self.u8(offset + 0x120)
        if vertex_count > MAX_FRAGMENT_BOUND_VERTICES:
            self.error(
                f"{path}.vertices",
                f"{vertex_count} exceeds the fragment bound limit "
                f"of {MAX_FRAGMENT_BOUND_VERTICES}",
                code="yft.binary.validate_geometry_bound.exceeds_fragment_bound_limit",
            )
        if polygon_count > MAX_FRAGMENT_BOUND_POLYGONS:
            self.error(
                f"{path}.polygons",
                f"{polygon_count} exceeds the fragment bound limit "
                f"of {MAX_FRAGMENT_BOUND_POLYGONS}",
                code="yft.binary.validate_geometry_bound.exceeds_fragment_bound_limit",
            )
        if material_count > MAX_FRAGMENT_BOUND_MATERIALS:
            self.error(
                f"{path}.materials",
                f"{material_count} exceeds the fragment bound limit "
                f"of {MAX_FRAGMENT_BOUND_MATERIALS}",
                code="yft.binary.validate_geometry_bound.exceeds_fragment_bound_limit",
            )
        self.pointer(
            self.u64(offset + 0xB0),
            f"{path}.vertices",
            size=vertex_count * 6,
            nullable=vertex_count == 0,
        )
        shrunk_pointer = self.u64(offset + 0x78)
        shrunk_count = self.u32(offset + 0x84)
        self.pointer(
            shrunk_pointer,
            f"{path}.vertices_shrunk",
            size=shrunk_count * 6,
            nullable=with_bvh or shrunk_count == 0,
        )
        polygons_offset = self.pointer(
            self.u64(offset + 0x88),
            f"{path}.polygons",
            size=polygon_count * 16,
            nullable=polygon_count == 0,
        )
        material_indices_offset = self.pointer(
            self.u64(offset + 0x118),
            f"{path}.polygon_material_indices",
            size=polygon_count,
            nullable=polygon_count == 0,
        )
        if material_count:
            self.pointer(
                self.u64(offset + 0xF0),
                f"{path}.materials",
                size=max(4, material_count) * 8,
                nullable=False,
            )
        if material_indices_offset is not None:
            for index in range(polygon_count):
                material_index = self.u8(material_indices_offset + index)
                if material_index >= material_count:
                    self.error(
                        f"{path}.polygon_material_indices[{index}]",
                        f"material {material_index} is outside "
                        f"{material_count} entries",
                        code="yft.binary.validate_geometry_bound.material_outside_entries",
                    )
        if polygons_offset is not None:
            for index in range(polygon_count):
                polygon = polygons_offset + index * 16
                polygon_type = self.u8(polygon) & 0x07
                if polygon_type == 0:
                    vertex_indices = tuple(
                        value & 0x7FFF
                        for value in struct.unpack_from(
                            "<3H",
                            self.system_data,
                            polygon + 4,
                        )
                    )
                elif polygon_type == 1:
                    vertex_indices = (self.u16(polygon + 2),)
                elif polygon_type in (2, 4):
                    vertex_indices = (
                        self.u16(polygon + 2),
                        self.u16(polygon + 8),
                    )
                elif polygon_type == 3:
                    vertex_indices = tuple(
                        value & 0xFFFF
                        for value in struct.unpack_from(
                            "<4h",
                            self.system_data,
                            polygon + 4,
                        )
                    )
                else:
                    self.error(
                        f"{path}.polygons[{index}]",
                        f"unsupported polygon type {polygon_type}",
                        code="yft.binary.validate_geometry_bound.unsupported_polygon_type",
                    )
                    continue
                for vertex_index in vertex_indices:
                    if vertex_index >= vertex_count:
                        self.error(
                            f"{path}.polygons[{index}]",
                            f"vertex {vertex_index} is outside {vertex_count} entries",
                            code="yft.binary.validate_geometry_bound.vertex_outside_entries",
                        )

        octants = self.u64(offset + 0xC0)
        octant_pointers = self.u64(offset + 0xC8)
        if not with_bvh and (octants or octant_pointers):
            counts_offset = self.pointer(
                octants,
                f"{path}.octants.counts",
                size=8 * 4,
                nullable=False,
            )
            pointers_offset = self.pointer(
                octant_pointers,
                f"{path}.octants.items",
                size=8 * 8,
                nullable=False,
            )
            if counts_offset is not None and pointers_offset is not None:
                for index in range(8):
                    count = self.u32(counts_offset + index * 4)
                    items = self.pointer(
                        self.u64(pointers_offset + index * 8),
                        f"{path}.octants[{index}]",
                        size=count * 4,
                        nullable=count == 0,
                    )
                    if items is None:
                        continue
                    for item_index in range(count):
                        vertex_index = self.u32(items + item_index * 4)
                        if vertex_index >= vertex_count:
                            self.error(
                                f"{path}.octants[{index}][{item_index}]",
                                f"vertex {vertex_index} is outside "
                                f"{vertex_count} entries",
                                code="yft.binary.validate_geometry_bound.vertex_outside_entries",
                            )

    def validate_profile_bound_tree(
        self,
        pointer: int,
        path: str,
        *,
        expected_slots: int | None = None,
    ) -> list[int]:
        offset = self.pointer(
            pointer,
            path,
            size=_BOUND_BASE_SIZE,
            nullable=False,
        )
        if offset is None:
            return []
        try:
            bound_type = BoundType(self.u8(offset + 0x10))
        except ValueError:
            self.error(
                f"{path}.type",
                f"unsupported bound type {self.u8(offset + 0x10)}",
                code="yft.binary.profile_bound_tree.unsupported_bound_type",
            )
            return []
        vft = self.u32(offset)
        expected_vft = (
            GEN9_BOUND_FILE_VFTS.get(bound_type)
            if self.runtime_headers.enhanced
            else expected_profile_vft(bound_type, self.profile)
        )
        if self.runtime_headers.enhanced and expected_vft is None:
            self.error(
                f"{path}.type",
                f"{bound_type.name} is not defined for Enhanced resources",
                code="yft.binary.profile_bound_tree.not_defined_enhanced_resources",
            )
        elif (
            self.profile is not YftPhysicsBoundProfile.PRESERVE and expected_vft is None
        ):
            self.error(
                f"{path}.type",
                f"{bound_type.name} is not defined for {self.profile.value}",
                code="yft.binary.profile_bound_tree.not_defined",
            )
        elif expected_vft is not None and vft != expected_vft:
            self.error(
                f"{path}.vft",
                f"expected target runtime VFT 0x{expected_vft:08X}, found 0x{vft:08X}",
                code="yft.binary.profile_bound_tree.expected_target_runtime_vft_0x_08x_found_0x_08x",
            )
        elif not vft:
            self.error(
                f"{path}.vft",
                "bound VFT is zero",
                code="yft.binary.profile_bound_tree.bound_vft_zero",
            )

        finite_values = struct.unpack_from("<f", self.system_data, offset + 0x14)
        finite_values += struct.unpack_from("<4f", self.system_data, offset + 0x20)
        finite_values += struct.unpack_from("<3f", self.system_data, offset + 0x30)
        finite_values += struct.unpack_from("<3f", self.system_data, offset + 0x40)
        finite_values += struct.unpack_from("<3f", self.system_data, offset + 0x50)
        finite_values += struct.unpack_from("<4f", self.system_data, offset + 0x60)
        if not all(math.isfinite(value) for value in finite_values):
            self.error(
                path,
                "bound metrics contain NaN or infinity",
                code="yft.binary.profile_bound_tree.bound_metrics_contain_nan_infinity",
            )
        minimum = struct.unpack_from("<3f", self.system_data, offset + 0x30)
        maximum = struct.unpack_from("<3f", self.system_data, offset + 0x20)
        if any(minimum[axis] > maximum[axis] for axis in range(3)):
            self.error(
                path,
                "bound AABB is inverted",
                code="yft.binary.profile_bound_tree.bound_aabb_inverted",
            )

        if bound_type is BoundType.GEOMETRY:
            self._validate_geometry_bound(
                pointer,
                offset,
                path,
                with_bvh=False,
            )
            return []
        if bound_type is BoundType.GEOMETRY_BVH:
            if self.profile not in (
                YftPhysicsBoundProfile.VEHICLE,
                YftPhysicsBoundProfile.PRESERVE,
            ):
                self.error(
                    path,
                    f"BoundBVH is not valid for {self.profile.value}",
                    code="yft.binary.profile_bound_tree.boundbvh_not_valid",
                )
            self._validate_geometry_bound(
                pointer,
                offset,
                path,
                with_bvh=True,
            )
            return []
        if bound_type is not BoundType.COMPOSITE:
            if expected_slots not in (None, 1):
                self.error(
                    path,
                    f"{bound_type.name} cannot provide {expected_slots} physics slots",
                    code="yft.binary.profile_bound_tree.cannot_provide_physics_slots",
                )
            return [pointer]

        if (
            self.pointer(
                pointer,
                path,
                size=_BOUND_COMPOSITE_SIZE,
                nullable=False,
            )
            is None
        ):
            return []
        capacity = self.u16(offset + 0xA0)
        count = self.u16(offset + 0xA2)
        if count > capacity:
            self.error(
                f"{path}.children",
                f"active count {count} exceeds capacity {capacity}",
                code="yft.binary.profile_bound_tree.active_count_exceeds_capacity",
            )
        if expected_slots is not None and count != expected_slots:
            self.error(
                f"{path}.children",
                f"composite has {count} slots for {expected_slots} physics children",
                code="yft.binary.profile_bound_tree.composite_slots_physics_children",
            )
        children = list(
            self.pointer_array(
                self.u64(offset + 0x70),
                capacity,
                f"{path}.children",
            )
        )
        array_offsets: dict[str, int | None] = {}
        for field_offset, item_size, label in (
            (0x78, 0x40, "transforms"),
            (0x80, 0x40, "transforms_copy"),
            (0x88, 0x20, "child_bounds"),
            (0x90, 0x08, "flags1"),
            (0x98, 0x08, "flags2"),
        ):
            array_offsets[label] = self.pointer(
                self.u64(offset + field_offset),
                f"{path}.{label}",
                size=capacity * item_size,
                nullable=(
                    capacity == 0 or label in ("transforms_copy", "flags1", "flags2")
                ),
            )
        for index, child in enumerate(children):
            child_path = f"{path}.children[{index}]"
            child_bounds = array_offsets["child_bounds"]
            if child_bounds is not None:
                packed_bounds = struct.unpack_from(
                    "<8f",
                    self.system_data,
                    child_bounds + index * 0x20,
                )
                if not all(math.isfinite(value) for value in packed_bounds):
                    self.error(
                        f"{child_path}.bounds",
                        "slot AABB contains NaN or infinity",
                        code="yft.binary.profile_bound_tree.slot_aabb_contains_nan_infinity",
                    )
            if not child:
                for label in ("flags1", "flags2"):
                    flags = array_offsets[label]
                    if flags is not None and struct.unpack_from(
                        "<II",
                        self.system_data,
                        flags + index * 8,
                    ) != (0, 0):
                        self.error(
                            f"{child_path}.{label}",
                            "null slot must have zero flags",
                            code="yft.binary.profile_bound_tree.null_slot_must_zero_flags",
                        )
                continue
            child_offset = self.pointer(
                child,
                child_path,
                size=_BOUND_BASE_SIZE,
                nullable=False,
            )
            if child_offset is None:
                continue
            child_type = self.u8(child_offset + 0x10)
            if self.profile in (
                YftPhysicsBoundProfile.PROP,
                YftPhysicsBoundProfile.SET_PIECE,
            ) and child_type == int(BoundType.COMPOSITE):
                self.error(
                    child_path,
                    "nested composite is not valid",
                    code="yft.binary.profile_bound_tree.nested_composite_not_valid",
                )
            self.validate_profile_bound_tree(child, child_path)
        return children[:count]

    def _bound_slot_signature(self, pointer: int) -> tuple[object, ...] | None:
        offset = self.pointer(
            pointer,
            "bound_signature",
            size=_BOUND_BASE_SIZE,
            nullable=True,
        )
        if offset is None:
            return None
        return (
            self.u32(offset),
            self.u8(offset + 0x10),
            self.u16(offset + 0x12),
            self.system_data[offset + 0x14 : offset + 0x3C],
            self.system_data[offset + 0x40 : offset + 0x70],
        )

    def validate_matching_bound_slots(
        self,
        primary: list[int],
        other: list[int],
        path: str,
    ) -> None:
        if len(primary) != len(other):
            self.error(
                path,
                "bound owner slot counts do not match",
                code="yft.binary.matching_bound_slots.bound_owner_slot_counts_do_not_match",
            )
            return
        for index, (expected, actual) in enumerate(zip(primary, other, strict=True)):
            if bool(expected) != bool(actual):
                self.error(
                    f"{path}[{index}]",
                    "bound owner nullability does not match",
                    code="yft.binary.matching_bound_slots.bound_owner_nullability_does_not_match",
                )
                continue
            if expected and (
                self._bound_slot_signature(expected)
                != self._bound_slot_signature(actual)
            ):
                self.error(
                    f"{path}[{index}]",
                    "bound owner slot does not match the composite order",
                    code="yft.binary.matching_bound_slots.bound_owner_slot_does_not_match_composite_order",
                )

    def validate_bound_ref_count(
        self,
        pointer: int,
        path: str,
        expected: int,
    ) -> None:
        offset = self.pointer(
            pointer,
            path,
            size=_BOUND_BASE_SIZE,
            nullable=False,
        )
        if offset is None:
            return
        actual = self.u32(offset + 0x3C)
        if actual != expected:
            self.error(
                f"{path}.ref_count",
                f"expected {expected} owners, found {actual}",
                code="yft.binary.bound_ref_count.expected_owners_found",
            )

    def validate_child_bound_link(
        self,
        child_pointer: int,
        path: str,
        *,
        entity_field: int,
        entity_label: str,
        expected_bound: int,
    ) -> None:
        child = self.pointer(
            child_pointer,
            path,
            size=_PHYSICS_CHILD_SIZE,
            nullable=False,
        )
        if child is None:
            return
        entity_pointer = self.u64(child + entity_field)
        if not entity_pointer:
            return
        entity_path = f"{path}.{entity_label}"
        entity = self.pointer(
            entity_pointer,
            entity_path,
            size=0xF8,
            nullable=False,
        )
        if entity is None:
            return
        actual_bound = self.u64(entity + 0xF0)
        if not expected_bound:
            if actual_bound:
                self.error(
                    f"{entity_path}.bound",
                    "must be null because the matching archetype bound child is null",
                    code="yft.binary.child_bound_link.must_null_because_matching_archetype_bound_child_null",
                )
        elif actual_bound != expected_bound:
            self.error(
                f"{entity_path}.bound",
                f"must reference the matching archetype bound child "
                f"0x{expected_bound:08X}, got 0x{actual_bound:08X}; "
                "standalone fragDrawable bounds are not resource-constructed",
                code="yft.binary.child_bound_link.must_reference_matching_archetype_bound_child_0x_08x_got",
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
            self.error(
                f"{path}.num_links",
                f"{num_links} exceeds the native limit of 23",
                code="yft.binary.body.exceeds_native_limit_23",
            )
        if num_joints > 22:
            self.error(
                f"{path}.num_joints",
                f"{num_joints} exceeds the native limit of 22",
                code="yft.binary.body.exceeds_native_limit_22",
            )
        if num_children and num_links not in (0, num_children):
            self.error(
                f"{path}.num_links",
                f"{num_links} links do not match {num_children} physics children",
                code="yft.binary.body.links_do_not_match_physics_children",
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
                    code="yft.binary.body.unsupported_joint_type",
                )
                continue
            self.class_header(
                joint_pointer,
                f"{path}.joints[{index}]",
                size=joint_size,
                expected_vft=(
                    self.runtime_headers.joint_1dof
                    if joint_type == 0
                    else self.runtime_headers.joint_3dof
                ),
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
            expected_vft=self.runtime_headers.physics_transforms,
        )
        if offset is None:
            return
        count = self.u32(offset + 0x10)
        self.pointer(pointer, path, size=0x20 + count * 64, nullable=False)
        if count != num_children:
            self.error(
                f"{path}.count",
                f"{count} transforms do not match {num_children} physics children",
                code="yft.binary.transforms.transforms_do_not_match_physics_children",
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
            expected_vft=self.runtime_headers.physics_lod,
        )
        if offset is None:
            return
        num_self_collisions = self.u8(offset + 0x118)
        num_groups = self.u8(offset + 0x11A)
        root_group_count = self.u8(offset + 0x11B)
        num_bony_children = self.u8(offset + 0x11D)
        num_children = self.u8(offset + 0x11E)
        if root_group_count > num_groups:
            self.error(
                f"{path}.root_group_count",
                f"{root_group_count} exceeds {num_groups} groups",
                code="yft.binary.lod.exceeds_groups",
            )
        if num_bony_children > num_children:
            self.error(
                f"{path}.num_bony_children",
                f"{num_bony_children} exceeds {num_children} children",
                code="yft.binary.lod.exceeds_children",
            )

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
        group_offsets = [
            self.pointer(
                group,
                f"{path}.groups[{index}]",
                size=_PHYSICS_GROUP_SIZE,
                nullable=False,
            )
            for index, group in enumerate(groups)
        ]
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
        child_offsets = [
            self.pointer(
                child,
                f"{path}.children[{index}]",
                size=_PHYSICS_CHILD_SIZE,
                nullable=False,
            )
            for index, child in enumerate(children)
        ]
        actual_root_groups = sum(
            1
            for group in group_offsets
            if group is not None and self.u8(group + 0x4D) == 0xFF
        )
        if root_group_count != actual_root_groups:
            self.error(
                f"{path}.root_group_count",
                f"declares {root_group_count} root groups but has {actual_root_groups}",
                code="yft.binary.lod.declares_root_groups",
            )
        claimed_children: set[int] = set()
        for group_index, group in enumerate(group_offsets):
            if group is None:
                continue
            death_event_set = self.u64(group)
            if death_event_set:
                self.validate_event_set(
                    death_event_set,
                    f"{path}.groups[{group_index}].death_event_set",
                )
            death_event_player = self.u64(group + 0x08)
            if death_event_player:
                self.pointer(
                    death_event_player,
                    f"{path}.groups[{group_index}].death_event_player",
                )
            child_index = self.u8(group + 0x4E)
            group_child_count = self.u8(group + 0x4F)
            if child_index == 0xFF:
                if group_child_count:
                    self.error(
                        f"{path}.groups[{group_index}]",
                        "empty child slice has a non-zero count",
                        code="yft.binary.lod.empty_child_slice_non_zero_count",
                    )
                continue
            if child_index + group_child_count > num_children:
                self.error(
                    f"{path}.groups[{group_index}]",
                    "child slice points outside the child array",
                    code="yft.binary.lod.child_slice_points_outside_child_array",
                )
                continue
            for child_index_value in range(
                child_index,
                child_index + group_child_count,
            ):
                if child_index_value in claimed_children:
                    self.error(
                        f"{path}.groups[{group_index}]",
                        f"physics child {child_index_value} belongs to multiple groups",
                        code="yft.binary.lod.physics_child_belongs_multiple_groups",
                    )
                claimed_children.add(child_index_value)
                child = child_offsets[child_index_value]
                if child is not None and self.u8(child + 0x10) != group_index:
                    self.error(
                        f"{path}.children[{child_index_value}]",
                        "owner group does not match the ordered group slice",
                        code="yft.binary.lod.owner_group_does_not_match_ordered_group_slice",
                    )
        if num_children and claimed_children != set(range(num_children)):
            self.error(
                f"{path}.groups",
                "group slices must cover every physics child exactly once",
                code="yft.binary.lod.group_slices_must_cover_every_physics_child_exactly_once",
            )

        damp_bounds: dict[str, int] = {}
        for field_offset, label in (
            (0xD8, "undamaged_damp_archetype"),
            (0xE0, "damaged_damp_archetype"),
        ):
            damp = self.u64(offset + field_offset)
            if damp:
                damp_bounds[label] = self.validate_damp(
                    damp,
                    f"{path}.{label}",
                )
        undamaged_bound = damp_bounds.get("undamaged_damp_archetype", 0)
        damaged_bound = damp_bounds.get("damaged_damp_archetype", 0)
        composite_bound = self.u64(offset + 0xE8)
        if not undamaged_bound:
            self.error(
                f"{path}.undamaged_damp_archetype.bound",
                "physics LOD requires a non-null undamaged bound",
                code="yft.binary.lod.physics_lod_requires_non_null_undamaged_bound",
            )
        if undamaged_bound and damaged_bound == undamaged_bound:
            self.error(
                f"{path}.damaged_damp_archetype.bound",
                "damaged and undamaged archetypes must not share a bound "
                "resource; the second construction would fix up the same "
                "pointers twice",
                code="yft.binary.lod.damaged_undamaged_archetypes_must_not_share_bound_resource_second",
            )
        if composite_bound:
            self.validate_bound_ref_count(
                composite_bound,
                f"{path}.composite_bound",
                1 + int(composite_bound == undamaged_bound),
            )
        if undamaged_bound and undamaged_bound != composite_bound:
            self.validate_bound_ref_count(
                undamaged_bound,
                f"{path}.undamaged_damp_archetype.bound",
                1,
            )
        if damaged_bound:
            self.validate_bound_ref_count(
                damaged_bound,
                f"{path}.damaged_damp_archetype.bound",
                2,
            )
        composite_child_bounds = self.validate_profile_bound_tree(
            composite_bound,
            f"{path}.composite_bound",
            expected_slots=num_children,
        )
        undamaged_child_bounds = (
            self.validate_profile_bound_tree(
                undamaged_bound,
                f"{path}.undamaged_damp_archetype.bound",
                expected_slots=num_children,
            )
            if undamaged_bound
            else []
        )
        damaged_child_bounds = (
            self.validate_profile_bound_tree(
                damaged_bound,
                f"{path}.damaged_damp_archetype.bound",
                expected_slots=num_children,
            )
            if damaged_bound
            else []
        )
        if composite_bound and undamaged_bound and composite_bound != undamaged_bound:
            self.validate_matching_bound_slots(
                composite_child_bounds,
                undamaged_child_bounds,
                f"{path}.undamaged_damp_archetype.bound.children",
            )
        if damaged_bound:
            for index, child in enumerate(child_offsets):
                if child is None:
                    continue
                damaged_entity = self.u64(child + 0xA8)
                damaged_child_bound = (
                    damaged_child_bounds[index]
                    if index < len(damaged_child_bounds)
                    else 0
                )
                if not damaged_entity and damaged_child_bound:
                    self.error(
                        (f"{path}.damaged_damp_archetype.bound.children[{index}]"),
                        "must be null when the matching physics child has "
                        "no damaged entity",
                        code="yft.binary.lod.must_null_when_matching_physics_child_no_damaged_entity",
                    )
        if self.profile is YftPhysicsBoundProfile.PROP:
            for index in range(num_children):
                undamaged_child_bound = (
                    undamaged_child_bounds[index]
                    if index < len(undamaged_child_bounds)
                    else 0
                )
                damaged_child_bound = (
                    damaged_child_bounds[index]
                    if index < len(damaged_child_bounds)
                    else 0
                )
                if not undamaged_child_bound and not damaged_child_bound:
                    self.error(
                        f"{path}.children[{index}]",
                        "physical child has no collision in either state",
                        code="yft.binary.lod.physical_child_no_collision_either_state",
                    )
        for index, child in enumerate(children):
            child_path = f"{path}.children[{index}]"
            self.validate_child_bound_link(
                child,
                child_path,
                entity_field=0xA0,
                entity_label="undamaged_entity",
                expected_bound=(
                    undamaged_child_bounds[index]
                    if index < len(undamaged_child_bounds)
                    else 0
                ),
            )
            self.validate_child_bound_link(
                child,
                child_path,
                entity_field=0xA8,
                entity_label="damaged_entity",
                expected_bound=(
                    damaged_child_bounds[index]
                    if index < len(damaged_child_bounds)
                    else 0
                ),
            )

        transforms = self.u64(offset + 0x100)
        if transforms:
            self.validate_transforms(
                transforms,
                f"{path}.link_attachments",
                num_children,
            )
        elif num_children and self.profile is not YftPhysicsBoundProfile.PRESERVE:
            self.error(
                f"{path}.link_attachments",
                "authored physics LOD requires one attachment per child",
                code="yft.binary.lod.authored_physics_lod_requires_one_attachment_per_child",
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

    def validate(self) -> ValidationReport:
        root = RSC7_VIRTUAL_BASE
        root_offset = self.class_header(
            root,
            "root",
            size=FRAGMENT_ROOT_SIZE,
            expected_vft=self.runtime_headers.fragment_type,
        )
        if root_offset is None:
            return self.report

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
                    code="yft.binary.validate.page_counts_do_not_match_rsc7_resource_map",
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
        collision_event_set = self.u64(root_offset + 0x88)
        if collision_event_set:
            self.validate_event_set(
                collision_event_set,
                "root.collision_event_set",
            )
        collision_event_player = self.u64(root_offset + 0x90)
        if collision_event_player:
            self.pointer(
                collision_event_player,
                "root.collision_event_player",
            )

        physics_group = self.u64(root_offset + 0xF0)
        if physics_group:
            group_offset = self.class_header(
                physics_group,
                "root.physics_lod_group",
                size=0x30,
                expected_vft=self.runtime_headers.physics_lod_group,
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
        return self.report


def validate_yft_bytes(
    source: ByteSource,
    *,
    profile: YftPhysicsBoundProfile | str = (YftPhysicsBoundProfile.PRESERVE),
) -> ValidationReport:
    asset = str(source) if isinstance(source, (str, Path)) else None
    try:
        data = read_source_bytes(source)
        header, payload = parse_rsc7(data)
    except (OSError, ValueError, struct.error) as exc:
        report = ValidationReport()
        report.issue(
            "yft.binary.resource_invalid",
            str(exc),
            asset=asset,
            path="resource",
        )
        return report
    if len(payload) != header.total_size:
        report = ValidationReport()
        report.issue(
            "yft.binary.payload_size_mismatch",
            f"decoded size 0x{len(payload):X} does not match "
            f"RSC7 size 0x{header.total_size:X}",
            asset=asset,
            path="resource.payload",
        )
        return report
    system_data = payload[: header.system_size]
    graphics_data = payload[header.system_size :]
    report = _YftBinaryValidator(
        header,
        system_data,
        graphics_data,
        profile=coerce_yft_physics_bound_profile(profile),
    ).validate()
    if asset is not None:
        report.issues = [issue.for_asset(asset) for issue in report]
    return report


__all__ = [
    "validate_yft_bytes",
]
