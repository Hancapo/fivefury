from __future__ import annotations

import trimesh
from trimesh.visual.material import MultiMaterial, SimpleMaterial
from trimesh.visual.texture import TextureVisuals

from fivefury.ydr.trimesh.materials import iter_material_parts


def test_material_parts_are_sorted_while_faces_keep_source_order() -> None:
    materials = MultiMaterial(
        [
            SimpleMaterial(name="zero"),
            SimpleMaterial(name="one"),
            SimpleMaterial(name="two"),
        ]
    )
    mesh = trimesh.Trimesh(
        vertices=(
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
            (-1.0, 1.0, 0.0),
            (-1.0, 0.0, 0.0),
        ),
        faces=((0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5)),
        visual=TextureVisuals(
            material=materials,
            face_materials=(2, 0, 2, 1),
        ),
        process=False,
    )

    parts = [
        (slot, indices.tolist() if indices is not None else None)
        for _material, slot, indices in iter_material_parts(mesh)
    ]

    assert parts == [(0, [1]), (1, [3]), (2, [0, 2])]
