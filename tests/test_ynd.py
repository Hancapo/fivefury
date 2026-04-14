from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import (
    GameFileCache,
    GameFileType,
    Ynd,
    YndLink,
    YndNetwork,
    YndNode,
    build_ynd_bytes,
    get_ynd_area_id,
    read_ynd,
)


_REFERENCE_DIR = Path(__file__).resolve().parents[1] / "references" / "ynd"


def _reference_ynd_paths() -> list[Path]:
    return sorted(_REFERENCE_DIR.glob("*.ynd"))


def _assert_roundtrip_equivalent(original: Ynd, rebuilt: Ynd) -> None:
    assert rebuilt.version == original.version
    assert rebuilt.file_vft == original.file_vft
    assert rebuilt.file_unknown == original.file_unknown
    assert len(rebuilt.nodes) == len(original.nodes)
    assert rebuilt.vehicle_node_count == original.vehicle_node_count
    assert rebuilt.ped_node_count == original.ped_node_count
    assert rebuilt.link_count == original.link_count
    assert rebuilt.junction_count == original.junction_count
    for original_node, rebuilt_node in zip(original.nodes, rebuilt.nodes, strict=True):
        assert rebuilt_node.area_id == original_node.area_id
        assert rebuilt_node.node_id == original_node.node_id
        assert rebuilt_node.street_name_hash == original_node.street_name_hash
        assert rebuilt_node.group == original_node.group
        assert rebuilt_node.movement_flags == original_node.movement_flags
        assert rebuilt_node.guidance_flags == original_node.guidance_flags
        assert rebuilt_node.state_flags == original_node.state_flags
        assert rebuilt_node.routing_flags == original_node.routing_flags
        assert rebuilt_node.topography_flags == original_node.topography_flags
        assert rebuilt_node.special == original_node.special
        assert rebuilt_node.speed == original_node.speed
        assert rebuilt_node.qualifies_as_junction == original_node.qualifies_as_junction
        assert rebuilt_node.distance_hash == original_node.distance_hash
        assert rebuilt_node.density == original_node.density
        assert rebuilt_node.dead_endness == original_node.dead_endness
        assert rebuilt_node.flags0 == original_node.flags0
        assert rebuilt_node.flags1 == original_node.flags1
        assert rebuilt_node.flags2 == original_node.flags2
        assert rebuilt_node.flags3 == original_node.flags3
        assert rebuilt_node.flags4 == original_node.flags4
        assert rebuilt_node.link_count_flags == original_node.link_count_flags
        assert rebuilt_node.position == pytest.approx(original_node.position)
        assert len(rebuilt_node.links) == len(original_node.links)
        for original_link, rebuilt_link in zip(original_node.links, rebuilt_node.links, strict=True):
            assert rebuilt_link.area_id == original_link.area_id
            assert rebuilt_link.node_id == original_link.node_id
            assert rebuilt_link.travel_flags == original_link.travel_flags
            assert rebuilt_link.shape_flags == original_link.shape_flags
            assert rebuilt_link.navigation_flags == original_link.navigation_flags
            assert rebuilt_link.tilt == original_link.tilt
            assert rebuilt_link.tilt_falloff == original_link.tilt_falloff
            assert rebuilt_link.width == original_link.width
            assert rebuilt_link.lanes_from_other_node == original_link.lanes_from_other_node
            assert rebuilt_link.lanes_to_other_node == original_link.lanes_to_other_node
            assert rebuilt_link.distance == original_link.distance
            assert rebuilt_link.flags0 == original_link.flags0
            assert rebuilt_link.flags1 == original_link.flags1
            assert rebuilt_link.flags2 == original_link.flags2
            assert rebuilt_link.link_length == original_link.link_length
        if original_node.junction is None:
            assert rebuilt_node.junction is None
        else:
            assert rebuilt_node.junction is not None
            assert rebuilt_node.junction.position == pytest.approx(original_node.junction.position)
            assert rebuilt_node.junction.min_z == pytest.approx(original_node.junction.min_z)
            assert rebuilt_node.junction.max_z == pytest.approx(original_node.junction.max_z)
            assert rebuilt_node.junction.heightmap_dim_x == original_node.junction.heightmap_dim_x
            assert rebuilt_node.junction.heightmap_dim_y == original_node.junction.heightmap_dim_y
            assert rebuilt_node.junction.heightmap == original_node.junction.heightmap
            assert rebuilt_node.junction.junction_ref_unk0 == original_node.junction.junction_ref_unk0


def test_read_all_reference_ynd_samples() -> None:
    paths = _reference_ynd_paths()
    if not paths:
        pytest.skip("real YND reference directory not available")

    for path in paths:
        ynd = read_ynd(path)
        assert ynd.version == 1
        assert ynd.file_vft == 0x406203D0
        assert ynd.file_unknown == 1
        assert ynd.nodes
        assert ynd.vehicle_node_count + ynd.ped_node_count == len(ynd.nodes)
        assert ynd.link_count > 0


def test_roundtrip_reference_ynd_sample() -> None:
    paths = _reference_ynd_paths()
    if not paths:
        pytest.skip("real YND reference directory not available")

    original = read_ynd(paths[0])
    rebuilt = read_ynd(build_ynd_bytes(original))
    _assert_roundtrip_equivalent(original, rebuilt)


def test_roundtrip_all_reference_ynd_samples() -> None:
    paths = _reference_ynd_paths()
    if not paths:
        pytest.skip("real YND reference directory not available")

    for path in paths:
        original = read_ynd(path)
        rebuilt = read_ynd(build_ynd_bytes(original))
        _assert_roundtrip_equivalent(original, rebuilt)


def test_gamefilecache_parses_loose_ynd(tmp_path: Path) -> None:
    paths = _reference_ynd_paths()
    if not paths:
        pytest.skip("real YND reference directory not available")

    stream_dir = tmp_path / "stream"
    stream_dir.mkdir()
    target = stream_dir / paths[0].name
    target.write_bytes(paths[0].read_bytes())

    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)

    game_file = cache.get_file(f"stream/{paths[0].name}")
    assert game_file is not None
    assert game_file.kind == GameFileType.YND
    assert isinstance(game_file.parsed, Ynd)
    assert game_file.parsed.nodes


def test_build_rejects_nodes_outside_ynd_area() -> None:
    node = YndNode(node_id=10, position=(0.0, 0.0, 0.0))
    area_id = get_ynd_area_id((4608.0, -6144.0, 0.0))

    with pytest.raises(ValueError, match="does not belong to area_id"):
        Ynd.from_nodes([node], area_id=area_id).build()


def test_network_partitions_nodes_into_multiple_ynds() -> None:
    node_a = YndNode(node_id=10, key="a", position=(0.0, 0.0, 0.0))
    node_b = YndNode(node_id=11, key="b", position=(600.0, 0.0, 0.0))
    node_a.links.append(YndLink(target_key="b"))
    node_b.links.append(YndLink(target_key="a"))

    ynds = YndNetwork.from_nodes([node_a, node_b]).build_ynds()

    assert len(ynds) == 2
    area_ids = [ynd.area_id for ynd in ynds]
    assert area_ids == sorted(area_ids)
    assert area_ids[0] != area_ids[1]
    assert {node.area_id for ynd in ynds for node in ynd.nodes} == set(area_ids)
