"""
Performance benchmarks for fivefury hot paths.

Run with:
    pytest tests/bench_perf.py -v --benchmark-sort=mean
    pytest tests/bench_perf.py -v --benchmark-columns=mean,stddev,rounds,iterations

Disable benchmarking (just run as tests):
    pytest tests/bench_perf.py --benchmark-disable

Run only game-cache benchmarks (requires GTA V install):
    pytest tests/bench_perf.py -v -k "GameCache" -o "python_classes=Test*"
"""

from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path

import pytest

from fivefury.hashing import jenk_hash
from fivefury.metahash import MetaHash
from fivefury.resolver import clear_hash_resolver, register_name, resolve_hash
from fivefury.meta import MetaBuilder, MetaStructInfo, MetaFieldInfo, ParsedMeta, build_meta_system
from fivefury.meta_defs import MetaDataType, meta_name
from fivefury.ymap import Ymap, Entity
from fivefury.ytyp import Ytyp, Archetype
from fivefury.rpf import create_rpf
from fivefury.gamefile import guess_game_file_type
from fivefury.cache import GameFileCache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SHORT_STRINGS = ["a", "test", "CMapData", "prop_tree_pine_01", "ymap"]
LONG_STRING = "very_long_archetype_name_for_a_custom_asset_object_in_gta_v_modding"

MANY_NAMES = [f"prop_object_{i:04d}" for i in range(1000)]

GTA_ROOT = os.environ.get(
    "GTA5_ROOT",
    r"C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy",
)
_HAS_GTA = os.path.isdir(GTA_ROOT) and any(
    f.lower().endswith(".rpf") for f in os.listdir(GTA_ROOT)
)
skip_no_gta = pytest.mark.skipif(not _HAS_GTA, reason="GTA V not found at GTA5_ROOT")


@pytest.fixture
def small_ymap_bytes():
    """A small YMAP with 5 entities, serialized to bytes."""
    ymap = Ymap(name="bench_map")
    for i in range(5):
        ymap.add_entity(
            Entity(
                archetype_name=f"prop_bench_{i}",
                position=(float(i), 0.0, 0.0),
                lod_dist=100.0,
            )
        )
    ymap.recalculate_extents()
    ymap.recalculate_flags()
    return ymap.to_bytes()


@pytest.fixture
def medium_ymap_bytes():
    """A medium YMAP with 100 entities, serialized to bytes."""
    ymap = Ymap(name="bench_map_medium")
    for i in range(100):
        ymap.add_entity(
            Entity(
                archetype_name=f"prop_medium_{i:04d}",
                position=(float(i), float(i % 10), 0.0),
                lod_dist=120.0,
            )
        )
    ymap.recalculate_extents()
    ymap.recalculate_flags()
    return ymap.to_bytes()


@pytest.fixture
def large_ymap():
    """A large YMAP with 500 entities (in-memory object)."""
    ymap = Ymap(name="bench_map_large")
    for i in range(500):
        ymap.add_entity(
            Entity(
                archetype_name=f"prop_large_{i:04d}",
                position=(float(i), float(i % 50), float(i % 10)),
                rotation=(0.0, 0.0, 0.0, 1.0),
                lod_dist=150.0,
            )
        )
    return ymap


# ---------------------------------------------------------------------------
# 1. jenk_hash — the most called function
# ---------------------------------------------------------------------------

class TestJenkHashPerf:
    def test_hash_short_string(self, benchmark):
        """jenk_hash on a short string (typical archetype name)."""
        benchmark(jenk_hash, "prop_tree_pine_01")

    def test_hash_long_string(self, benchmark):
        """jenk_hash on a long string (~66 chars)."""
        benchmark(jenk_hash, LONG_STRING)

    def test_hash_batch_1000_names(self, benchmark):
        """Hash 1000 different names (simulates scan registration)."""
        def run():
            for name in MANY_NAMES:
                jenk_hash(name)
        benchmark(run)

    def test_hash_empty_string(self, benchmark):
        """jenk_hash baseline on empty string."""
        benchmark(jenk_hash, "")


# ---------------------------------------------------------------------------
# 2. MetaHash — re-hashing on every property access
# ---------------------------------------------------------------------------

