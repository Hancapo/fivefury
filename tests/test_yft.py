from __future__ import annotations

import dataclasses
import math
import struct
from pathlib import Path

import pytest

from fivefury import (
    BoundAabb,
    BoundBox,
    BoundChild,
    BoundComposite,
    BoundGeometry,
    BoundMaterial,
    YdrMaterialInput,
    YdrMeshInput,
    build_bound_from_triangles,
    calculate_bound_ref_counts,
    create_ydr,
)
from fivefury.common import atomic_write_bytes
from fivefury.resource import (
    ResourceHeader,
    build_rsc7,
    get_resource_chunk_sizes,
    get_resource_flags_from_page_counts,
    get_resource_size_from_flags,
    split_rsc7_sections,
    validate_resource_pointer,
    virtual_to_offset,
)
from fivefury.ydr import (
    Ydr,
    YdrLight,
    YdrLod,
    YdrMaterial,
    YdrMesh,
    YdrModel,
    YdrSkeleton,
)
from fivefury.ydr.resource_headers import LEGACY_FRAGMENT_DRAWABLE_HEADERS
from fivefury.yft import (
    MAX_FRAGMENT_BOUND_VERTICES,
    Yft,
    YftClothBridge,
    YftClothController,
    YftClothMorphController,
    YftClothTuning,
    YftDrawable,
    YftEnvironmentCloth,
    YftEventSet,
    YftFragmentDrawable,
    YftFragmentFlag,
    YftFragmentMatrix,
    YftFragmentState,
    YftGlassPane,
    YftPhysicsBoundProfile,
    YftPhysicsChild,
    YftPhysicsDampArchetype,
    YftPhysicsEntity,
    YftPhysicsGroup,
    YftPhysicsGroupFlag,
    YftPhysicsLod,
    YftPhysicsLodPointers,
    YftSharedMatrixSet,
    YftVehicleGlassFlag,
    YftVehicleGlassRow,
    YftVehicleGlassWindow,
    YftVehicleGlassWindows,
    YftVerletCloth,
    build_fragment_geometry_bound,
    build_yft_bytes,
    create_yft,
    normalize_physics_lod,
    read_yft,
    scan_yft_corpus,
    validate_yft,
    validate_yft_bytes,
)
from fivefury.yft.resource_headers import (
    FRAG_PHYS_ARCHETYPE_DAMP_VFT,
    FRAG_PHYS_TRANSFORMS_VFT,
    FRAG_PHYSICS_LOD_VFT,
    FRAG_TYPE_CHILD_VFT,
    PH_JOINT_3DOF_TYPE_VFT,
    RESOURCE_STATE,
)


def _composite(*bounds):
    return BoundComposite(
        bound_type=10,
        sphere_radius=0.0,
        box_max=(0.0, 0.0, 0.0),
        margin=0.0,
        box_min=(0.0, 0.0, 0.0),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
        children=[BoundChild(bound) for bound in bounds],
    ).build()


def _bound_child_pointer(
    system_data: bytes,
    root_pointer: int,
    index: int = 0,
) -> int:
    root_offset = virtual_to_offset(root_pointer)
    children_pointer = struct.unpack_from(
        "<Q",
        system_data,
        root_offset + 0x70,
    )[0]
    return struct.unpack_from(
        "<Q",
        system_data,
        virtual_to_offset(children_pointer) + index * 8,
    )[0]


def _simple_fragment_drawable(name: str):
    return create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="body",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="body")],
        name=name,
    )


def test_yft_light_array_roundtrip():
    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="default",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="default")],
        name="lit_fragment",
    )
    light = YdrLight.spot(
        position=(1.0, 2.0, 3.0),
        direction=(0.0, 0.0, -1.0),
        color="#80c0ff",
        intensity=4.5,
        falloff=12.0,
        cone_inner_angle=20.0,
        cone_outer_angle=35.0,
        bone_id=7,
        group_id=2,
    )
    source = create_yft(drawable, name="lit_fragment", lights=(light,))

    raw = build_yft_bytes(source)
    _, system_data, _ = split_rsc7_sections(raw)
    parsed = read_yft(raw, resolve_physics_entities=False)

    assert struct.unpack_from("<Q", system_data, 0x110)[0] != 0
    assert struct.unpack_from("<H", system_data, 0x118)[0] == 1
    assert struct.unpack_from("<H", system_data, 0x11A)[0] == 1
    assert len(parsed.lights) == 1
    parsed_light = parsed.lights[0]
    assert parsed_light.position == (1.0, 2.0, 3.0)
    assert parsed_light.color == (128, 192, 255)
    assert parsed_light.intensity == 4.5
    assert parsed_light.bone_id == 7
    assert parsed_light.group_id == 2
    assert parsed.validate() == []


def test_yft_application_user_data_roundtrip():
    drawable = create_ydr(
        meshes=[],
        materials=[],
        name="user_data_fragment",
    )
    source = create_yft(
        drawable,
        name="user_data_fragment",
        user_data=0x12345678,
    )

    raw = build_yft_bytes(source)
    _, system_data, _ = split_rsc7_sections(raw)
    parsed = read_yft(raw, resolve_physics_entities=False)

    assert struct.unpack_from("<Q", system_data, 0x80)[0] == 0x12345678
    assert parsed.user_data == 0x12345678
    assert parsed.validate() == []


def test_yft_shared_matrix_set_roundtrip():
    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="default",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="default")],
        name="matrix_fragment",
    )
    skeleton = YdrSkeleton.create()
    skeleton.add_bone("root")
    skeleton.add_bone("child", parent="root", translation=(0.0, 0.0, 1.0))
    drawable.skeleton = skeleton
    source = create_yft(drawable, name="matrix_fragment")

    raw = build_yft_bytes(source)
    _, system_data, _ = split_rsc7_sections(raw)
    drawable_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, 0x30)[0]
    )
    skeleton_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, drawable_offset + 0x18)[0]
    )
    parsed = read_yft(raw, resolve_physics_entities=False)

    assert struct.unpack_from("<II", system_data, skeleton_offset) == (
        LEGACY_FRAGMENT_DRAWABLE_HEADERS.skeleton,
        RESOURCE_STATE,
    )
    assert parsed.shared_matrix_set is not None
    assert parsed.shared_matrix_set.matrix_count == 2
    assert parsed.shared_matrix_set.is_skinned is False
    assert parsed.shared_matrix_set.matrices[0] == (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
    )
    assert parsed.shared_matrix_set.matrices[1] == (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        1.0,
    )
    assert validate_yft_bytes(raw) == []

    explicit = create_yft(
        drawable,
        name="explicit_matrix_fragment",
        shared_matrix_set=YftSharedMatrixSet.declare(
            [tuple(float(value) for value in range(12))],
            is_skinned=True,
        ),
    )
    explicit_parsed = read_yft(
        build_yft_bytes(explicit),
        resolve_physics_entities=False,
    )
    assert explicit_parsed.shared_matrix_set is not None
    assert explicit_parsed.shared_matrix_set.is_skinned is True
    assert explicit_parsed.shared_matrix_set.matrices[0] == tuple(
        float(value) for value in range(12)
    )


def test_yft_glass_roundtrip():
    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="glass",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="glass")],
        name="glass_fragment",
    )
    pane = YftGlassPane(
        position_base=(-1.0, 0.0, 0.0),
        position_width=(2.0, 0.0, 0.0),
        position_height=(0.0, 1.5, 0.0),
        shader_index=0,
        glass_type=1,
        bounds_offset_front=0.125,
        bounds_offset_back=-0.25,
    )
    vehicle_glass = YftVehicleGlassWindows(
        [
            YftVehicleGlassWindow.declare(
                7,
                2,
                (
                    YftVehicleGlassRow.declare(1, (10, 20, 30)),
                    YftVehicleGlassRow.declare(
                        0,
                        (1, 2),
                        second_start=5,
                        second_values=(3, 4),
                    ),
                    YftVehicleGlassRow.empty(),
                ),
                data_min=-0.5,
                data_max=0.75,
                flags=(
                    YftVehicleGlassFlag.VERSION_2
                    | YftVehicleGlassFlag.HAS_EXPOSED_EDGES
                ),
                texture_scale=1.25,
            )
        ]
    )
    source = create_yft(
        drawable,
        name="glass_fragment",
        glass_panes=(pane,),
        vehicle_glass_windows=vehicle_glass,
    )
    source.state = dataclasses.replace(source.state, glass_attachment_bone=4)

    raw = build_yft_bytes(source)
    _, system_data, _ = split_rsc7_sections(raw)
    parsed = read_yft(raw, resolve_physics_entities=False)

    assert system_data[0xD9] == 1
    assert struct.unpack_from("<Q", system_data, 0xE0)[0] != 0
    assert struct.unpack_from("<Q", system_data, 0x120)[0] != 0
    assert parsed.state.glass_attachment_bone == 4
    assert parsed.glass_pane_count == 1
    assert parsed.glass_panes[0].shader_index == 0
    assert parsed.glass_panes[0].bounds_offset_front == 0.125
    assert parsed.vehicle_glass_windows is not None
    window = parsed.vehicle_glass_windows.windows[0]
    assert window.component_id == 7
    assert window.geometry_index == 2
    assert window.column_count == 7
    assert window.row_count == 3
    assert window.rows[0].first.values == bytes((10, 20, 30))
    assert window.rows[1].second.values == bytes((3, 4))
    assert window.rows[2] == YftVehicleGlassRow.empty()
    assert window.flags & YftVehicleGlassFlag.HAS_EXPOSED_EDGES
    assert parsed.validate() == []


def test_yft_environment_cloth_roundtrip():
    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="cloth",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="cloth")],
        name="cloth_fragment",
    )
    vertices = [
        (0.0, 0.0, 0.0, 1.0),
        (1.0, 0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, 1.0),
    ]
    cloth = YftEnvironmentCloth(
        controller=YftClothController(
            name="cloth_fragment",
            bridge=YftClothBridge(
                mesh_vertex_counts=(3, 0, 0, 0),
                pin_radii=([0.0, 0.0, 0.0], [], [], []),
                vertex_weights=([1.0, 1.0, 1.0], [], [], []),
                display_maps=([0, 1, 2], [], [], []),
            ),
            morph=YftClothMorphController(),
            verlet_lods=(
                YftVerletCloth(
                    bounds_min=(0.0, 0.0, 0.0),
                    bounds_max=(1.0, 1.0, 0.0),
                    vertices=vertices,
                    previous_vertices=list(vertices),
                ),
                None,
                None,
            ),
        ),
        tuning=YftClothTuning(weight=0.75),
    )
    source = create_yft(drawable, name="cloth_fragment")
    source.environment_cloths.append(cloth)

    parsed = read_yft(build_yft_bytes(source), resolve_physics_entities=False)

    assert len(parsed.environment_cloths) == 1
    parsed_cloth = parsed.environment_cloths[0]
    assert parsed_cloth.drawable_label == "drawable"
    assert parsed_cloth.controller.name == "cloth_fragment"
    assert parsed_cloth.controller.bridge.mesh_vertex_counts == (3, 0, 0, 0)
    assert parsed_cloth.controller.bridge.display_maps[0] == [0, 1, 2]
    assert parsed_cloth.controller.verlet_lods[0].vertices == vertices
    assert parsed_cloth.tuning.weight == 0.75
    assert parsed_cloth.tuning.vft != 0


