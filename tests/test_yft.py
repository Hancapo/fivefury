from __future__ import annotations

import dataclasses
import struct

from fivefury import BoundBox, YdrMaterialInput, YdrMeshInput, create_ydr
from fivefury.resource import build_rsc7, split_rsc7_sections
from fivefury.ydr import Ydr, YdrLod, YdrMaterial, YdrMesh, YdrModel
from fivefury.yft import (
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
    YftPhysicsChild,
    YftPhysicsEntity,
    YftPhysicsGroup,
    YftPhysicsGroupFlag,
    YftPhysicsLod,
    YftPhysicsLodPointers,
    YftVerletCloth,
    build_yft_bytes,
    create_yft,
    read_yft,
    scan_yft_corpus,
    validate_yft,
)


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
    system_data[0x550:0x554] = bytes([0, 0, 7, 0])
    struct.pack_into("<QQ", system_data, 0x5E0, 0x50000680, 0x50000690)
    struct.pack_into("<ffff", system_data, 0x600, 100.0, 101.0, 102.0, 103.0)
    struct.pack_into("<ffff", system_data, 0x620, 1.0, 2.0, 3.0, 4.0)
    struct.pack_into("<ffff", system_data, 0x660, 5.0, 6.0, 7.0, 8.0)
    struct.pack_into("<IIQIIQ", system_data, 0xB00, 0x54534552, 0, 0, 1, 0, 0)
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
        "<ffffffff", system_data, 0xA10, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0
    )
    struct.pack_into("<i", system_data, 0x810, 2)
    struct.pack_into("<QQ", system_data, 0x818, 0x50000A70, 0x50000A80)
    struct.pack_into("<IIH", system_data, 0x828, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF)
    struct.pack_into("<ffffff", system_data, 0x840, 10.0, 0.1, 1.0, 500.0, 6.28, 0.5)
    struct.pack_into("<ffffff", system_data, 0x860, 11.0, 12.0, 13.0, 0.01, 0.02, 0.03)
    struct.pack_into("<fff", system_data, 0x880, 0.7, 0.8, 0.9)
    struct.pack_into("<i", system_data, 0x910, 2)
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
        (0x690, "example/physics_high_child_0_undamaged.ydr"),
        (0x6A0, "example/physics_high_child_0_damaged.ydr"),
        (0x110, "example/drawable.ydr"),
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


def test_yft_declarative_physics_validation():
    drawable = Ydr(version=162, lods={YdrLod.HIGH: [YdrModel(lod=YdrLod.HIGH)]})
    child = YftPhysicsChild.declare(
        bone_id=4, undamaged_mass=2.5, min_breaking_impulse=120.0
    )
    group = YftPhysicsGroup.declare(
        "chassis", children=(child,), flags=YftPhysicsGroupFlag.DAMAGE_WHEN_BROKEN
    )
    lod = YftPhysicsLod.declare(groups=(group,))
    yft = Yft(
        main_drawable=drawable,
        physics_lods=YftPhysicsLodPointers(high=0x50000100),
        physics_lod_details=[lod],
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
    _, system_data, _ = split_rsc7_sections(raw)
    target = tmp_path / "fragment.yft"
    target.write_bytes(raw)
    parsed = read_yft(target, resolve_physics_entities=False)
    parsed_with_entities = read_yft(target)

    assert parsed.physics_lods.has_physics is True
    assert parsed.root_child is not None
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
    assert struct.unpack_from("<Q", system_data, 0x50)[0] != 0
    assert struct.unpack_from("<Q", system_data, 0x58)[0] != 0
    assert struct.unpack_from("<fff", system_data, 0xCC) == (0.25, 0.5, 0.75)
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
    assert parsed.validate() == []

    parsed.main_drawable.extra_bound_indices = (7,)
    parsed.main_drawable.extra_bound_matrices = (YftFragmentMatrix.identity(),)
    reparsed = read_yft(
        build_yft_bytes(parsed),
        resolve_physics_entities=False,
    )

    assert reparsed.main_drawable.extra_bound_indices == (7,)
    assert reparsed.main_drawable.extra_bound_matrices == (
        YftFragmentMatrix.identity(),
    )


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
        issue.is_error and issue.path == "collision_event_set"
        for issue in issues
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
