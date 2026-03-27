from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import resolve_symbol


def _hash_value(symbol, value: str) -> int:
    if symbol is None:
        raise AssertionError("hash symbol missing")
    if hasattr(symbol.value, "GenHash"):
        return int(symbol.value.GenHash(value))
    if callable(symbol.value):
        return int(symbol.value(value))
    raise AssertionError(f"Unsupported hash API: {symbol.module_name}.{symbol.symbol_name}")


class HashingContractTests(unittest.TestCase):
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
        self.assertEqual(_hash_value(symbol, "CMapData"), 0xD3593FA6)
        self.assertEqual(_hash_value(symbol, "ymap"), 0xCBADADE4)

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

    def test_gamefilecache_registers_loose_file_stems_in_global_resolver(self) -> None:
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

        self.assertEqual(resolve_symbol_value.value(_hash_value(hash_symbol, "test_alpha")), "test_alpha")
        self.assertEqual(resolve_symbol_value.value(_hash_value(hash_symbol, "test_beta")), "test_beta")


if __name__ == "__main__":
    unittest.main()

