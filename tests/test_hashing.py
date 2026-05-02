from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.compat import PytestCompat
from tests.helpers import resolve_symbol


def _hash_value(symbol, value: str) -> int:
    if symbol is None:
        raise AssertionError("hash symbol missing")
    if hasattr(symbol.value, "GenHash"):
        return int(symbol.value.GenHash(value))
    if callable(symbol.value):
        return int(symbol.value(value))
    raise AssertionError(f"Unsupported hash API: {symbol.module_name}.{symbol.symbol_name}")


class HashingContractTests(PytestCompat):
    def test_windows_aes_decryptor_reuses_handles_across_many_calls(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows CNG AES regression test is only relevant on Windows")

        import fivefury.crypto as crypto_module

        decryptor = crypto_module._build_windows_aes_decryptor(  # type: ignore[attr-defined]
            bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        )
        ciphertext = bytes.fromhex("3ad77bb40d7a3660a89ecaf32466ef97")
        plaintext = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")

        for _ in range(64):
            self.assertEqual(decryptor(ciphertext), plaintext)

    def test_jenk_hash_known_vectors(self) -> None:
        symbol = resolve_symbol(
            [
                "fivefury.hashing",
                "fivefury.gta5.hashing",
                "fivefury.core.hashing",
                "fivefury",
            ],
            ["jenk_hash", "hash_jenk", "GenHash", "JenkHash"],
        )
        if symbol is None:
            self.skipTest("hashing API not implemented yet")

        self.assertEqual(_hash_value(symbol, ""), 0)
        self.assertEqual(_hash_value(symbol, "a"), 0xCA2E9442)
        self.assertEqual(_hash_value(symbol, "test"), 0x3F75CCC1)
        self.assertEqual(_hash_value(symbol, "CMapData"), 0x62CAD9F0)
        self.assertEqual(_hash_value(symbol, "CMapData"), _hash_value(symbol, "cmapdata"))
        self.assertEqual(_hash_value(symbol, "ymap"), 0xCBADADE4)

    def test_jenk_partial_hash_known_vectors(self) -> None:
        from fivefury.hashing import jenk_finalize_hash, jenk_hash, jenk_partial_hash

        self.assertEqual(jenk_partial_hash(""), 0)
        self.assertEqual(jenk_partial_hash("a"), 0x00018270)
        self.assertEqual(jenk_partial_hash("test"), 0x1100B6AC)
        self.assertEqual(jenk_partial_hash("CMapData"), 0xC5FA439C)
        self.assertEqual(jenk_partial_hash('"quoted"suffix'), 0xD840099E)
        self.assertEqual(jenk_partial_hash("abc\x00def"), 0x589993F5)
        self.assertEqual(jenk_finalize_hash(jenk_partial_hash("prop_tree_pine_01")), jenk_hash("prop_tree_pine_01"))

    def test_jenk_finalize_hash_known_vectors(self) -> None:
        from fivefury.hashing import jenk_finalize_hash

        self.assertEqual(jenk_finalize_hash(0), 0)
        self.assertEqual(jenk_finalize_hash(0x00018270), 0xCA2E9442)
        self.assertEqual(jenk_finalize_hash(0x1100B6AC), 0x3F75CCC1)
        self.assertEqual(jenk_finalize_hash(0xC5FA439C), 0x62CAD9F0)
        self.assertEqual(jenk_finalize_hash(0x1C5FA439C), 0x62CAD9F0)

    def test_crypto_magic_mask_known_vectors(self) -> None:
        from fivefury._native import crypto_magic_mask

        self.assertEqual(crypto_magic_mask(123456789, 16).hex(), "3e39f9fe36d49b7e9075cb0a45af4c71")
        self.assertEqual(crypto_magic_mask(-123456789, 16).hex(), "3e39f9fe36d49b7e9075cb0a45af4c71")
        self.assertEqual(crypto_magic_mask(-2147483648, 16).hex(), "4460a1c7a9963f0813c90d207694fd3a")

    def test_global_hash_resolver_register_and_resolve(self) -> None:
        register_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["register_name"],
        )
        resolve_symbol_value = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["resolve_hash"],
        )
        clear_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["clear_hash_resolver"],
        )
        matches_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["hash_matches"],
        )
        hash_symbol = resolve_symbol(
            ["fivefury.hashing", "fivefury"],
            ["jenk_hash", "hash_jenk", "GenHash", "JenkHash"],
        )
        if None in (register_symbol, resolve_symbol_value, clear_symbol, matches_symbol, hash_symbol):
            self.skipTest("hash resolver API not implemented yet")

        clear_symbol.value()
        register_symbol.value("prop_tree_pine_01")
        prop_hash = _hash_value(hash_symbol, "prop_tree_pine_01")

        self.assertEqual(resolve_symbol_value.value(prop_hash), "prop_tree_pine_01")
        self.assertTrue(matches_symbol.value(prop_hash, "prop_tree_pine_01"))

    def test_gamefilecache_can_populate_global_resolver_from_indexed_assets(self) -> None:
        cache_symbol = resolve_symbol(
            ["fivefury.cache", "fivefury"],
            ["GameFileCache"],
        )
        resolve_symbol_value = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["resolve_hash"],
        )
        clear_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["clear_hash_resolver"],
        )
        hash_symbol = resolve_symbol(
            ["fivefury.hashing", "fivefury"],
            ["jenk_hash", "hash_jenk", "GenHash", "JenkHash"],
        )
        if None in (cache_symbol, resolve_symbol_value, clear_symbol, hash_symbol):
            self.skipTest("resolver/cache API not implemented yet")

        clear_symbol.value()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            maps = root / "maps"
            maps.mkdir(parents=True, exist_ok=True)
            (maps / "test_alpha.ymap").write_bytes(b"dummy")
            (maps / "test_beta.ytyp").write_bytes(b"dummy")

            cache = cache_symbol.value(root)
            cache.scan()
            populate = getattr(cache, "populate_resolver", None)
            if callable(populate):
                populate()

        self.assertEqual(resolve_symbol_value.value(_hash_value(hash_symbol, "test_alpha")), "test_alpha")
        self.assertEqual(resolve_symbol_value.value(_hash_value(hash_symbol, "test_beta")), "test_beta")

    def test_global_hash_resolver_registers_names_from_text_file(self) -> None:
        register_file_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["register_names_file"],
        )
        resolve_symbol_value = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["resolve_hash"],
        )
        clear_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["clear_hash_resolver"],
        )
        hash_symbol = resolve_symbol(
            ["fivefury.hashing", "fivefury"],
            ["jenk_hash", "hash_jenk", "GenHash", "JenkHash"],
        )
        if None in (register_file_symbol, resolve_symbol_value, clear_symbol, hash_symbol):
            self.skipTest("text-file resolver API not implemented yet")

        clear_symbol.value()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "names.txt"
            path.write_text(
                "# comment\n"
                "prop_tree_pine_01\n"
                "\n"
                "prop_sign_road_01\n"
                "; another comment\n"
                "// one more comment\n",
                encoding="utf-8",
            )
            hashes = register_file_symbol.value(path)

        self.assertEqual(len(hashes), 2)
        self.assertEqual(resolve_symbol_value.value(_hash_value(hash_symbol, "prop_tree_pine_01")), "prop_tree_pine_01")
        self.assertEqual(resolve_symbol_value.value(_hash_value(hash_symbol, "prop_sign_road_01")), "prop_sign_road_01")

    def test_metahash_exposes_string_and_integer_views(self) -> None:
        metahash_symbol = resolve_symbol(
            ["fivefury.metahash", "fivefury"],
            ["MetaHash", "HashString"],
        )
        register_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["register_name"],
        )
        clear_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["clear_hash_resolver"],
        )
        hash_symbol = resolve_symbol(
            ["fivefury.hashing", "fivefury"],
            ["jenk_hash", "hash_jenk", "GenHash", "JenkHash"],
        )
        if None in (metahash_symbol, register_symbol, clear_symbol, hash_symbol):
            self.skipTest("MetaHash API not implemented yet")

        clear_symbol.value()
        register_symbol.value("prop_tree_pine_01")
        prop_hash = _hash_value(hash_symbol, "prop_tree_pine_01")

        value = metahash_symbol.value(prop_hash)

        self.assertEqual(int(value), prop_hash)
        self.assertEqual(value.hash, prop_hash)
        self.assertEqual(value.uint, prop_hash)
        self.assertEqual(value.string, "prop_tree_pine_01")
        self.assertEqual(str(value), "prop_tree_pine_01")

    def test_metahash_serializes_through_meta_builder(self) -> None:
        metahash_symbol = resolve_symbol(
            ["fivefury.metahash", "fivefury"],
            ["MetaHash", "HashString"],
        )
        build_symbol = resolve_symbol(
            ["fivefury.meta", "fivefury"],
            ["build_meta_system"],
        )
        struct_symbol = resolve_symbol(
            ["fivefury.meta", "fivefury"],
            ["MetaStructInfo"],
        )
        field_symbol = resolve_symbol(
            ["fivefury.meta", "fivefury"],
            ["MetaFieldInfo"],
        )
        type_symbol = resolve_symbol(
            ["fivefury.meta", "fivefury"],
            ["MetaDataType"],
        )
        hash_symbol = resolve_symbol(
            ["fivefury.hashing", "fivefury"],
            ["jenk_hash", "hash_jenk", "GenHash", "JenkHash"],
        )
        if None in (metahash_symbol, build_symbol, struct_symbol, field_symbol, type_symbol, hash_symbol):
            self.skipTest("MetaBuilder API not implemented yet")

        root_name_hash = _hash_value(hash_symbol, "CTestHash")
        field_hash = _hash_value(hash_symbol, "name")
        struct_info = struct_symbol.value(
            name_hash=root_name_hash,
            key=1,
            unknown=0,
            structure_size=4,
            entries=[
                field_symbol.value(
                    name_hash=field_hash,
                    data_offset=0,
                    data_type=type_symbol.value.HASH,
                    unknown_9h=0,
                    reference_type_index=0,
                    reference_key=0,
                )
            ],
        )

        payload_from_str = build_symbol.value(
            root_name_hash=root_name_hash,
            root_value={"name": "prop_tree_pine_01"},
            struct_infos=[struct_info],
            enum_infos=[],
        )
        payload_from_hash = build_symbol.value(
            root_name_hash=root_name_hash,
            root_value={"name": metahash_symbol.value("prop_tree_pine_01")},
            struct_infos=[struct_info],
            enum_infos=[],
        )

        self.assertEqual(payload_from_hash, payload_from_str)

    def test_ymap_and_ytyp_store_hash_fields_as_metahash(self) -> None:
        metahash_symbol = resolve_symbol(
            ["fivefury.metahash", "fivefury"],
            ["MetaHash", "HashString"],
        )
        entity_symbol = resolve_symbol(
            ["fivefury.ymap", "fivefury"],
            ["Entity", "EntityDef"],
        )
        archetype_symbol = resolve_symbol(
            ["fivefury.ytyp", "fivefury"],
            ["Archetype", "BaseArchetypeDef"],
        )
        ymap_symbol = resolve_symbol(
            ["fivefury.ymap", "fivefury"],
            ["Ymap"],
        )
        ytyp_symbol = resolve_symbol(
            ["fivefury.ytyp", "fivefury"],
            ["Ytyp"],
        )
        hash_symbol = resolve_symbol(
            ["fivefury.hashing", "fivefury"],
            ["jenk_hash", "hash_jenk", "GenHash", "JenkHash"],
        )
        register_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["register_name"],
        )
        clear_symbol = resolve_symbol(
            ["fivefury.resolver", "fivefury"],
            ["clear_hash_resolver"],
        )
        if None in (
            metahash_symbol,
            entity_symbol,
            archetype_symbol,
            ymap_symbol,
            ytyp_symbol,
            hash_symbol,
            register_symbol,
            clear_symbol,
        ):
            self.skipTest("MetaHash model integration not implemented yet")

        clear_symbol.value()
        register_symbol.value("prop_tree_pine_01")
        prop_hash = _hash_value(hash_symbol, "prop_tree_pine_01")

        entity = entity_symbol.value(archetype_name=prop_hash)
        archetype = archetype_symbol.value(name=prop_hash, asset_name=prop_hash)
        ymap = ymap_symbol.value(name="sample.ymap", parent=prop_hash, physics_dictionaries=[prop_hash])
        ytyp = ytyp_symbol.value(name="sample.ytyp", dependencies=[prop_hash])

        self.assertIsInstance(entity.archetype_name, metahash_symbol.value)
        self.assertEqual(int(entity.archetype_name), prop_hash)
        self.assertEqual(str(entity.archetype_name), "prop_tree_pine_01")
        self.assertIsInstance(archetype.name, metahash_symbol.value)
        self.assertEqual(str(archetype.name), "prop_tree_pine_01")
        self.assertEqual(str(archetype.asset_name), "prop_tree_pine_01")
        self.assertIsInstance(ymap.name, metahash_symbol.value)
        self.assertEqual(str(ymap.name), "sample")
        self.assertEqual(str(ymap.parent), "prop_tree_pine_01")
        self.assertEqual(str(ymap.physics_dictionaries[0]), "prop_tree_pine_01")
        self.assertIsInstance(ytyp.name, metahash_symbol.value)
        self.assertEqual(str(ytyp.name), "sample")
        self.assertEqual(str(ytyp.dependencies[0]), "prop_tree_pine_01")


if __name__ == "__main__":
    unittest.main()