def test_read_yft_discovers_fragment_drawables(monkeypatch):
    system_data = bytearray(0xC00)
    struct.pack_into("<4f", system_data, 0x20, 1.0, 2.0, 3.0, 4.0)
    struct.pack_into("<Q", system_data, 0x30, 0x50000100)
    struct.pack_into("<Q", system_data, 0x38, 0x50000080)
    struct.pack_into("<Q", system_data, 0x40, 0x50000090)
    struct.pack_into("<I", system_data, 0x48, 2)
    struct.pack_into("<i", system_data, 0x4C, 0)
    struct.pack_into("<Q", system_data, 0x50, 0x500001E0)
    struct.pack_into("<Q", system_data, 0x58, 0x500001F0)
    struct.pack_into("<Q", system_data, 0xF0, 0x50000120)
    system_data[0xC0:0xC3] = bytes([2, 0xFF, 1])
    struct.pack_into(
        "<H",
        system_data,
        0xC4,
        int(
            YftFragmentFlag.NEEDS_CACHE_ENTRY_TO_ACTIVATE
            | YftFragmentFlag.DISABLE_BREAKING
        ),
    )
    struct.pack_into("<i", system_data, 0xC8, 123)
    struct.pack_into("<fff", system_data, 0xCC, 1.0, 0.5, 0.25)
    struct.pack_into("<QQQ", system_data, 0x130, 0x50000200, 0, 0)
    struct.pack_into("<QQ", system_data, 0x80, 0x50000140, 0)
    struct.pack_into("<QQ", system_data, 0x90, 0x500001D0, 0)
    struct.pack_into("<Q", system_data, 0xF8, 0x50000180)
    system_data[0x1F0:0x1FA] = b"tune_name\0"
    system_data[0x1D0:0x1D8] = b"extra\0\0\0"
    struct.pack_into("<fff", system_data, 0x214, 0.25, 12.5, 500.0)
    struct.pack_into("<II", system_data, 0x200, FRAG_PHYSICS_LOD_VFT, RESOURCE_STATE)
    struct.pack_into("<Q", system_data, 0x220, 0x500006E0)
    struct.pack_into("<Q", system_data, 0x228, 0x50000600)
    struct.pack_into("<fff", system_data, 0x230, 1.0, 2.0, 3.0)
    struct.pack_into("<Q", system_data, 0x2C0, 0x50000400)
    struct.pack_into("<Q", system_data, 0x2C8, 0x50000440)
    struct.pack_into("<Q", system_data, 0x2D0, 0x50000450)
    struct.pack_into("<QQ", system_data, 0x2D8, 0x50000800, 0x50000900)
    struct.pack_into("<Q", system_data, 0x2F0, 0x50000620)
    struct.pack_into("<Q", system_data, 0x2F8, 0x50000660)
    struct.pack_into("<Q", system_data, 0x300, 0x50000B00)
    struct.pack_into("<fff", system_data, 0x260, 0.1, 0.2, 0.3)
    system_data[0x318:0x31F] = bytes([0, 0, 1, 1, 2, 3, 4])
    struct.pack_into("<Q", system_data, 0x400, 0x50000420)
    system_data[0x420:0x427] = b"GroupA\0"
    struct.pack_into("<Q", system_data, 0x440, 0x50000480)
    struct.pack_into("<QQQQ", system_data, 0x450, 0x50000540, 0x500005F0, 0, 0)
    struct.pack_into("<QQ", system_data, 0x480, 0x50000A90, 0)
    struct.pack_into("<f", system_data, 0x490, 1000.0)
    struct.pack_into("<f", system_data, 0x4C4, 550.0)
    system_data[0x4CC:0x4D4] = bytes([0xFF, 0xFF, 0, 4, 0, 0xFF, 0, 4])
    struct.pack_into("<f", system_data, 0x4D8, 1.0)
    system_data[0x500:0x507] = b"GroupA\0"
    struct.pack_into("<ff", system_data, 0x548, 10.0, 11.0)
    struct.pack_into("<II", system_data, 0x540, FRAG_TYPE_CHILD_VFT, RESOURCE_STATE)
    system_data[0x550:0x554] = bytes([0, 0, 7, 0])
    struct.pack_into("<II", system_data, 0x5F0, FRAG_TYPE_CHILD_VFT, RESOURCE_STATE)
    struct.pack_into("<QQ", system_data, 0x5E0, 0x50000680, 0x50000690)
    struct.pack_into("<ffff", system_data, 0x600, 100.0, 101.0, 102.0, 103.0)
    struct.pack_into("<ffff", system_data, 0x620, 1.0, 2.0, 3.0, 4.0)
    struct.pack_into("<ffff", system_data, 0x660, 5.0, 6.0, 7.0, 8.0)
    struct.pack_into(
        "<IIQIIQ",
        system_data,
        0xB00,
        FRAG_PHYS_TRANSFORMS_VFT,
        RESOURCE_STATE,
        0,
        1,
        0,
        0,
    )
    struct.pack_into(
        "<16f",
        system_data,
        0xB20,
        1.0,
        0.0,
        0.0,
        10.0,
        0.0,
        1.0,
        0.0,
        20.0,
        0.0,
        0.0,
        1.0,
        30.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    struct.pack_into("<ii", system_data, 0x6F0, -1, 0)
    struct.pack_into("<ff", system_data, 0x74C, 1.0, 0.25)
    struct.pack_into("<QQ", system_data, 0x758, 0x50000A00, 0x50000A10)
    system_data[0x768:0x76B] = bytes([2, 1, 1])
    system_data[0x780] = 1
    struct.pack_into("<Q", system_data, 0xA00, 0x50000A50)
    struct.pack_into(
        "<II", system_data, 0xA50, PH_JOINT_3DOF_TYPE_VFT, RESOURCE_STATE
    )
    struct.pack_into(
        "<ffffffff", system_data, 0xA10, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0
    )
    struct.pack_into("<i", system_data, 0x810, 2)
    struct.pack_into(
        "<II", system_data, 0x800, FRAG_PHYS_ARCHETYPE_DAMP_VFT, RESOURCE_STATE
    )
    struct.pack_into("<QQ", system_data, 0x818, 0x50000A70, 0x50000A80)
    struct.pack_into("<IIH", system_data, 0x828, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF)
    struct.pack_into("<ffffff", system_data, 0x840, 10.0, 0.1, 1.0, 500.0, 6.28, 0.5)
    struct.pack_into("<ffffff", system_data, 0x860, 11.0, 12.0, 13.0, 0.01, 0.02, 0.03)
    struct.pack_into("<fff", system_data, 0x880, 0.7, 0.8, 0.9)
    struct.pack_into("<i", system_data, 0x910, 2)
    struct.pack_into(
        "<II", system_data, 0x900, FRAG_PHYS_ARCHETYPE_DAMP_VFT, RESOURCE_STATE
    )
    struct.pack_into("<ffffff", system_data, 0x940, 20.0, 0.05, 1.0, 500.0, 6.28, 0.25)
    struct.pack_into("<fff", system_data, 0x980, 0.4, 0.5, 0.6)
    struct.pack_into("<I", system_data, 0xA90, 0x74536353)
    calls: list[tuple[int, str]] = []

    def fake_read_drawable(
        _header,
        _system_data,
        _graphics_data,
        pointer,
        *,
        label,
        path,
        shader_library,
    ):
        root_offset = pointer - 0x50000000 + 0x10
        internal_path = (
            f"{path.rsplit('.', 1)[0]}/{label}.ydr" if path else f"{label}.ydr"
        )
        calls.append((root_offset, internal_path))
        return YftFragmentDrawable(version=162, path=internal_path)

    monkeypatch.setattr(
        "fivefury.yft.reader.read_fragment_drawable", fake_read_drawable
    )
    monkeypatch.setattr(
        "fivefury.yft.physics_reader.read_fragment_drawable", fake_read_drawable
    )

    yft = read_yft(build_rsc7(bytes(system_data), version=162), path="example.yft")

    assert yft.version == 162
    assert yft.bounding_sphere == (1.0, 2.0, 3.0, 4.0)
    assert yft.pointers.common_drawable == 0x50000100
    assert yft.pointers.root_child == 0x500001E0
    assert yft.pointers.tune_name == 0x500001F0
    assert yft.state.damaged_drawable_index == 0
    assert yft.pointers.physics_lod_group == 0x50000120
    assert yft.state.entity_class == 2
    assert yft.state.art_asset_id == -1
    assert yft.state.attach_bottom_end is True
    assert yft.state.flags == (
        YftFragmentFlag.NEEDS_CACHE_ENTRY_TO_ACTIVATE | YftFragmentFlag.DISABLE_BREAKING
    )
    assert yft.state.client_class_id == 123
    assert yft.state.gravity_factor == 0.5
    assert yft.physics_lods == YftPhysicsLodPointers(high=0x50000200)
    assert yft.physics_lods.has_physics is True
    assert yft.physics_lods.active_count == 1
    assert len(yft.physics_lod_details) == 1
    assert yft.physics_lod_details[0].label == "high"
    assert yft.physics_lod_details[0].vft == FRAG_PHYSICS_LOD_VFT
    assert yft.physics_lod_details[0].resource_state == RESOURCE_STATE
    assert yft.physics_lod_details[0].smallest_ang_inertia == 0.25
    assert yft.physics_lod_details[0].root_cg_offset == (1.0, 2.0, 3.0)
    assert yft.physics_lod_details[0].num_groups == 1
    assert yft.physics_lod_details[0].num_children == 4
    assert yft.physics_lod_details[0].group_names == ("GroupA",)
    assert yft.physics_lod_details[0].group_pointers == (0x50000480,)
    assert yft.physics_lod_details[0].child_pointers == (0x50000540, 0x500005F0, 0, 0)
    assert len(yft.physics_lod_details[0].groups) == 1
    assert yft.physics_lod_details[0].groups[0].strength == 1000.0
    assert yft.physics_lod_details[0].groups[0].total_undamaged_mass == 550.0
    assert (
        yft.physics_lod_details[0].groups[0].flags
        == YftPhysicsGroupFlag.DAMAGE_WHEN_BROKEN
    )
    assert yft.physics_lod_details[0].groups[0].debug_name == "GroupA"
    assert yft.physics_lod_details[0].groups[0].name == "GroupA"
    assert yft.physics_lod_details[0].groups[0].events.death.pointer == 0x50000A90
    assert yft.physics_lod_details[0].groups[0].events.has_any is True
    assert yft.physics_lod_details[0].groups[0].damages_when_broken is True
    assert yft.physics_lod_details[0].groups[0].is_legacy_glass is False
    assert len(yft.physics_lod_details[0].groups[0].children) == 2
    assert len(yft.physics_lod_details[0].children) == 2
    assert len(yft.physics_groups()) == 1
    assert len(yft.physics_children()) == 2
    assert yft.physics_lod_details[0].children[0].undamaged_mass == 10.0
    assert yft.physics_lod_details[0].children[0].vft == FRAG_TYPE_CHILD_VFT
    assert yft.physics_lod_details[0].children[0].resource_state == RESOURCE_STATE
    assert yft.physics_lod_details[0].children[0].damaged_mass == 11.0
    assert yft.physics_lod_details[0].children[0].bone_id == 7
    assert yft.physics_lod_details[0].children[0].owner_group_name == "GroupA"
    assert yft.physics_lod_details[0].children[0].min_breaking_impulse == 100.0
    assert yft.physics_lod_details[0].damping_constants[0].as_tuple() == (
        0.10000000149011612,
        0.20000000298023224,
        0.30000001192092896,
    )
    assert yft.physics_lod_details[0].body_type.pointer == 0x500006E0
    assert yft.physics_lod_details[0].phys_damp_undamaged.pointer == 0x50000800
    assert yft.physics_lod_details[0].phys_damp_damaged.pointer == 0x50000900
    assert yft.physics_lod_details[0].articulated_body_type is not None
    assert yft.physics_lod_details[0].articulated_body_type.num_links == 2
    assert yft.physics_lod_details[0].articulated_body_type.num_joints == 1
    assert yft.physics_lod_details[0].articulated_body_type.locally_owned is True
    assert yft.physics_lod_details[0].undamaged_damp_archetype is not None
    assert (
        yft.physics_lod_details[0].undamaged_damp_archetype.vft
        == FRAG_PHYS_ARCHETYPE_DAMP_VFT
    )
    assert yft.physics_lod_details[0].undamaged_damp_archetype.mass == 10.0
    assert yft.physics_lod_details[0].undamaged_damp_archetype.damping_constants[
        0
    ].as_tuple() == (
        0.699999988079071,
        0.800000011920929,
        0.8999999761581421,
    )
    assert yft.physics_lod_details[0].link_attachments.matrices[0][0] == (
        1.0,
        0.0,
        0.0,
        10.0,
    )
    assert yft.physics_lod_details[0].link_attachments.vft == FRAG_PHYS_TRANSFORMS_VFT
    assert yft.physics_lod_details[0].children[0].undamaged_ang_inertia.as_tuple() == (
        1.0,
        2.0,
        3.0,
        4.0,
    )
    assert yft.physics_lod_details[0].children[0].damaged_ang_inertia.as_tuple() == (
        5.0,
        6.0,
        7.0,
        8.0,
    )
    assert yft.physics_lod_details[0].min_breaking_impulses[:4] == (
        100.0,
        101.0,
        102.0,
        103.0,
    )
    assert yft.physics_lod_details[0].children[0].undamaged_entity_pointer == 0x50000680
    assert yft.physics_lod_details[0].children[0].undamaged_entity is not None
    assert len(yft.physics_lod_details[0].children[0].entities()) == 2
    assert yft.physics_lod_details[0].children[0].uses_bone is True
    assert yft.physics_lod_details[0].children[0].has_damage_state is True
    assert yft.physics_lod_details[0].children[0].undamaged_entity.drawable is not None
    assert (
        yft.physics_lod_details[0].children[0].undamaged_entity.drawable.path
        == "example/physics_high_child_0_undamaged.ydr"
    )
    assert [entity.label for entity in yft.physics_entities()] == [
        "physics_high_child_0_undamaged",
        "physics_high_child_0_damaged",
    ]
    assert [entry.label for entry in yft.physics_drawables()] == [
        "physics_high_child_0_undamaged",
        "physics_high_child_0_damaged",
    ]
    assert yft.physics_lod("high") is yft.physics_lod_details[0]
    assert yft.best_physics_lod is yft.physics_lod_details[0]
    assert yft.physics_lod_details[0].child(0) is yft.physics_lod_details[0].children[0]
    assert (
        yft.physics_lod_details[0].child("GroupA")
        is yft.physics_lod_details[0].children[0]
    )
    assert yft.physics_lod_details[0].children_for_bone(7) == (
        yft.physics_lod_details[0].children[0],
    )
    assert yft.physics_lod_details[0].damageable_groups == (
        yft.physics_lod_details[0].groups[0],
    )
    assert (
        yft.physics_lod_details[0].archetype()
        is yft.physics_lod_details[0].undamaged_damp_archetype
    )
    assert (
        yft.physics_lod_details[0].archetype(damaged=True)
        is yft.physics_lod_details[0].damaged_damp_archetype
    )
    assert yft.physics_lod_details[0].child_entity_pointers == (0x50000680, 0x50000690)
    assert yft.tune_name == "tune_name"
    assert yft.damaged_drawable is yft.drawables[0].drawable
    assert yft.drawable_count == 3
    assert [(entry.label, entry.name) for entry in yft.iter_drawables()] == [
        ("drawable", "drawable"),
        ("extra", "extra"),
        ("drawable_cloth", "drawable_cloth"),
    ]
    assert calls == [
        (0x110, "example/drawable.ydr"),
        (0x690, "example/physics_high_child_0_undamaged.ydr"),
        (0x6A0, "example/physics_high_child_0_damaged.ydr"),
        (0x150, "example/extra.ydr"),
        (0x190, "example/drawable_cloth.ydr"),
    ]
    assert {field.label for field in yft.raw_fields} >= {
        "common_drawable",
        "root_child",
        "tune_name",
    }
    assert build_yft_bytes(yft, lossless=True) == yft.raw_bytes


def test_yft_geometry_summary_aggregates_drawable_meshes():
    mesh_a = YdrMesh(
        positions=[(0.0, 0.0, 0.0)] * 3, indices=[0, 1, 2], material_index=0
    )
    mesh_b = YdrMesh(
        positions=[(0.0, 0.0, 0.0)] * 4, indices=[0, 1, 2, 0, 2, 3], material_index=0
    )
    drawable = Ydr(
        version=162,
        materials=[YdrMaterial(index=0, name="mat")],
        lods={YdrLod.HIGH: [YdrModel(lod=YdrLod.HIGH, meshes=[mesh_a, mesh_b])]},
    )
    yft = Yft(main_drawable=drawable, drawables=[YftDrawable("damaged", drawable)])

    stats = yft.geometry_stats()

    assert stats.drawable_count == 2
    assert stats.mesh_count == 4
    assert stats.vertex_count == 14
    assert stats.triangle_count == 6
    assert stats.material_count == 2
    assert yft.summary()["mesh_count"] == 4


def test_create_yft_declares_simple_fragment():
    drawable = Ydr(version=162, lods={YdrLod.HIGH: [YdrModel(lod=YdrLod.HIGH)]})

    yft = create_yft(
        drawable, name="example_fragment", bounding_sphere=(1.0, 2.0, 3.0, 4.0)
    )

    assert yft.name == "example_fragment"
    assert yft.main_drawable is drawable
    assert yft.bounding_sphere == (1.0, 2.0, 3.0, 4.0)


def test_resource_chunks_match_runtime_page_map():
    flags = get_resource_flags_from_page_counts(
        [1, 2, 3, 4, 5, 1, 1, 1, 1],
        version=10,
        base_shift=4,
    )

    chunks = get_resource_chunk_sizes(flags)

    assert chunks[:3] == (0x200000, 0x100000, 0x100000)
    assert chunks[-4:] == (0x10000, 0x8000, 0x4000, 0x2000)
    assert len(chunks) == 19
    assert sum(chunks) == get_resource_size_from_flags(flags)


def test_yft_binary_validation_rejects_pointer_outside_resource_chunks():
    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                indices=[0, 1, 2],
                material="default",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="default")],
        name="pointer_test",
    )
    raw = build_yft_bytes(create_yft(drawable, name="pointer_test"))
    header, system_data, graphics_data = split_rsc7_sections(raw)
    broken_system = bytearray(system_data)
    struct.pack_into("<Q", broken_system, 0x30, 0x50000000 + header.system_size)
    broken = build_rsc7(
        broken_system,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )

    issues = validate_yft_bytes(broken)

    assert any(
        issue.is_error
        and issue.path == "root.common_drawable"
        and "outside" in issue.message
        for issue in issues
    )

    drawable_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, 0x30)[0]
    )
    lod_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, drawable_offset + 0x50)[0]
    )
    models_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, lod_offset)[0]
    )
    model_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, models_offset)[0]
    )
    geometries_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, model_offset + 0x08)[0]
    )
    geometry_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, geometries_offset)[0]
    )
    broken_system = bytearray(system_data)
    struct.pack_into(
        "<Q",
        broken_system,
        geometry_offset + 0x18,
        0x50000000 + header.system_size,
    )
    broken = build_rsc7(
        broken_system,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )

    issues = validate_yft_bytes(broken)

    assert any(
        issue.is_error
        and issue.path.endswith(".geometries[0].vertex_buffer")
        and "outside" in issue.message
        for issue in issues
    )


