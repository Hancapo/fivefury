from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()