class TestMetaHashPerf:
    def test_uint_from_string_no_cache(self, benchmark):
        """MetaHash.uint when backed by a string (re-hashes every time)."""
        mh = MetaHash("prop_tree_pine_01")
        benchmark(lambda: mh.uint)

    def test_uint_from_int(self, benchmark):
        """MetaHash.uint when backed by an int (fast path)."""
        mh = MetaHash(0xCA2E9442)
        benchmark(lambda: mh.uint)

    def test_hash_equality_string_vs_string(self, benchmark):
        """MetaHash == MetaHash (both strings, triggers 2x jenk_hash)."""
        a = MetaHash("prop_tree_pine_01")
        b = MetaHash("prop_tree_pine_01")
        benchmark(lambda: a == b)

    def test_hash_in_set_lookup(self, benchmark):
        """Looking up a string-backed MetaHash in a set (triggers __hash__)."""
        items = {MetaHash(f"name_{i}") for i in range(100)}
        target = MetaHash("name_50")
        benchmark(lambda: target in items)

    def test_metahash_repeated_int_conversion(self, benchmark):
        """Calling int() on a string-backed MetaHash 100 times."""
        mh = MetaHash("prop_tree_pine_01")
        def run():
            for _ in range(100):
                int(mh)
        benchmark(run)


# ---------------------------------------------------------------------------
# 3. YMAP serialization (to_bytes) — exercises MetaBuilder + packing
# ---------------------------------------------------------------------------

class TestYmapSerializationPerf:
    def test_serialize_5_entities(self, benchmark, small_ymap_bytes):
        """Deserialize + re-serialize a 5-entity YMAP (roundtrip)."""
        def run():
            ymap = Ymap.from_bytes(small_ymap_bytes)
            ymap.to_bytes()
        benchmark(run)

    def test_serialize_100_entities(self, benchmark, medium_ymap_bytes):
        """Deserialize + re-serialize a 100-entity YMAP."""
        def run():
            ymap = Ymap.from_bytes(medium_ymap_bytes)
            ymap.to_bytes()
        benchmark(run)

    def test_build_500_entities_from_scratch(self, benchmark):
        """Build a 500-entity YMAP from scratch and serialize."""
        def run():
            ymap = Ymap(name="perf_test")
            for i in range(500):
                ymap.add_entity(
                    Entity(
                        archetype_name=f"prop_perf_{i:04d}",
                        position=(float(i), 0.0, 0.0),
                        lod_dist=100.0,
                    )
                )
            ymap.recalculate_extents()
            ymap.recalculate_flags()
            ymap.to_bytes()
        benchmark(run)

    def test_recalculate_extents_500(self, benchmark, large_ymap):
        """recalculate_extents on 500 entities."""
        benchmark(large_ymap.recalculate_extents)

    def test_recalculate_flags_500(self, benchmark, large_ymap):
        """recalculate_flags on 500 entities."""
        benchmark(large_ymap.recalculate_flags)


# ---------------------------------------------------------------------------
# 4. YMAP deserialization (from_bytes) — exercises META parser
# ---------------------------------------------------------------------------

class TestYmapParsingPerf:
    def test_parse_5_entities(self, benchmark, small_ymap_bytes):
        """Parse a 5-entity YMAP from bytes."""
        benchmark(Ymap.from_bytes, small_ymap_bytes)

    def test_parse_100_entities(self, benchmark, medium_ymap_bytes):
        """Parse a 100-entity YMAP from bytes."""
        benchmark(Ymap.from_bytes, medium_ymap_bytes)


# ---------------------------------------------------------------------------
# 5. YTYP serialization roundtrip
# ---------------------------------------------------------------------------

class TestYtypPerf:
    def test_ytyp_roundtrip_50_archetypes(self, benchmark):
        """Build + serialize + deserialize a 50-archetype YTYP."""
        def run():
            ytyp = Ytyp(name="perf_types")
            for i in range(50):
                ytyp.add_archetype(
                    Archetype(
                        name=f"arch_{i:04d}",
                        lod_dist=120.0,
                        asset_type=0,
                        bb_min=(-1.0, -1.0, -0.5),
                        bb_max=(1.0, 1.0, 5.0),
                        bs_centre=(0.0, 0.0, 2.0),
                        bs_radius=3.0,
                    )
                )
            data = ytyp.to_bytes()
            Ytyp.from_bytes(data)
        benchmark(run)