def test_yft_without_physics_writes_runtime_root_child_header():
    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                indices=[0, 1, 2],
                material="default",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="default")],
        name="static_fragment",
    )

    raw = build_yft_bytes(create_yft(drawable, name="static_fragment"))
    _, system_data, _ = split_rsc7_sections(raw)
    child_pointer = struct.unpack_from("<Q", system_data, 0x50)[0]

    assert struct.unpack_from(
        "<II", system_data, virtual_to_offset(child_pointer)
    ) == (FRAG_TYPE_CHILD_VFT, RESOURCE_STATE)
    assert validate_yft_bytes(raw) == []


def test_yft_declarative_physics_validation():
    from fivefury.yft import simple_physics_bound

    drawable = Ydr(version=162, lods={YdrLod.HIGH: [YdrModel(lod=YdrLod.HIGH)]})
    child = YftPhysicsChild.declare(
        bone_id=4, undamaged_mass=2.5, min_breaking_impulse=120.0
    )
    group = YftPhysicsGroup.declare(
        "chassis", children=(child,), flags=YftPhysicsGroupFlag.DAMAGE_WHEN_BROKEN
    )
    lod = normalize_physics_lod(
        YftPhysicsLod.declare(groups=(group,)),
        composite_bound=simple_physics_bound(),
    )
    yft = create_yft(
        drawable,
        physics_lods=(lod,),
        physics_bound=lod.composite_bound,
    )

    assert yft.validate() == []
    assert lod.num_children == 1
    assert lod.group("chassis") is not None
    assert lod.children_for_group("chassis")[0].min_breaking_impulse == 120.0

    broken_lod = YftPhysicsLod(
        label="high",
        num_groups=1,
        num_children=0,
        groups=(YftPhysicsGroup(child_index=0, num_children=1),),
    )
    issues = validate_yft(Yft(main_drawable=drawable, physics_lod_details=[broken_lod]))

    assert any(issue.is_error and "child slice" in issue.message for issue in issues)

    invalid_damage = Yft(
        main_drawable=drawable,
        state=YftFragmentState(damaged_drawable_index=0),
    )
    issues = validate_yft(invalid_damage)

    assert any(
        issue.is_error and issue.path == "state.damaged_drawable_index"
        for issue in issues
    )


