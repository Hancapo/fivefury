from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from fivefury.cache import GameFileCache
from fivefury.hashing import jenk_hash
from fivefury.meta import MetaDataType, MetaFieldInfo, MetaStructInfo, build_meta_system
from fivefury.metahash import MetaHash
from fivefury.resolver import (
    clear_hash_resolver,
    hash_matches,
    register_name,
    register_names_file,
    resolve_hash,
)
from fivefury.ymap import Entity, Ymap
from fivefury.ytyp import Archetype, Ytyp


class HashingContractTests:
    @pytest.mark.requires_platform("nt")
    def test_windows_aes_decryptor_reuses_handles_across_many_calls(self) -> None:
        if os.name != "nt":
            pytest.fail("Windows CNG AES regression test is only relevant on Windows")
        import fivefury.crypto as crypto_module

        decryptor = crypto_module._build_windows_aes_decryptor(
            bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        )
        ciphertext = bytes.fromhex("3ad77bb40d7a3660a89ecaf32466ef97")
        plaintext = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
        for _ in range(64):
            assert decryptor(ciphertext) == plaintext

    def test_jenk_hash_known_vectors(self) -> None:
        assert jenk_hash("") == 0
        assert jenk_hash("a") == 3392050242
        assert jenk_hash("test") == 1064684737
        assert jenk_hash("CMapData") == 1657461232
        assert jenk_hash("CMapData") == jenk_hash("cmapdata")
        assert jenk_hash("ymap") == 3417157092

    def test_jenk_hash_many_matches_scalar_hashing(self) -> None:
        from fivefury.hashing import jenk_hash, jenk_hash_many

        values = ["", "test", b"CMapData", "prop_tree_pine_01"]
        assert jenk_hash_many(value for value in values) == [
            jenk_hash(value) for value in values
        ]

    def test_compact_index_exports_paths_in_insertion_order(self) -> None:
        from fivefury._native import CompactIndex

        index = CompactIndex()
        index.record("maps/alpha.ymap", 1, 10, 10)
        index.record("types/beta.ytyp", 2, 20, 20)
        assert index.paths() == ["maps/alpha.ymap", "types/beta.ytyp"]

    def test_jenk_partial_hash_known_vectors(self) -> None:
        from fivefury.hashing import jenk_finalize_hash, jenk_hash, jenk_partial_hash

        assert jenk_partial_hash("") == 0
        assert jenk_partial_hash("a") == 98928
        assert jenk_partial_hash("test") == 285259436
        assert jenk_partial_hash("CMapData") == 3321512860
        assert jenk_partial_hash('"quoted"suffix') == 3628075422
        assert jenk_partial_hash("abc\x00def") == 1486459893
        assert jenk_finalize_hash(jenk_partial_hash("prop_tree_pine_01")) == jenk_hash(
            "prop_tree_pine_01"
        )

    def test_jenk_finalize_hash_known_vectors(self) -> None:
        from fivefury.hashing import jenk_finalize_hash

        assert jenk_finalize_hash(0) == 0
        assert jenk_finalize_hash(98928) == 3392050242
        assert jenk_finalize_hash(285259436) == 1064684737
        assert jenk_finalize_hash(3321512860) == 1657461232
        assert jenk_finalize_hash(7616480156) == 1657461232

    def test_jenk_continue_hash_extends_serialized_partial_state(self) -> None:
        from fivefury.hashing import (
            jenk_continue_hash,
            jenk_finalize_hash,
            jenk_hash,
            jenk_partial_hash,
        )

        partial = jenk_partial_hash("prop_box.001")
        assert jenk_finalize_hash(jenk_continue_hash(partial, "-3")) == jenk_hash(
            "prop_box.001-3"
        )

    def test_crypto_magic_mask_known_vectors(self) -> None:
        from fivefury._native import crypto_magic_mask

        assert (
            crypto_magic_mask(123456789, 16).hex() == "3e39f9fe36d49b7e9075cb0a45af4c71"
        )
        assert (
            crypto_magic_mask(-123456789, 16).hex()
            == "3e39f9fe36d49b7e9075cb0a45af4c71"
        )
        assert (
            crypto_magic_mask(-2147483648, 16).hex()
            == "4460a1c7a9963f0813c90d207694fd3a"
        )

    def test_global_hash_resolver_register_and_resolve(self) -> None:
        clear_hash_resolver()
        register_name("prop_tree_pine_01")
        prop_hash = jenk_hash("prop_tree_pine_01")
        assert resolve_hash(prop_hash) == "prop_tree_pine_01"
        assert hash_matches(prop_hash, "prop_tree_pine_01")

    def test_gamefilecache_can_populate_global_resolver_from_indexed_assets(
        self,
    ) -> None:
        clear_hash_resolver()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            maps = root / "maps"
            maps.mkdir(parents=True, exist_ok=True)
            (maps / "test_alpha.ymap").write_bytes(b"dummy")
            (maps / "test_beta.ytyp").write_bytes(b"dummy")
            cache = GameFileCache(root)
            cache.scan()
            cache.populate_resolver()
        assert resolve_hash(jenk_hash("test_alpha")) == "test_alpha"
        assert resolve_hash(jenk_hash("test_beta")) == "test_beta"

    def test_global_hash_resolver_registers_names_from_text_file(self) -> None:
        clear_hash_resolver()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "names.txt"
            path.write_text(
                "# comment\nprop_tree_pine_01\n\nprop_sign_road_01\n; another comment\n// one more comment\n",
                encoding="utf-8",
            )
            hashes = register_names_file(path)
        assert len(hashes) == 2
        assert resolve_hash(jenk_hash("prop_tree_pine_01")) == "prop_tree_pine_01"
        assert resolve_hash(jenk_hash("prop_sign_road_01")) == "prop_sign_road_01"

    def test_metahash_exposes_string_and_integer_views(self) -> None:
        clear_hash_resolver()
        register_name("prop_tree_pine_01")
        prop_hash = jenk_hash("prop_tree_pine_01")
        value = MetaHash(prop_hash)
        assert int(value) == prop_hash
        assert value.hash == prop_hash
        assert value.uint == prop_hash
        assert value.string == "prop_tree_pine_01"
        assert str(value) == "prop_tree_pine_01"

    def test_metahash_serializes_through_meta_builder(self) -> None:
        root_name_hash = jenk_hash("CTestHash")
        field_hash = jenk_hash("name")
        struct_info = MetaStructInfo(
            name_hash=root_name_hash,
            key=1,
            unknown=0,
            structure_size=4,
            entries=[
                MetaFieldInfo(
                    name_hash=field_hash,
                    data_offset=0,
                    data_type=MetaDataType.HASH,
                    unknown_9h=0,
                    reference_type_index=0,
                    reference_key=0,
                )
            ],
        )
        payload_from_str = build_meta_system(
            root_name_hash=root_name_hash,
            root_value={"name": "prop_tree_pine_01"},
            struct_infos=[struct_info],
            enum_infos=[],
        )
        payload_from_hash = build_meta_system(
            root_name_hash=root_name_hash,
            root_value={"name": MetaHash("prop_tree_pine_01")},
            struct_infos=[struct_info],
            enum_infos=[],
        )
        assert payload_from_hash == payload_from_str

    def test_ymap_and_ytyp_store_hash_fields_as_metahash(self) -> None:
        clear_hash_resolver()
        register_name("prop_tree_pine_01")
        prop_hash = jenk_hash("prop_tree_pine_01")
        entity = Entity(archetype_name=prop_hash)
        archetype = Archetype(name=prop_hash, asset_name=prop_hash)
        ymap = Ymap(
            name="sample.ymap", parent=prop_hash, physics_dictionaries=[prop_hash]
        )
        ytyp = Ytyp(name="sample.ytyp", dependencies=[prop_hash])
        assert isinstance(entity.archetype_name, MetaHash)
        assert int(entity.archetype_name) == prop_hash
        assert str(entity.archetype_name) == "prop_tree_pine_01"
        assert isinstance(archetype.name, MetaHash)
        assert str(archetype.name) == "prop_tree_pine_01"
        assert str(archetype.asset_name) == "prop_tree_pine_01"
        assert isinstance(ymap.name, MetaHash)
        assert str(ymap.name) == "sample"
        assert str(ymap.parent) == "prop_tree_pine_01"
        assert str(ymap.physics_dictionaries[0]) == "prop_tree_pine_01"
        assert isinstance(ytyp.name, MetaHash)
        assert str(ytyp.name) == "sample"
        assert str(ytyp.dependencies[0]) == "prop_tree_pine_01"
