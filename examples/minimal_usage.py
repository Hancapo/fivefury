"""Minimal usage example for the eventual FiveFury Python port.

This file is intentionally defensive: it can be imported or run before the
Python port exists without crashing the workspace.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from fivefury import Entity, GameFileCache, Ymap, create_rpf, jenk_hash, rpf_to_zip, zip_to_rpf  # type: ignore
    except Exception:
        print("FiveFury Python API is not available yet.")
        return 0

    ymap = Ymap(name="example_map")
    ymap.add_entity(Entity(archetype_name="prop_tree_pine_01", position=(0.0, 0.0, 0.0), lod_dist=120.0))
    ymap.recalculate_extents()

    ymap_path = project_root / "example.ymap"
    ymap.save(ymap_path)

    archive = create_rpf("example.rpf")
    archive.add("maps/example.ymap", ymap)
    archive.add("docs/readme.txt", b"hello from fivefury")

    print(f"Hash for 'CMapData': {jenk_hash('CMapData'):08x}")
    print("RPF helpers available:", callable(create_rpf), callable(zip_to_rpf), callable(rpf_to_zip))
    print("Archive bytes:", len(archive.to_bytes()))
    print("Cache type available:", GameFileCache.__name__)
    print("Example root:", Path(".").resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