def test_multichild_prop_does_not_invent_euphoria_body():
    from fivefury.yft import normalize_physics_lod, simple_physics_bound

    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="default",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="default")],
        name="breakable_prop",
    )
    bound = simple_physics_bound()
    drawable.bound = bound
    children = (
        YftPhysicsChild.declare(undamaged_mass=1.0),
        YftPhysicsChild.declare(undamaged_mass=1.0),
    )
    group = YftPhysicsGroup.declare("breakable_prop", children=children)
    lod = normalize_physics_lod(
        YftPhysicsLod.declare("high", groups=(group,)),
        composite_bound=_composite(
            simple_physics_bound(center=(-0.5, 0.0, 0.0)),
            simple_physics_bound(center=(0.5, 0.0, 0.0)),
        ),
    )
    source = create_yft(
        drawable,
        name="breakable_prop",
        physics_lods=(lod,),
        physics_bound=bound,
    )
    parsed = read_yft(
        build_yft_bytes(source),
        resolve_physics_entities=False,
    )

    assert len(lod.children) == 2
    assert lod.articulated_body_type is None
    assert parsed.physics_lod("high").body_type_pointer == 0
    assert parsed.physics_lod("high").articulated_body_type is None


def test_physics_lod_without_damaged_entities_omits_damaged_archetype():
    from fivefury.yft import normalize_physics_lod, simple_physics_bound

    child = YftPhysicsChild.declare(undamaged_mass=1.0)
    group = YftPhysicsGroup.declare("intact_only", children=(child,))
    lod = normalize_physics_lod(
        YftPhysicsLod.declare("high", groups=(group,)),
        composite_bound=simple_physics_bound(),
    )

    assert lod.undamaged_damp_archetype is not None
    assert lod.undamaged_damp_archetype.type_flags == 1
    assert lod.undamaged_damp_archetype.include_flags == 0xFFFFFFFF
    assert lod.num_root_damage_regions == 1
    assert lod.damaged_damp_archetype is None

    invalid = Yft(
        physics_lod_details=[
            dataclasses.replace(
                lod,
                damaged_damp_archetype=YftPhysicsDampArchetype(),
            )
        ]
    )
    assert any(
        issue.is_error
        and issue.path
        == "physics_lod_details[0].damaged_damp_archetype"
        for issue in validate_yft(invalid)
    )


def test_physics_authoring_preserves_root_bone_in_bony_child_prefix():
    from fivefury.yft import normalize_physics_lod, simple_physics_bound

    root_child = YftPhysicsChild.declare(bone_id=0)
    child = YftPhysicsChild.declare(bone_id=17)
    group = YftPhysicsGroup.declare("root", children=(root_child, child))
    declared = YftPhysicsLod.declare("high", groups=(group,))

    normalized = normalize_physics_lod(
        declared,
        composite_bound=_composite(
            simple_physics_bound(center=(-0.5, 0.0, 0.0)),
            simple_physics_bound(center=(0.5, 0.0, 0.0)),
        ),
    )

    assert normalized.num_bony_children == 2
    assert normalized.children[0].follows_root


def test_physics_lods_own_distinct_child_drawable_bound_links():
    from fivefury.yft import simple_physics_bound

    def drawable(name: str):
        return create_ydr(
            meshes=[
                YdrMeshInput(
                    positions=[
                        (0.0, 0.0, 0.0),
                        (1.0, 0.0, 0.0),
                        (0.0, 1.0, 0.0),
                    ],
                    indices=[0, 1, 2],
                    material="body",
                    texcoords=[
                        [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
                    ],
                )
            ],
            materials=[YdrMaterialInput(name="body")],
            name=name,
        )

    high_child = YftPhysicsChild.declare()
    medium_child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(
            drawable("medium_physics"),
            label="medium_physics",
        )
    )
    source = create_yft(
        drawable("multi_lod"),
        name="multi_lod",
        physics_lods=(
            YftPhysicsLod.declare(
                "high",
                groups=(YftPhysicsGroup.declare("high", children=(high_child,)),),
            ),
            YftPhysicsLod.declare(
                "medium",
                groups=(
                    YftPhysicsGroup.declare(
                        "medium",
                        children=(medium_child,),
                    ),
                ),
            ),
        ),
        physics_bound=simple_physics_bound(),
    )

    raw = build_yft_bytes(source)
    _, system_data, _ = split_rsc7_sections(raw)
    parsed = read_yft(raw, resolve_physics_entities=False)
    high = parsed.physics_lod("high")
    medium = parsed.physics_lod("medium")
    high_entity = high.children[0].undamaged_entity_pointer
    medium_entity = medium.children[0].undamaged_entity_pointer

    assert high_entity != medium_entity
    assert struct.unpack_from(
        "<Q",
        system_data,
        virtual_to_offset(high_entity) + 0xF0,
    )[0] == _bound_child_pointer(
        system_data,
        high.composite_bounds_pointer,
    )
    assert struct.unpack_from(
        "<Q",
        system_data,
        virtual_to_offset(medium_entity) + 0xF0,
    )[0] == _bound_child_pointer(
        system_data,
        medium.composite_bounds_pointer,
    )
    assert validate_yft_bytes(raw) == []


def test_composite_bound_may_preserve_only_null_native_slots():
    composite = BoundComposite(
        bound_type=10,
        sphere_radius=0.0,
        box_max=(0.0, 0.0, 0.0),
        margin=0.0,
        box_min=(0.0, 0.0, 0.0),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
        children=[
            BoundChild(None),
            BoundChild(None),
        ]
    )

    assert "Composite bound has no non-null children" not in composite.validate()


def test_bound_ownership_counts_external_roots_and_composite_edges_once():
    def composite(children):
        return BoundComposite(
            bound_type=10,
            sphere_radius=0.0,
            box_max=(0.0, 0.0, 0.0),
            margin=0.0,
            box_min=(0.0, 0.0, 0.0),
            box_center=(0.0, 0.0, 0.0),
            sphere_center=(0.0, 0.0, 0.0),
            children=children,
        )

    nested_leaf = BoundBox.from_bounds((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))
    nested = composite([BoundChild(nested_leaf), BoundChild(None)])
    sibling = BoundBox.from_bounds((-2.0, -2.0, -2.0), (2.0, 2.0, 2.0))
    root = composite([BoundChild(nested), BoundChild(sibling)])

    counts = calculate_bound_ref_counts((root, root, nested))

    assert counts[id(root)] == 2
    assert counts[id(nested)] == 2
    assert counts[id(nested_leaf)] == 1
    assert counts[id(sibling)] == 1


def test_yft_writer_derives_direct_bound_ownership_and_roundtrips_it():
    from fivefury.yft import simple_physics_bound

    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                indices=[0, 1, 2],
                material="body",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="body")],
        name="owned_bound",
    )
    bound = simple_physics_bound()
    source = create_yft(
        drawable,
        name="owned_bound",
        physics_lods=(
            YftPhysicsLod.declare(
                "high",
                groups=(
                    YftPhysicsGroup.declare(
                        "root",
                        children=(YftPhysicsChild.declare(),),
                    ),
                ),
            ),
        ),
        physics_bound=bound,
    )

    assert source.physics_lod("high").composite_bound.ref_count == 2
    assert bound.ref_count == 2
    parsed = read_yft(build_yft_bytes(source), resolve_physics_entities=False)
    assert parsed.physics_lod("high").composite_bound.ref_count == 2
    assert parsed.physics_lod("high").composite_bound.children[0].bound.ref_count == 2


def test_yft_validation_rejects_bound_ref_count_mismatch():
    from fivefury.yft import normalize_physics_lod, simple_physics_bound

    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                indices=[0, 1, 2],
                material="body",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="body")],
        name="bad_ownership",
    )
    bound = simple_physics_bound()
    lod = normalize_physics_lod(
        YftPhysicsLod.declare(
            "high",
            groups=(
                YftPhysicsGroup.declare(
                    "root",
                    children=(YftPhysicsChild.declare(),),
                ),
            ),
        ),
        composite_bound=bound,
    )
    bound.ref_count = 1

    issues = validate_yft(Yft(main_drawable=drawable, physics_lod_details=[lod]))

    assert any(
        issue.is_error and issue.path.endswith("ref_count") for issue in issues
    )


def test_atomic_write_preserves_existing_file_when_replace_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "asset.bin"
    target.write_bytes(b"stable")

    def fail_replace(_source, _destination) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("fivefury.common.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write_bytes(target, b"partial")

    assert target.read_bytes() == b"stable"
    assert not list(tmp_path.glob(".asset.bin.*.tmp"))


def test_resource_pointer_validation_checks_section_and_extent():
    system_flags = get_resource_flags_from_page_counts(
        [1, 0, 0, 0, 0, 0, 0, 0, 0],
        1,
    )
    graphics_flags = get_resource_flags_from_page_counts(
        [1, 0, 0, 0, 0, 0, 0, 0, 0],
        1,
    )
    header = ResourceHeader(1, system_flags, graphics_flags)

    assert validate_resource_pointer(header, 0x50000000, section="system") is not None
    assert validate_resource_pointer(header, 0, nullable=True) is None
    with pytest.raises(ValueError, match="outside"):
        validate_resource_pointer(header, 0x4057C038)
    with pytest.raises(ValueError, match="instead of system"):
        validate_resource_pointer(header, 0x60000000, section="system")


def test_physics_lod_with_damaged_entity_synthesizes_damaged_archetype():
    from fivefury.yft import normalize_physics_lod, simple_physics_bound

    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="damaged",
            )
        ],
        materials=[YdrMaterialInput(name="damaged")],
        name="damaged_piece",
    )
    child = YftPhysicsChild.declare(
        damaged_entity=YftPhysicsEntity.declare(drawable),
        damaged_mass=1.0,
    )
    group = YftPhysicsGroup.declare("two_state", children=(child,))
    lod = normalize_physics_lod(
        YftPhysicsLod.declare("high", groups=(group,)),
        composite_bound=simple_physics_bound(),
    )

    assert lod.damaged_damp_archetype is not None


