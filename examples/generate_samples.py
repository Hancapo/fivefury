from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fivefury import (
    Aabb,
    Archetype,
    BoxOccluder,
    Entity,
    GrassBatch,
    GrassInstance,
    OccludeModel,
    ParticleEffectExtension,
    TimeArchetype,
    Ymap,
    Ytyp,
    create_rpf,
)


GENERATED_DIR = Path(__file__).resolve().parent / "generated"


def build_vanilla_like_test():
    ymap = Ymap(name="vanilla_like_test")
    ymap.add_entity(
        Entity(
            archetype_name="prop_tree_pine_01",
            guid=1,
            position=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0, 1.0),
            lod_dist=120.0,
        )
    )
    ymap.recalculate_extents()
    ymap.recalculate_flags()
    return ymap


def build_typed_test_map():
    ymap = Ymap(name="typed_test_map")

    entity = Entity(
        archetype_name="prop_tree_pine_01",
        guid=1,
        position=(2.0, 2.0, 0.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
        lod_dist=150.0,
    )
    entity.add_extension(
        ParticleEffectExtension(
            name="fx_smoke",
            offset_position=(0.0, 0.0, 1.0),
            offset_rotation=(0.0, 0.0, 0.0, 1.0),
            fx_name="scr_wheel_burnout",
            fx_type=2,
            scale=1.0,
            probability=100,
            flags=1,
            color=0xFFFFFFFF,
        )
    )
    ymap.add_entity(entity)

    ymap.add_box_occluder(
        BoxOccluder(
            iCenterX=80,
            iCenterY=40,
            iCenterZ=16,
            iCosZ=0,
            iLength=48,
            iWidth=24,
            iHeight=32,
            iSinZ=32767,
        )
    )

    ymap.add_occlude_model(
        OccludeModel.from_geometry(
            [
                (0.0, 0.0, 0.0),
                (4.0, 0.0, 0.0),
                (4.0, 4.0, 0.0),
                (0.0, 4.0, 0.0),
            ],
            b"\x00\x01\x02\x00\x02\x03",
            flags=1,
        )
    )

    grass_batch = GrassBatch(
        batch_aabb=Aabb(minimum=(0.0, 0.0, 0.0), maximum=(20.0, 20.0, 4.0)),
        scale_range=(0.8, 1.0, 1.2),
        archetype_name="prop_grass_01",
        lod_dist=80,
        lod_fade_start_dist=40.0,
        lod_inst_fade_range=20.0,
        orient_to_terrain=1.0,
    )
    grass_batch.add_instance(
        GrassInstance(
            position=(5.0, 5.0, 1.0),
            normal=(0.0, 0.0, 1.0),
            color=(20, 120, 40),
            scale=100,
            ao=90,
        )
    )
    grass_batch.add_instance(
        GrassInstance(
            position=(9.0, 7.0, 1.2),
            normal=(0.0, 0.0, 1.0),
            color=(30, 130, 50),
            scale=110,
            ao=100,
        )
    )
    ymap.add_grass_batch(grass_batch)

    ymap.lod_light(
        position=(3.0, 3.0, 4.0),
        direction=(0.0, 0.0, -1.0),
        falloff=18.0,
        falloff_exponent=1.5,
        time_and_state_flags=0,
        hash="streetlight",
        cone_inner_angle=30,
        cone_outer_angle_or_cap_ext=60,
        corona_intensity=64,
        rgbi=0xC8B482FF,
    )

    ymap.recalculate_extents()
    ymap.recalculate_flags()
    return ymap


def build_150_entities_test():
    ymap = Ymap(name="entities_150_test")

    columns = 15
    spacing = 8.0
    base_x = -56.0
    base_y = -36.0

    for index in range(150):
        row = index // columns
        column = index % columns
        x = base_x + (column * spacing)
        y = base_y + (row * spacing)
        z = 0.0
        ymap.add_entity(
            Entity(
                archetype_name="prop_tree_pine_01",
                guid=index + 1,
                position=(x, y, z),
                rotation=(0.0, 0.0, 0.0, 1.0),
                lod_dist=180.0,
            )
        )

    ymap.recalculate_extents()
    ymap.recalculate_flags()
    return ymap


def build_typed_test_ytyp():
    ytyp = Ytyp(name="typed_test_types")

    archetype = Archetype(
        name="prop_tree_pine_01",
        lod_dist=150.0,
        asset_type=0,
        asset_name="prop_tree_pine_01",
        bb_min=(-1.5, -1.5, -0.5),
        bb_max=(1.5, 1.5, 8.0),
        bs_centre=(0.0, 0.0, 3.5),
        bs_radius=5.0,
        hd_texture_dist=60.0,
    )
    archetype.add_extension(
        ParticleEffectExtension(
            name="fx_tree",
            offset_position=(0.0, 0.0, 1.0),
            offset_rotation=(0.0, 0.0, 0.0, 1.0),
            fx_name="scr_wheel_burnout",
            fx_type=2,
            scale=0.8,
            probability=100,
            flags=1,
            color=0xFFFFFFFF,
        )
    )
    ytyp.add_archetype(archetype)

    ytyp.add_archetype(
        Archetype(
            name="prop_grass_01",
            lod_dist=60.0,
            asset_type=0,
            asset_name="prop_grass_01",
            bb_min=(-0.5, -0.5, 0.0),
            bb_max=(0.5, 0.5, 1.0),
            bs_centre=(0.0, 0.0, 0.5),
            bs_radius=0.9,
            hd_texture_dist=20.0,
        )
    )

    ytyp.add_archetype(
        TimeArchetype(
            name="prop_sign_road_01",
            lod_dist=90.0,
            asset_type=0,
            asset_name="prop_sign_road_01",
            bb_min=(-1.0, -0.2, 0.0),
            bb_max=(1.0, 0.2, 3.0),
            bs_centre=(0.0, 0.0, 1.5),
            bs_radius=1.8,
            hd_texture_dist=30.0,
            time_flags=0xFFFFFF,
        )
    )

    return ytyp


def main() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    vanilla_path = GENERATED_DIR / "vanilla_like_test.ymap"
    typed_path = GENERATED_DIR / "typed_test_map.ymap"
    entities_150_path = GENERATED_DIR / "entities_150_test.ymap"
    ytyp_path = GENERATED_DIR / "typed_test_types.ytyp"
    archive_path = GENERATED_DIR / "typed_test_assets.rpf"

    vanilla = build_vanilla_like_test()
    typed = build_typed_test_map()
    entities_150 = build_150_entities_test()
    ytyp = build_typed_test_ytyp()

    vanilla.save(vanilla_path)
    typed.save(typed_path)
    entities_150.save(entities_150_path)
    ytyp.save(ytyp_path)

    archive = create_rpf("typed_test_assets.rpf")
    archive.add("stream/typed_test_map.ymap", typed)
    archive.add("stream/typed_test_types.ytyp", ytyp)
    archive.save(archive_path)

    print(vanilla_path)
    print(typed_path)
    print(entities_150_path)
    print(ytyp_path)
    print(archive_path)


if __name__ == "__main__":
    main()