# ---------------------------------------------------------------------------
# 6. RPF archive construction
# ---------------------------------------------------------------------------

class TestRpfBuildPerf:
    def test_build_rpf_50_files(self, benchmark):
        """Build an RPF archive with 50 small binary entries."""
        def run():
            archive = create_rpf("bench.rpf")
            for i in range(50):
                archive.add(f"data/file_{i:04d}.dat", f"content {i}".encode())
            buf = archive.to_bytes()
            assert len(buf) > 0
        benchmark(run)

    def test_build_rpf_with_ymap_assets(self, benchmark, small_ymap_bytes):
        """Build an RPF with 10 YMAP resource entries."""
        def run():
            archive = create_rpf("maps.rpf")
            for i in range(10):
                ymap = Ymap.from_bytes(small_ymap_bytes)
                ymap.meta_name = f"map_{i:04d}"
                archive.add(f"stream/map_{i:04d}.ymap", ymap)
            archive.to_bytes()
        benchmark(run)


# ---------------------------------------------------------------------------
# 7. Hash resolver — bulk registration
# ---------------------------------------------------------------------------

class TestResolverPerf:
    def test_register_1000_names(self, benchmark):
        """Register 1000 names into the global hash resolver."""
        def run():
            clear_hash_resolver()
            for name in MANY_NAMES:
                register_name(name)
        benchmark(run)

    def test_resolve_1000_hashes(self, benchmark):
        """Resolve 1000 hashes after registration."""
        clear_hash_resolver()
        hashes = []
        for name in MANY_NAMES:
            register_name(name)
            hashes.append(jenk_hash(name))

        def run():
            for h in hashes:
                resolve_hash(h)
        benchmark(run)


# ---------------------------------------------------------------------------
# 8. struct packing — simulates _pack_primitive_array patterns
# ---------------------------------------------------------------------------

class TestStructPackingPerf:
    def test_pack_floats_per_element(self, benchmark):
        """Current approach: struct.pack per element + join (1000 floats)."""
        values = [float(i) for i in range(1000)]
        def run():
            b"".join(struct.pack("<f", v) for v in values)
        benchmark(run)

    def test_pack_floats_batch(self, benchmark):
        """Optimal approach: single struct.pack call (1000 floats)."""
        values = [float(i) for i in range(1000)]
        fmt = f"<{len(values)}f"
        def run():
            struct.pack(fmt, *values)
        benchmark(run)

    def test_pack_ints_per_element(self, benchmark):
        """Current approach: struct.pack per element (1000 uint32)."""
        values = list(range(1000))
        def run():
            b"".join(struct.pack("<I", v) for v in values)
        benchmark(run)

    def test_pack_ints_batch(self, benchmark):
        """Optimal approach: single struct.pack call (1000 uint32)."""
        values = list(range(1000))
        fmt = f"<{len(values)}I"
        def run():
            struct.pack(fmt, *values)
        benchmark(run)


# ---------------------------------------------------------------------------
# 9. guess_game_file_type — dict rebuilt per call
# ---------------------------------------------------------------------------

class TestGameFileTypePerf:
    def test_guess_type_1000_paths(self, benchmark):
        """Call guess_game_file_type 1000 times (dict rebuilt each time)."""
        paths = [f"folder/file_{i}.ymap" for i in range(500)] + [
            f"folder/file_{i}.ytyp" for i in range(500)
        ]
        def run():
            for p in paths:
                guess_game_file_type(p)
        benchmark(run)


# ---------------------------------------------------------------------------
# 10. GameFileCache — scan with loose files
# ---------------------------------------------------------------------------

class TestCacheScanPerf:
    def test_scan_200_loose_files(self, benchmark):
        """Scan a temp directory with 200 loose files."""
        def run():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                maps = root / "maps"
                maps.mkdir()
                types = root / "types"
                types.mkdir()
                for i in range(100):
                    (maps / f"map_{i:04d}.ymap").write_bytes(b"dummy")
                for i in range(100):
                    (types / f"type_{i:04d}.ytyp").write_bytes(b"dummy")
                cache = GameFileCache(root)
                cache.scan()
        benchmark(run)

    def test_scan_and_populate_resolver(self, benchmark):
        """Scan + populate_resolver with 200 assets."""
        def run():
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                maps = root / "maps"
                maps.mkdir()
                for i in range(200):
                    (maps / f"asset_{i:04d}.ymap").write_bytes(b"dummy")
                cache = GameFileCache(root)
                cache.scan()
                cache.populate_resolver()
        benchmark(run)