def test_damaged_archetype_owns_a_distinct_bound_resource():
    from fivefury.yft import simple_physics_bound

    drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="body",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="body")],
        name="two_state_prop",
    )
    bound = simple_physics_bound()
    child = YftPhysicsChild.declare(undamaged_mass=1.0, damaged_mass=1.0)
    group = YftPhysicsGroup.declare("body", children=(child,))
    source = create_yft(
        drawable,
        name="two_state_prop",
        damaged_drawable=drawable,
        physics_lods=(YftPhysicsLod.declare("high", groups=(group,)),),
        physics_bound=bound,
    )
    lod = source.physics_lod_details[0]
    source.physics_lod_details[0] = dataclasses.replace(
        lod,
        damaged_damp_archetype=YftPhysicsDampArchetype(
            resource_type=2,
            mass=1.0,
            inv_mass=1.0,
            gravity_factor=1.0,
        ),
    )

    raw = build_yft_bytes(source)
    header, system_data, graphics_data = split_rsc7_sections(raw)
    parsed = read_yft(raw, resolve_physics_entities=False)
    parsed_lod = parsed.physics_lod("high")
    undamaged_bound = parsed_lod.undamaged_damp_archetype.bound_pointer
    damaged_bound = parsed_lod.damaged_damp_archetype.bound_pointer

    assert undamaged_bound == parsed_lod.composite_bounds_pointer
    assert damaged_bound != undamaged_bound
    assert struct.unpack_from(
        "<I",
        system_data,
        virtual_to_offset(undamaged_bound) + 0x3C,
    )[0] == 2
    assert struct.unpack_from(
        "<I",
        system_data,
        virtual_to_offset(damaged_bound) + 0x3C,
    )[0] == 1
    assert validate_yft_bytes(raw) == []

    broken_system = bytearray(system_data)
    damaged_damp_offset = virtual_to_offset(
        parsed_lod.phys_damp_damaged_pointer
    )
    struct.pack_into(
        "<Q",
        broken_system,
        damaged_damp_offset + 0x20,
        undamaged_bound,
    )
    broken = build_rsc7(
        broken_system,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )

    assert any(
        issue.is_error
        and issue.path
        == "physics_lods.high.damaged_damp_archetype.bound"
        and "must not share" in issue.message
        for issue in validate_yft_bytes(broken)
    )


def test_composite_bound_ownership_covers_nested_null_and_damage_states():
    def drawable(name: str):
        return create_ydr(
            meshes=[
                YdrMeshInput(
                    positions=[
                        (0.0, 0.0, 0.0),
                        (1.0, 0.0, 0.0),
                        (0.0, 1.0, 0.0),
                    ],
                    indices=[0, 1, 2],
                    material="body",
                    texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
                )
            ],
            materials=[YdrMaterialInput(name="body")],
            name=name,
        )

    intact_piece = BoundBox.from_center_size((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    unlinked_piece = BoundBox.from_center_size((2.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    composite = BoundComposite(
        bound_type=10,
        sphere_radius=0.0,
        box_max=(0.0, 0.0, 0.0),
        margin=0.0,
        box_min=(0.0, 0.0, 0.0),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
        children=[
            BoundChild(intact_piece),
            BoundChild(unlinked_piece),
            BoundChild(None),
        ],
    ).build()
    linked_child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(drawable("intact_physics")),
        damaged_entity=YftPhysicsEntity.declare(drawable("damaged_physics")),
    )
    source = create_yft(
        drawable("composite_owner"),
        name="composite_owner",
        physics_lods=(
            YftPhysicsLod.declare(
                "high",
                groups=(
                    YftPhysicsGroup.declare(
                        "parts",
                        children=(
                            linked_child,
                            YftPhysicsChild.declare(),
                            YftPhysicsChild.declare(),
                        ),
                    ),
                ),
            ),
        ),
        physics_bound=composite,
        physics_bound_profile=YftPhysicsBoundProfile.SET_PIECE,
    )

    raw = build_yft_bytes(source)
    _, system_data, _ = split_rsc7_sections(raw)
    parsed = read_yft(raw, resolve_physics_entities=False)
    lod = parsed.physics_lod("high")
    root_offset = virtual_to_offset(lod.composite_bounds_pointer)
    child_array = virtual_to_offset(struct.unpack_from("<Q", system_data, root_offset + 0x70)[0])
    child_pointers = struct.unpack_from("<3Q", system_data, child_array)

    assert struct.unpack_from("<I", system_data, root_offset + 0x3C)[0] == 2
    assert struct.unpack_from(
        "<I",
        system_data,
        virtual_to_offset(child_pointers[0]) + 0x3C,
    )[0] == 2
    assert struct.unpack_from(
        "<I",
        system_data,
        virtual_to_offset(child_pointers[1]) + 0x3C,
    )[0] == 1
    assert child_pointers[2] == 0


def test_partial_damage_uses_sparse_damaged_composite_children():
    from fivefury.yft import simple_physics_bound

    def drawable(name: str):
        result = create_ydr(
            meshes=[
                YdrMeshInput(
                    positions=[
                        (0.0, 0.0, 0.0),
                        (1.0, 0.0, 0.0),
                        (0.0, 1.0, 0.0),
                    ],
                    indices=[0, 1, 2],
                    material="body",
                    texcoords=[
                        [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
                    ],
                )
            ],
            materials=[YdrMaterialInput(name="body")],
            name=name,
        )
        result.bound = simple_physics_bound()
        return result

    main = drawable("partial_damage")
    damaged_main = drawable("partial_damage_damaged")
    intact_only = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(
            drawable("intact_only"),
        ),
    )
    damageable = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(
            drawable("damageable"),
        ),
        damaged_entity=YftPhysicsEntity.declare(
            drawable("damageable_damaged"),
        ),
    )
    damaged_only = YftPhysicsChild.declare(
        damaged_entity=YftPhysicsEntity.declare(
            drawable("damaged_only"),
        ),
    )
    group = YftPhysicsGroup.declare(
        "root",
        children=(intact_only, damageable, damaged_only),
    )
    composite = BoundComposite(
        bound_type=10,
        sphere_radius=2.0,
        box_max=(2.0, 2.0, 2.0),
        margin=0.0,
        box_min=(-2.0, -2.0, -2.0),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
        children=[
            BoundChild(
                simple_physics_bound(center=(-0.5, 0.0, 0.0)),
            ),
            BoundChild(
                simple_physics_bound(center=(0.5, 0.0, 0.0)),
            ),
            BoundChild(
                None,
                bounds=BoundAabb(
                    minimum=(0.0, 0.0, 0.0),
                    maximum=(0.0, 0.0, 0.0),
                ),
            ),
        ]
    ).build()
    source = create_yft(
        main,
        name="partial_damage",
        damaged_drawable=damaged_main,
        physics_lods=(YftPhysicsLod.declare("high", groups=(group,)),),
        physics_bound=composite,
        physics_bound_profile=YftPhysicsBoundProfile.SET_PIECE,
    )

    raw = build_yft_bytes(source)
    header, system_data, graphics_data = split_rsc7_sections(raw)
    parsed = read_yft(raw, resolve_physics_entities=False)
    lod = parsed.physics_lod("high")
    damaged_bound_offset = virtual_to_offset(
        lod.damaged_damp_archetype.bound_pointer
    )
    damaged_children_pointer = struct.unpack_from(
        "<Q",
        system_data,
        damaged_bound_offset + 0x70,
    )[0]
    damaged_children_offset = virtual_to_offset(damaged_children_pointer)
    damaged_bound_children = struct.unpack_from(
        "<QQQ",
        system_data,
        damaged_children_offset,
    )
    damaged_child_bounds_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, damaged_bound_offset + 0x88)[0]
    )
    damaged_flags1_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, damaged_bound_offset + 0x90)[0]
    )
    damaged_flags2_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, damaged_bound_offset + 0x98)[0]
    )

    assert damaged_bound_children[0] == 0
    assert damaged_bound_children[1] != 0
    assert damaged_bound_children[2] != 0
    null_bounds = struct.unpack_from(
        "<8f",
        system_data,
        damaged_child_bounds_offset,
    )
    assert null_bounds[0:3] == (0.0, 0.0, 0.0)
    assert null_bounds[4:8] == (0.0, 0.0, 0.0, 0.0)
    assert struct.unpack_from(
        "<II",
        system_data,
        damaged_flags1_offset,
    ) == (0, 0)
    assert struct.unpack_from(
        "<II",
        system_data,
        damaged_flags2_offset,
    ) == (0, 0)
    assert lod.composite_bound.children[2].bound is None
    assert validate_yft_bytes(raw) == []

    invalid_null_metadata_system = bytearray(system_data)
    struct.pack_into(
        "<f",
        invalid_null_metadata_system,
        damaged_child_bounds_offset,
        float("nan"),
    )
    invalid_null_metadata = build_rsc7(
        invalid_null_metadata_system,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )
    assert any(
        issue.is_error
        and issue.path
        == (
            "physics_lods.high.damaged_damp_archetype.bound"
            ".children[0].bounds"
        )
        for issue in validate_yft_bytes(invalid_null_metadata)
    )

    undamaged_bound_offset = virtual_to_offset(
        lod.undamaged_damp_archetype.bound_pointer
    )
    undamaged_children_pointer = struct.unpack_from(
        "<Q",
        system_data,
        undamaged_bound_offset + 0x70,
    )[0]
    undamaged_children_offset = virtual_to_offset(
        undamaged_children_pointer
    )
    invalid_child_pointer = struct.unpack_from(
        "<Q",
        system_data,
        undamaged_children_offset,
    )[0]
    broken_system = bytearray(system_data)
    struct.pack_into(
        "<Q",
        broken_system,
        damaged_children_offset,
        invalid_child_pointer,
    )
    broken = build_rsc7(
        broken_system,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )

    assert any(
        issue.is_error
        and issue.path
        == (
            "physics_lods.high.damaged_damp_archetype.bound"
            ".children[0]"
        )
        for issue in validate_yft_bytes(broken)
    )


def test_materialless_physics_drawable_uses_null_shader_group():
    main_drawable = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                ],
                indices=[0, 1, 2],
                material="body",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="body")],
        name="breakable_prop",
    )
    child_bound = BoundBox.from_center_size(
        (0.0, 0.0, 0.0),
        (2.0, 2.0, 2.0),
    ).build()
    child_drawable = create_ydr(
        meshes=[],
        materials=[],
        bound=child_bound,
        name="collision_piece",
    )
    child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(
            child_drawable,
            label="collision_piece",
        ),
        undamaged_mass=1.0,
    )
    group = YftPhysicsGroup.declare("collision_piece", children=(child,))
    source = create_yft(
        main_drawable,
        name="breakable_prop",
        physics_lods=(YftPhysicsLod.declare("high", groups=(group,)),),
        physics_bound=child_bound,
    )

    raw = build_yft_bytes(source)
    _, system_data, _ = split_rsc7_sections(raw)
    parsed = read_yft(raw)
    parsed_child = parsed.physics_lod("high").children[0]
    parsed_drawable = parsed_child.undamaged_entity.drawable
    drawable_offset = virtual_to_offset(parsed_child.undamaged_entity.pointer)

    assert parsed_drawable.shader_group_pointer == 0
    assert parsed_drawable.materials == []
    assert struct.unpack_from("<Q", system_data, drawable_offset + 0x10)[0] == 0
    assert validate_yft_bytes(raw) == []


def test_damaged_drawable_inherits_common_shader_group_and_remaps_materials():
    triangle = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
    ]
    texcoords = [[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]]
    main = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=triangle,
                indices=[0, 1, 2],
                material="body",
                texcoords=texcoords,
            )
        ],
        materials=[YdrMaterialInput(name="body", render_bucket=0)],
        name="shared_shader_fragment",
    )
    damaged = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=triangle,
                indices=[0, 1, 2],
                material="damage_only",
                texcoords=texcoords,
            ),
            YdrMeshInput(
                positions=triangle,
                indices=[0, 1, 2],
                material="body_alias",
                texcoords=texcoords,
            ),
        ],
        materials=[
            YdrMaterialInput(name="damage_only", shader="emissive.sps"),
            YdrMaterialInput(name="body_alias"),
        ],
        name="shared_shader_fragment_damaged",
    )

    raw = build_yft_bytes(
        create_yft(
            main,
            damaged_drawable=damaged,
            name="shared_shader_fragment",
        )
    )
    header, system_data, graphics_data = split_rsc7_sections(raw)
    main_offset = virtual_to_offset(struct.unpack_from("<Q", system_data, 0x30)[0])
    main_shader_group = struct.unpack_from("<Q", system_data, main_offset + 0x10)[0]
    main_shader_group_offset = virtual_to_offset(main_shader_group)
    extra_array_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, 0x38)[0]
    )
    damaged_pointer = struct.unpack_from("<Q", system_data, extra_array_offset)[0]
    damaged_offset = virtual_to_offset(damaged_pointer)
    damaged_lod_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, damaged_offset + 0x50)[0]
    )
    damaged_models_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, damaged_lod_offset)[0]
    )
    damaged_model_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, damaged_models_offset)[0]
    )
    damaged_mapping_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, damaged_model_offset + 0x20)[0]
    )

    assert struct.unpack_from("<H", system_data, main_shader_group_offset + 0x18)[0] == 2
    assert struct.unpack_from("<Q", system_data, damaged_offset + 0x10)[0] == 0
    assert struct.unpack_from("<2H", system_data, damaged_mapping_offset) == (1, 0)
    assert validate_yft_bytes(raw) == []

    parsed = read_yft(raw)
    parsed_damaged = parsed.damaged_drawable
    assert parsed_damaged is not None
    assert parsed_damaged.materials == parsed.main_drawable.materials
    assert [
        mesh.material_index
        for model in parsed_damaged.lods[YdrLod.HIGH]
        for mesh in model.meshes
    ] == [1, 0]
    assert all(
        mesh.material is parsed.main_drawable.materials[mesh.material_index]
        for model in parsed_damaged.lods[YdrLod.HIGH]
        for mesh in model.meshes
    )

    broken_system = bytearray(system_data)
    struct.pack_into("<Q", broken_system, damaged_offset + 0x10, main_shader_group)
    broken = build_rsc7(
        broken_system,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )
    assert any(
        issue.is_error
        and issue.path == "root.extra_drawables[0].shader_group"
        and "must inherit" in issue.message
        for issue in validate_yft_bytes(broken)
    )


def test_create_yft_writes_declared_physics_lod(tmp_path):
    build = create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                indices=[0, 1, 2],
                material="body",
                texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
            )
        ],
        materials=[YdrMaterialInput(name="body")],
        name="fragment_drawable",
    )
    bound = BoundBox.from_center_size((0.0, 0.0, 0.0), (2.0, 2.0, 2.0)).build()
    build.bound = bound
    child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity(
            pointer=0x5000DEAD,
            label="body_fragment",
            drawable=build,
        ),
        undamaged_mass=10.0,
        min_breaking_impulse=100.0,
        reserved_flags=0,
    )
    group = YftPhysicsGroup.declare(
        "body",
        children=(child,),
        flags=YftPhysicsGroupFlag.DAMAGE_WHEN_BROKEN,
    )
    yft = create_yft(
        build,
        name="fragment",
        damaged_drawable=build,
        physics_lods=(YftPhysicsLod.declare("high", groups=(group,)),),
        physics_bound=bound,
    )
    yft.tune_name = "fragment_tune"
    yft.state = dataclasses.replace(
        yft.state,
        entity_class=2,
        client_class_id=123,
        unbroken_elasticity=0.25,
        gravity_factor=0.5,
        buoyancy_factor=0.75,
        glass_attachment_bone=4,
    )

    raw = build_yft_bytes(yft)
    header, system_data, graphics_data = split_rsc7_sections(raw)
    target = tmp_path / "fragment.yft"
    target.write_bytes(raw)
    parsed = read_yft(target, resolve_physics_entities=False)
    parsed_with_entities = read_yft(target)

    assert parsed.physics_lods.has_physics is True
    # A physics child with its own drawable must not also be installed as the
    # fragment root child. GTA V would resource-construct the same child and
    # drawable twice, then try to fix up an already-relocated pointer.
    assert parsed.root_child is None
    assert isinstance(parsed.main_drawable, YftFragmentDrawable)
    assert parsed.main_drawable.bound is not None
    assert parsed.main_drawable.skeleton_type_name == "fragment_drawable"
    assert parsed.main_drawable.fragment_matrix == YftFragmentMatrix.identity()
    assert parsed.state.damaged_drawable_index == 0
    assert parsed.damaged_drawable is parsed.drawables[0].drawable
    assert parsed.tune_name == "fragment_tune"
    assert parsed.state == YftFragmentState(
        damaged_drawable_index=0,
        entity_class=2,
        client_class_id=123,
        unbroken_elasticity=0.25,
        gravity_factor=0.5,
        buoyancy_factor=0.75,
        glass_attachment_bone=4,
    )
    assert struct.unpack_from("<i", system_data, 0x4C)[0] == 0
    assert struct.unpack_from("<Q", system_data, 0x50)[0] == 0
    assert struct.unpack_from("<Q", system_data, 0x58)[0] != 0
    assert struct.unpack_from("<fff", system_data, 0xCC) == (0.25, 0.5, 0.75)
    drawable_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, 0x30)[0]
    )
    shader_group_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, drawable_offset + 0x10)[0]
    )
    lod_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, drawable_offset + 0x50)[0]
    )
    model_array_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, lod_offset)[0]
    )
    model_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, model_array_offset)[0]
    )
    geometry_array_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, model_offset + 0x08)[0]
    )
    geometry_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, geometry_array_offset)[0]
    )
    vertex_buffer_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, geometry_offset + 0x18)[0]
    )
    index_buffer_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, geometry_offset + 0x38)[0]
    )
    for offset, expected_vft in (
        (drawable_offset, LEGACY_FRAGMENT_DRAWABLE_HEADERS.drawable),
        (shader_group_offset, LEGACY_FRAGMENT_DRAWABLE_HEADERS.shader_group),
        (model_offset, LEGACY_FRAGMENT_DRAWABLE_HEADERS.model),
        (geometry_offset, LEGACY_FRAGMENT_DRAWABLE_HEADERS.geometry),
        (vertex_buffer_offset, LEGACY_FRAGMENT_DRAWABLE_HEADERS.vertex_buffer),
        (index_buffer_offset, LEGACY_FRAGMENT_DRAWABLE_HEADERS.index_buffer),
    ):
        assert struct.unpack_from("<II", system_data, offset) == (
            expected_vft,
            RESOURCE_STATE,
        )
    assert parsed.physics_lod("high") is not None
    lod = parsed.physics_lod("high")
    assert lod.num_children == 1
    assert lod.groups[0].name == "body"
    assert lod.groups[0].damages_when_broken is True
    assert lod.children[0].flags == 0
    assert lod.children[0].undamaged_entity_pointer != 0x5000DEAD
    assert (
        parsed_with_entities.physics_lod("high").children[0].undamaged_entity.drawable
        is not None
    )
    assert lod.children[0].min_breaking_impulse == 100.0
    assert lod.composite_bound is not None
    assert lod.link_attachments.count == 1
    assert lod.link_attachments.matrices[0][3] == (0.0, 0.0, 0.0, 1.0)
    assert lod.undamaged_damp_archetype is not None
    assert lod.damaged_damp_archetype is not None
    undamaged_entity_offset = virtual_to_offset(
        lod.children[0].undamaged_entity_pointer
    )
    damaged_entity_offset = virtual_to_offset(
        lod.children[0].damaged_entity_pointer
    )
    assert struct.unpack_from(
        "<Q",
        system_data,
        undamaged_entity_offset + 0xF0,
    )[0] == _bound_child_pointer(
        system_data,
        lod.undamaged_damp_archetype.bound_pointer,
    )
    assert struct.unpack_from(
        "<Q",
        system_data,
        damaged_entity_offset + 0xF0,
    )[0] == _bound_child_pointer(
        system_data,
        lod.damaged_damp_archetype.bound_pointer,
    )

    broken_system = bytearray(system_data)
    struct.pack_into("<Q", broken_system, undamaged_entity_offset + 0xF0, 0)
    broken_bound_link = build_rsc7(
        broken_system,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )
    assert any(
        issue.is_error
        and issue.path
        == "physics_lods.high.children[0].undamaged_entity.bound"
        and "matching archetype bound child" in issue.message
        for issue in validate_yft_bytes(broken_bound_link)
    )
    lod_offset = virtual_to_offset(lod.pointer)
    child_offset = virtual_to_offset(lod.child_pointers[0])
    transforms_offset = virtual_to_offset(lod.link_attachments_pointer)
    damp_offset = virtual_to_offset(lod.phys_damp_undamaged_pointer)
    group_names_offset = virtual_to_offset(lod.group_names_pointer)
    assert struct.unpack_from("<II", system_data, lod_offset) == (
        FRAG_PHYSICS_LOD_VFT,
        RESOURCE_STATE,
    )
    assert struct.unpack_from("<II", system_data, child_offset) == (
        FRAG_TYPE_CHILD_VFT,
        RESOURCE_STATE,
    )
    assert struct.unpack_from("<II", system_data, transforms_offset) == (
        FRAG_PHYS_TRANSFORMS_VFT,
        RESOURCE_STATE,
    )
    assert struct.unpack_from("<II", system_data, damp_offset) == (
        FRAG_PHYS_ARCHETYPE_DAMP_VFT,
        RESOURCE_STATE,
    )
    assert struct.unpack_from(
        "<Q", system_data, group_names_offset + lod.num_groups * 8
    )[0] == 0
    assert parsed.validate() == []

    physics_drawable = next(parsed_with_entities.iter_physics_drawables()).drawable
    physics_drawable.extra_bounds = (None,) * 65
    physics_drawable.extra_bound_matrices = (
        YftFragmentMatrix.identity(),
    ) * 65
    assert any(
        issue.is_error
        and issue.path.endswith(".extra_bounds")
        and "more than 64 bounds" in issue.message
        for issue in parsed_with_entities.validate()
    )

    parsed.main_drawable.extra_bounds = (
        BoundBox.from_bounds(
            (-0.5, -0.5, -0.5),
            (0.5, 0.5, 0.5),
        ).build(),
    )
    parsed.main_drawable.extra_bound_matrices = (YftFragmentMatrix.identity(),)
    rebuilt = build_yft_bytes(parsed)
    reparsed = read_yft(
        rebuilt,
        resolve_physics_entities=False,
    )

    assert len(reparsed.main_drawable.extra_bounds) == 1
    assert isinstance(reparsed.main_drawable.extra_bounds[0], BoundBox)
    assert reparsed.main_drawable.extra_bound_matrices == (
        YftFragmentMatrix.identity(),
    )
    assert validate_yft_bytes(rebuilt) == []

    rebuilt_header, rebuilt_system, rebuilt_graphics = split_rsc7_sections(rebuilt)
    rebuilt_drawable = virtual_to_offset(
        struct.unpack_from("<Q", rebuilt_system, 0x30)[0]
    )
    extra_bounds_array = virtual_to_offset(
        struct.unpack_from("<Q", rebuilt_system, rebuilt_drawable + 0xF8)[0]
    )
    broken_system = bytearray(rebuilt_system)
    struct.pack_into("<Q", broken_system, extra_bounds_array, 7)
    broken_extra_bound = build_rsc7(
        broken_system,
        version=rebuilt_header.version,
        graphics_data=rebuilt_graphics,
        system_flags=rebuilt_header.system_flags,
        graphics_flags=rebuilt_header.graphics_flags,
    )
    assert any(
        issue.is_error
        and issue.path == "root.common_drawable.extra_bounds[0]"
        and "outside the system and graphics virtual spaces" in issue.message
        for issue in validate_yft_bytes(broken_extra_bound)
    )

    spare_capacity_system = bytearray(rebuilt_system)
    struct.pack_into("<Q", spare_capacity_system, extra_bounds_array + 8, 0)
    struct.pack_into("<HH", spare_capacity_system, rebuilt_drawable + 0x100, 2, 2)
    spare_capacity = build_rsc7(
        spare_capacity_system,
        version=rebuilt_header.version,
        graphics_data=rebuilt_graphics,
        system_flags=rebuilt_header.system_flags,
        graphics_flags=rebuilt_header.graphics_flags,
    )
    spare_capacity_parsed = read_yft(spare_capacity)
    assert len(spare_capacity_parsed.main_drawable.extra_bounds) == 1
    assert len(spare_capacity_parsed.main_drawable.extra_bound_matrices) == 1
    assert validate_yft_bytes(spare_capacity) == []

    invalid_active_count_system = bytearray(spare_capacity_system)
    struct.pack_into("<H", invalid_active_count_system, rebuilt_drawable + 0x110, 3)
    invalid_active_count = build_rsc7(
        invalid_active_count_system,
        version=rebuilt_header.version,
        graphics_data=rebuilt_graphics,
        system_flags=rebuilt_header.system_flags,
        graphics_flags=rebuilt_header.graphics_flags,
    )
    assert any(
        issue.is_error
        and issue.path == "root.common_drawable.extra_bounds"
        and "active count 3 exceeds array count 2" in issue.message
        for issue in validate_yft_bytes(invalid_active_count)
    )
    with pytest.raises(ValueError, match="extra-bound count exceeds array count"):
        read_yft(invalid_active_count)