# ---------------------------------------------------------------------------
# 11. MetaBuilder._add_block — linear scan bottleneck
# ---------------------------------------------------------------------------

class TestMetaBuilderBlockPerf:
    def test_add_block_grouping_100(self, benchmark):
        """Simulate adding 100 small data blocks with grouping enabled."""
        def run():
            builder = MetaBuilder(struct_infos={}, enum_infos={})
            name_hash = jenk_hash("CEntityDef")
            for i in range(100):
                builder._add_block(name_hash, struct.pack("<4f", 1.0, 2.0, 3.0, float(i)))
        benchmark(run)

    def test_add_block_grouping_500(self, benchmark):
        """Simulate adding 500 small data blocks with grouping (O(n²) risk)."""
        def run():
            builder = MetaBuilder(struct_infos={}, enum_infos={})
            name_hash = jenk_hash("CEntityDef")
            for i in range(500):
                builder._add_block(name_hash, struct.pack("<4f", 1.0, 2.0, 3.0, float(i)))
        benchmark(run)


# ---------------------------------------------------------------------------
# 12. RPF _rebuild_index — called per add_file
# ---------------------------------------------------------------------------

class TestRpfRebuildIndexPerf:
    def test_rebuild_index_100_files(self, benchmark):
        """Build an RPF adding 100 files (rebuild_index called each time)."""
        def run():
            archive = create_rpf("idx_test.rpf")
            for i in range(100):
                archive.add(f"stream/file_{i:04d}.dat", b"x" * 64)
        benchmark(run)


# ---------------------------------------------------------------------------
# 13. Real game cache — scan + populate_resolver on actual GTA V install
#     Set GTA5_ROOT env var to override default path.
#     Skipped automatically if GTA V is not installed.
# ---------------------------------------------------------------------------

class TestGameCacheRealPerf:
    @skip_no_gta
    def test_scan_game_full(self, benchmark):
        """Full scan of GTA V installation (cold, no index cache)."""
        benchmark.extra_info["gta_root"] = GTA_ROOT
        def run():
            cache = GameFileCache(GTA_ROOT)
            cache.scan(use_index_cache=False)
            assert cache.scan_ok
            assert cache.asset_count > 100_000
        result = benchmark.pedantic(run, rounds=3, warmup_rounds=0)

    @skip_no_gta
    def test_scan_game_cached(self, benchmark):
        """Scan with index cache (warm: deserialize pre-built index)."""
        # Ensure cache file exists from a first scan
        warmup = GameFileCache(GTA_ROOT)
        warmup.scan(use_index_cache=True)
        assert warmup.scan_ok

        def run():
            cache = GameFileCache(GTA_ROOT)
            cache.scan(use_index_cache=True)
            assert cache.scan_ok
            assert cache.asset_count > 100_000
        benchmark.pedantic(run, rounds=5, warmup_rounds=0)

    @skip_no_gta
    def test_populate_resolver_real(self, benchmark):
        """populate_resolver on a real ~390K asset index (dominated by jenk_hash)."""
        cache = GameFileCache(GTA_ROOT)
        cache.scan(use_index_cache=True)
        asset_count = cache.asset_count
        benchmark.extra_info["asset_count"] = asset_count

        def run():
            clear_hash_resolver()
            cache.populate_resolver()
        benchmark.pedantic(run, rounds=5, warmup_rounds=1)

    @skip_no_gta
    def test_jenk_hash_at_game_scale(self, benchmark):
        """jenk_hash on realistic filenames at game scale (~390K names)."""
        cache = GameFileCache(GTA_ROOT)
        cache.scan(use_index_cache=True)
        names = [cache._index.get_path(i).rsplit("/", 1)[-1].rsplit(".", 1)[0]
                 for i in range(min(cache.asset_count, 10_000))]
        benchmark.extra_info["name_count"] = len(names)

        def run():
            for name in names:
                jenk_hash(name)
        benchmark.pedantic(run, rounds=5, warmup_rounds=1)