def test_yft_corpus_scanner_reports_unreadable_paths(tmp_path):
    broken = tmp_path / "broken.yft"
    broken.write_bytes(b"not a resource")

    result = scan_yft_corpus((tmp_path,))

    assert result[0].path == broken
    assert result[0].readable is False
    assert "RSC7" in result[0].error or "short" in result[0].error


def test_yft_articulated_joints_roundtrip():
    from fivefury.resource import ResourceWriter
    from fivefury.yft import (
        IDENTITY_MATRIX44,
        YftPhysicsJoint1Dof,
        YftPhysicsJoint3Dof,
        YftPhysicsJointType,
    )
    from fivefury.yft.physics_reader import read_physics_joint
    from fivefury.yft.physics_writer import _write_physics_joint

    joints = (
        YftPhysicsJoint1Dof(
            parent_link_index=0,
            child_link_index=1,
            orientation_parent=IDENTITY_MATRIX44,
            orientation_child=IDENTITY_MATRIX44,
            hard_angle_min=-0.5,
            hard_angle_max=0.75,
        ),
        YftPhysicsJoint3Dof(
            parent_link_index=1,
            child_link_index=2,
            orientation_parent=IDENTITY_MATRIX44,
            orientation_child=IDENTITY_MATRIX44,
            hard_first_lean_angle_max=0.25,
            hard_second_lean_angle_max=0.5,
            hard_twist_angle_max=1.0,
            use_child_for_twist_axis=True,
        ),
    )
    writer = ResourceWriter(initial_size=0)
    offsets = [_write_physics_joint(writer, joint) for joint in joints]
    data = writer.finish()

    one_dof = read_physics_joint(
        data, 0x50000000 + offsets[0], YftPhysicsJointType.ONE_DOF
    )
    three_dof = read_physics_joint(
        data, 0x50000000 + offsets[1], YftPhysicsJointType.THREE_DOF
    )

    assert one_dof.parent_link_index == 0
    assert one_dof.hard_angle_min == -0.5
    assert one_dof.hard_angle_max == 0.75
    assert three_dof.parent_link_index == 1
    assert three_dof.hard_twist_angle_max == 1.0
    assert three_dof.use_child_for_twist_axis is True


def test_yft_validation_rejects_unwritable_resource_graphs():
    yft = Yft()
    yft.pointers.collision_event_set = 0x50000100

    issues = validate_yft(yft)

    assert any(
        issue.is_error and issue.path == "collision_event_set" for issue in issues
    )


def test_yft_empty_event_sets_roundtrip():
    event_set = YftEventSet.declare()
    child = YftPhysicsChild.declare()
    child = dataclasses.replace(
        child,
        events=child.events.declare(continuous=event_set),
    )
    group = YftPhysicsGroup.declare("body", children=(child,))
    drawable = Ydr(
        version=162,
        lods={YdrLod.HIGH: [YdrModel(lod=YdrLod.HIGH)]},
    )
    bound = BoundBox.from_center_size(
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0),
    ).build()
    drawable.bound = bound
    yft = create_yft(
        drawable,
        name="event_fragment",
        physics_lods=(YftPhysicsLod.declare("high", groups=(group,)),),
        physics_bound=bound,
    )

    parsed = read_yft(
        build_yft_bytes(yft),
        resolve_physics_entities=False,
    )
    parsed_event = parsed.physics_lod("high").children[0].events.continuous

    assert parsed_event is not None
    assert parsed_event.resource_tag == 0x74536353
    assert parsed_event.is_empty is True
    assert parsed.validate() == []


def test_fragment_geometry_bound_builder_creates_direct_prop_leaf():
    geometry = build_fragment_geometry_bound(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ],
        [
            (0, 2, 1),
            (0, 1, 3),
            (1, 2, 3),
            (2, 0, 3),
        ],
        materials=[BoundMaterial(type=0)],
    )

    assert type(geometry) is BoundGeometry
    assert geometry.file_vft == 0x4062D258
    assert geometry.vertices_shrunk == geometry.vertices
    assert geometry.octants is not None
    assert geometry.volume == pytest.approx(1.0 / 6.0)
    assert geometry.box_center == pytest.approx((0.5, 0.5, 0.5))
    assert geometry.sphere_center == pytest.approx((0.25, 0.25, 0.25))
    assert geometry.sphere_radius == pytest.approx(
        math.sqrt((0.75**2) + (0.25**2) + (0.25**2))
    )
    assert all(math.isfinite(value) and value > 0.0 for value in geometry.angular_inertia)


def test_fragment_geometry_bound_builder_rejects_packed_material_overflow():
    with pytest.raises(ValueError, match="room_id"):
        build_fragment_geometry_bound(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
            ],
            [(0, 1, 2)],
            materials=[BoundMaterial(room_id=0x20)],
        )


def test_prop_profile_writes_native_composite_and_geometry_vfts():
    geometry = build_fragment_geometry_bound(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ],
        [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)],
    )
    drawable = _simple_fragment_drawable("prop_profile")
    child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(
            drawable,
            label="prop_profile",
        )
    )
    source = create_yft(
        drawable,
        name="prop_profile",
        physics_lods=(
            YftPhysicsLod.declare(
                "high",
                groups=(YftPhysicsGroup.declare("root", children=(child,)),),
            ),
        ),
        physics_bound=geometry,
    )

    raw = build_yft_bytes(source)
    _, system_data, _ = split_rsc7_sections(raw)
    parsed = read_yft(raw)
    root_pointer = parsed.physics_lod("high").undamaged_damp_archetype.bound_pointer
    leaf_pointer = _bound_child_pointer(system_data, root_pointer)

    assert struct.unpack_from("<I", system_data, virtual_to_offset(root_pointer))[0] == (
        0x40629AA8
    )
    assert struct.unpack_from("<I", system_data, virtual_to_offset(leaf_pointer))[0] == (
        0x4062D258
    )
    assert parsed.physics_bound_profile is YftPhysicsBoundProfile.PRESERVE
    assert validate_yft_bytes(raw, profile=YftPhysicsBoundProfile.PROP) == []

    rebuilt = build_yft_bytes(parsed)
    _, rebuilt_system, _ = split_rsc7_sections(rebuilt)
    reparsed = read_yft(rebuilt)
    rebuilt_root = reparsed.physics_lod("high").undamaged_damp_archetype.bound_pointer
    rebuilt_leaf = _bound_child_pointer(rebuilt_system, rebuilt_root)
    assert struct.unpack_from(
        "<I", rebuilt_system, virtual_to_offset(rebuilt_root)
    )[0] == 0x40629AA8
    assert struct.unpack_from(
        "<I", rebuilt_system, virtual_to_offset(rebuilt_leaf)
    )[0] == 0x4062D258
    assert validate_yft_bytes(
        rebuilt,
        profile=YftPhysicsBoundProfile.PROP,
    ) == []


def test_prop_profile_rejects_ybn_style_bvh():
    triangle = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
    )
    bvh = build_bound_from_triangles([triangle])
    drawable = _simple_fragment_drawable("prop_bvh")
    child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(drawable, label="prop_bvh")
    )

    with pytest.raises(ValueError, match="BoundBVH"):
        create_yft(
            drawable,
            name="prop_bvh",
            physics_lods=(
                YftPhysicsLod.declare(
                    "high",
                    groups=(YftPhysicsGroup.declare("root", children=(child,)),),
                ),
            ),
            physics_bound=bvh,
        )


def test_vehicle_profile_accepts_bvh_and_writes_native_vfts():
    triangle = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
    )
    bvh = build_bound_from_triangles([triangle])
    drawable = _simple_fragment_drawable("vehicle_bvh")
    child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(drawable, label="vehicle_bvh")
    )
    source = create_yft(
        drawable,
        name="vehicle_bvh",
        physics_lods=(
            YftPhysicsLod.declare(
                "high",
                groups=(YftPhysicsGroup.declare("root", children=(child,)),),
            ),
        ),
        physics_bound=bvh,
        physics_bound_profile=YftPhysicsBoundProfile.VEHICLE,
    )

    raw = build_yft_bytes(source)
    _, system_data, _ = split_rsc7_sections(raw)
    parsed = read_yft(raw)
    root_pointer = parsed.physics_lod("high").undamaged_damp_archetype.bound_pointer
    leaf_pointer = _bound_child_pointer(system_data, root_pointer)

    assert struct.unpack_from("<I", system_data, virtual_to_offset(root_pointer))[0] == (
        0x4062B5D8
    )
    assert struct.unpack_from("<I", system_data, virtual_to_offset(leaf_pointer))[0] == (
        0x4062FAB8
    )
    assert validate_yft_bytes(raw, profile=YftPhysicsBoundProfile.VEHICLE) == []

    rebuilt = build_yft_bytes(parsed)
    _, rebuilt_system, _ = split_rsc7_sections(rebuilt)
    reparsed = read_yft(rebuilt)
    rebuilt_root = reparsed.physics_lod("high").undamaged_damp_archetype.bound_pointer
    rebuilt_leaf = _bound_child_pointer(rebuilt_system, rebuilt_root)
    assert struct.unpack_from(
        "<I", rebuilt_system, virtual_to_offset(rebuilt_root)
    )[0] == 0x4062B5D8
    assert struct.unpack_from(
        "<I", rebuilt_system, virtual_to_offset(rebuilt_leaf)
    )[0] == 0x4062FAB8
    assert validate_yft_bytes(
        rebuilt,
        profile=YftPhysicsBoundProfile.VEHICLE,
    ) == []


def test_set_piece_profile_roundtrip_preserves_native_vfts():
    bound = BoundBox.from_center_size(
        (0.0, 0.0, 0.0),
        (2.0, 2.0, 2.0),
    ).build()
    drawable = _simple_fragment_drawable("set_piece")
    child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(drawable, label="set_piece")
    )
    raw = build_yft_bytes(
        create_yft(
            drawable,
            name="set_piece",
            physics_lods=(
                YftPhysicsLod.declare(
                    "high",
                    groups=(YftPhysicsGroup.declare("root", children=(child,)),),
                ),
            ),
            physics_bound=bound,
            physics_bound_profile=YftPhysicsBoundProfile.SET_PIECE,
        )
    )
    parsed = read_yft(raw)
    rebuilt = build_yft_bytes(parsed)
    _, rebuilt_system, _ = split_rsc7_sections(rebuilt)
    reparsed = read_yft(rebuilt)
    root_pointer = reparsed.physics_lod("high").undamaged_damp_archetype.bound_pointer
    leaf_pointer = _bound_child_pointer(rebuilt_system, root_pointer)

    assert struct.unpack_from(
        "<I", rebuilt_system, virtual_to_offset(root_pointer)
    )[0] == 0x4062BAA8
    assert struct.unpack_from(
        "<I", rebuilt_system, virtual_to_offset(leaf_pointer)
    )[0] == 0x4062DD58
    assert validate_yft_bytes(
        rebuilt,
        profile=YftPhysicsBoundProfile.SET_PIECE,
    ) == []


def test_binary_validation_rejects_swapped_prop_bound_slots():
    bounds = (
        BoundBox.from_center_size((-2.0, 0.0, 0.0), (1.0, 1.0, 1.0)).build(),
        BoundBox.from_center_size((2.0, 0.0, 0.0), (2.0, 2.0, 2.0)).build(),
    )
    composite = _composite(*bounds)
    drawable = _simple_fragment_drawable("ordered_prop")
    children = tuple(
        YftPhysicsChild.declare(
            undamaged_entity=YftPhysicsEntity.declare(
                _simple_fragment_drawable(f"ordered_prop_{index}"),
                label=f"ordered_prop_{index}",
            )
        )
        for index in range(2)
    )
    raw = build_yft_bytes(
        create_yft(
            drawable,
            name="ordered_prop",
            physics_lods=(
                YftPhysicsLod.declare(
                    "high",
                    groups=(
                        YftPhysicsGroup.declare("root", children=children),
                    ),
                ),
            ),
            physics_bound=composite,
        )
    )
    parsed = read_yft(raw)
    header, system_data, graphics_data = split_rsc7_sections(raw)
    root_pointer = parsed.physics_lod("high").undamaged_damp_archetype.bound_pointer
    root_offset = virtual_to_offset(root_pointer)
    slots_offset = virtual_to_offset(
        struct.unpack_from("<Q", system_data, root_offset + 0x70)[0]
    )
    first, second = struct.unpack_from("<2Q", system_data, slots_offset)
    broken_system = bytearray(system_data)
    struct.pack_into("<2Q", broken_system, slots_offset, second, first)
    broken = build_rsc7(
        broken_system,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )

    assert any(
        issue.is_error
        and "matching archetype bound child" in issue.message
        for issue in validate_yft_bytes(
            broken,
            profile=YftPhysicsBoundProfile.PROP,
        )
    )


def test_binary_validation_rejects_fragment_geometry_vertex_overflow():
    geometry = build_fragment_geometry_bound(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
        [(0, 1, 2)],
    )
    drawable = _simple_fragment_drawable("overflow_prop")
    child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(drawable, label="overflow_prop")
    )
    raw = build_yft_bytes(
        create_yft(
            drawable,
            name="overflow_prop",
            physics_lods=(
                YftPhysicsLod.declare(
                    "high",
                    groups=(YftPhysicsGroup.declare("root", children=(child,)),),
                ),
            ),
            physics_bound=geometry,
        )
    )
    parsed = read_yft(raw)
    header, system_data, graphics_data = split_rsc7_sections(raw)
    root_pointer = parsed.physics_lod("high").undamaged_damp_archetype.bound_pointer
    geometry_pointer = _bound_child_pointer(system_data, root_pointer)
    broken_system = bytearray(system_data)
    struct.pack_into(
        "<I",
        broken_system,
        virtual_to_offset(geometry_pointer) + 0xD0,
        0x8000,
    )
    broken = build_rsc7(
        broken_system,
        version=header.version,
        graphics_data=graphics_data,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    )

    assert any(
        issue.is_error
        and issue.path.endswith(".vertices")
        and "32768 exceeds" in issue.message
        for issue in validate_yft_bytes(
            broken,
            profile=YftPhysicsBoundProfile.PROP,
        )
    )


def test_yft_authoring_rejects_fragment_geometry_limits_before_writing():
    geometry = build_fragment_geometry_bound(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
        [(0, 1, 2)],
    )
    drawable = _simple_fragment_drawable("source_overflow")
    child = YftPhysicsChild.declare(
        undamaged_entity=YftPhysicsEntity.declare(drawable, label="source_overflow")
    )
    source = create_yft(
        drawable,
        name="source_overflow",
        physics_lods=(
            YftPhysicsLod.declare(
                "high",
                groups=(YftPhysicsGroup.declare("root", children=(child,)),),
            ),
        ),
        physics_bound=geometry,
    )
    geometry.vertices.extend(
        [(0.0, 0.0, 0.0)]
        * (MAX_FRAGMENT_BOUND_VERTICES + 1 - len(geometry.vertices))
    )

    with pytest.raises(ValueError, match="fragment bound limit"):
        build_yft_bytes(source)


def test_yft_authoring_rejects_bone_ids_that_would_be_truncated():
    bound = BoundBox.from_center_size(
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0),
    ).build()
    drawable = _simple_fragment_drawable("invalid_bone")
    child = YftPhysicsChild.declare(
        bone_id=0x10000,
        undamaged_entity=YftPhysicsEntity.declare(drawable, label="invalid_bone"),
    )
    source = create_yft(
        drawable,
        name="invalid_bone",
        physics_lods=(
            YftPhysicsLod.declare(
                "high",
                groups=(YftPhysicsGroup.declare("root", children=(child,)),),
            ),
        ),
        physics_bound=bound,
    )

    with pytest.raises(ValueError, match="bone_id"):
        build_yft_bytes(source)
