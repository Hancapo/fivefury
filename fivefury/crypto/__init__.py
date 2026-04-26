from __future__ import annotations

import base64
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from .backends import _AesEcbCipher, _build_windows_aes_decryptor
from .keys import (
    _AES_KEY_SHA1,
    _DEFAULT_AES_KEY_B64,
    _DEFAULT_AWC_KEY,
    _NG_BLOB_SIZE,
    _decode_awc_key,
    _decode_magic_payload,
    _decode_ng_blob,
    _default_cache_path,
    _default_magic_path,
    _load_cache,
    _read_packaged_data,
    _resolve_exe_path,
    _save_cache,
    _search_sha1_window,
)
from ..hashing import jenk_hash

NONE_ENCRYPTION: Final[int] = 0
OPEN_ENCRYPTION: Final[int] = 0x4E45504F
AES_ENCRYPTION: Final[int] = 0x0FFFFFF9
NG_ENCRYPTION: Final[int] = 0x0FEFFFFF

_default_crypto: "GameCrypto | None" = None


@dataclass(slots=True)
class GameCrypto:
    aes_key: bytes
    ng_keys: tuple[bytes, ...]
    ng_tables: tuple[tuple[tuple[int, ...], ...], ...]
    ng_blob: bytes = b""
    awc_key: tuple[int, int, int, int] | None = None
    magic_path: str = ""
    _aes: _AesEcbCipher = field(init=False, repr=False, compare=False)
    _ng_subkeys: tuple[tuple[tuple[int, int, int, int], ...], ...] = field(init=False, repr=False, compare=False)
    _native_context: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.aes_key = bytes(self.aes_key)
        self.ng_keys = tuple(bytes(key) for key in self.ng_keys)
        self.ng_tables = tuple(tuple(tuple(table) for table in round_tables) for round_tables in self.ng_tables)
        self.ng_blob = bytes(self.ng_blob)
        self.awc_key = tuple(int(value) & 0xFFFFFFFF for value in self.awc_key) if self.awc_key is not None else None
        self._aes = _AesEcbCipher(self.aes_key)
        self._ng_subkeys = tuple(
            tuple(
                struct.unpack_from("<4I", key, index * 16)
                for index in range(17)
            )
            for key in self.ng_keys
        )

    @classmethod
    def from_aes_key(cls, aes_key: bytes | str, *, magic_path: str | Path | None = None) -> "GameCrypto":
        if isinstance(aes_key, str):
            aes_bytes = base64.b64decode(aes_key)
        else:
            aes_bytes = bytes(aes_key)
        source_path = Path(magic_path) if magic_path is not None else None
        awc_key: tuple[int, int, int, int] | None = None
        if source_path is not None:
            if source_path.name.lower() == "ng.dat" or source_path.stat().st_size == _NG_BLOB_SIZE:
                ng_blob = source_path.read_bytes()
                ng_keys, ng_tables = _decode_ng_blob(ng_blob)
            else:
                ng_blob = _decode_magic_payload(aes_bytes, source_path.read_bytes())
                ng_keys, ng_tables = _decode_ng_blob(ng_blob)
                awc_key = _decode_awc_key(ng_blob)
            return cls(
                aes_key=aes_bytes,
                ng_keys=ng_keys,
                ng_tables=ng_tables,
                ng_blob=ng_blob,
                awc_key=awc_key or _DEFAULT_AWC_KEY,
                magic_path=str(source_path),
            )

        packaged_ng = _read_packaged_data("ng.dat")
        if packaged_ng is not None:
            ng_blob = packaged_ng[0]
            ng_keys, ng_tables = _decode_ng_blob(ng_blob)
            packaged_magic = _read_packaged_data("magic.dat")
            if packaged_magic is not None:
                try:
                    awc_key = _decode_awc_key(_decode_magic_payload(aes_bytes, packaged_magic[0]))
                except Exception:
                    awc_key = None
            return cls(
                aes_key=aes_bytes,
                ng_keys=ng_keys,
                ng_tables=ng_tables,
                ng_blob=ng_blob,
                awc_key=awc_key or _DEFAULT_AWC_KEY,
                magic_path=packaged_ng[1],
            )

        magic = _default_magic_path()
        ng_blob = _decode_magic_payload(aes_bytes, magic.read_bytes())
        ng_keys, ng_tables = _decode_ng_blob(ng_blob)
        awc_key = _decode_awc_key(ng_blob)
        return cls(
            aes_key=aes_bytes,
            ng_keys=ng_keys,
            ng_tables=ng_tables,
            ng_blob=ng_blob,
            awc_key=awc_key or _DEFAULT_AWC_KEY,
            magic_path=str(magic),
        )

    @classmethod
    def from_game(
        cls,
        root_or_exe: str | Path,
        *,
        magic_path: str | Path | None = None,
        gen9: bool = False,
        cache_path: str | Path | None = None,
        use_cache: bool = True,
    ) -> "GameCrypto":
        exe_path = _resolve_exe_path(root_or_exe, gen9=gen9).resolve()
        cache = Path(cache_path) if cache_path is not None else _default_cache_path()
        cache_key = str(exe_path).lower()
        aes_key: bytes | None = None
        if use_cache:
            data = _load_cache(cache)
            item = data.get(cache_key)
            stat = exe_path.stat()
            if isinstance(item, dict):
                if int(item.get("size", -1)) == stat.st_size and int(item.get("mtime_ns", -1)) == stat.st_mtime_ns:
                    encoded = item.get("aes_key")
                    if isinstance(encoded, str):
                        aes_key = base64.b64decode(encoded)
        if aes_key is None:
            aes_key = _search_sha1_window(exe_path, _AES_KEY_SHA1, length=32)
            if use_cache:
                data = _load_cache(cache)
                stat = exe_path.stat()
                data[cache_key] = {
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "aes_key": base64.b64encode(aes_key).decode("ascii"),
                }
                _save_cache(cache, data)
        return cls.from_aes_key(aes_key, magic_path=magic_path)

    def decrypt_aes(self, data: bytes) -> bytes:
        return self._aes.decrypt(data)

    def decrypt_ng(self, data: bytes, name: str, length: int) -> bytes:
        if not data:
            return b""
        key_seed = (jenk_hash(name) + (int(length) & 0xFFFFFFFF) + 61) & 0xFFFFFFFF
        key_index = key_seed % 0x65
        subkeys = self._ng_subkeys[key_index]
        aligned = len(data) - (len(data) % 16)
        if aligned <= 0:
            return bytes(data)
        out = bytearray(len(data))
        for offset in range(0, aligned, 16):
            out[offset : offset + 16] = self._decrypt_ng_block(data[offset : offset + 16], subkeys)
        if aligned < len(data):
            out[aligned:] = data[aligned:]
        return bytes(out)

    def decrypt_archive_table(self, data: bytes, encryption: int, *, archive_name: str, archive_size: int) -> bytes:
        if encryption in (NONE_ENCRYPTION, OPEN_ENCRYPTION):
            return data
        from ..hashing import _get_lut

        return self.native_context().decrypt_archive_table(data, encryption, archive_name, archive_size, _get_lut())

    def decrypt_entry_payload(self, data: bytes, encryption: int, *, entry_name: str, entry_length: int) -> bytes:
        if not data:
            return b""
        if encryption in (NONE_ENCRYPTION, OPEN_ENCRYPTION):
            return data
        from ..hashing import _get_lut

        return self.native_context().decrypt_data(data, encryption, entry_name, entry_length, _get_lut())

    def clone_for_worker(self) -> "GameCrypto":
        clone = object.__new__(GameCrypto)
        clone.aes_key = self.aes_key
        clone.ng_keys = self.ng_keys
        clone.ng_tables = self.ng_tables
        clone.ng_blob = self.ng_blob
        clone.awc_key = self.awc_key
        clone.magic_path = self.magic_path
        clone._aes = _AesEcbCipher(self.aes_key)
        clone._ng_subkeys = self._ng_subkeys
        clone._native_context = self._native_context
        return clone

    def _build_ng_blob(self) -> bytes:
        if self.ng_blob:
            return self.ng_blob
        keys_blob = b"".join(self.ng_keys)
        tables_blob = b"".join(
            struct.pack("<256I", *table)
            for round_tables in self.ng_tables
            for table in round_tables
        )
        self.ng_blob = keys_blob + tables_blob
        return self.ng_blob

    def native_context(self) -> object:
        if self._native_context is None:
            from .._native import NativeCryptoContext

            self._native_context = NativeCryptoContext(self.aes_key, self._build_ng_blob())
        return self._native_context

    def _decrypt_ng_block(self, data: bytes, subkeys: tuple[tuple[int, int, int, int], ...]) -> bytes:
        buffer = data
        buffer = self._decrypt_ng_round_a(buffer, subkeys[0], self.ng_tables[0])
        buffer = self._decrypt_ng_round_a(buffer, subkeys[1], self.ng_tables[1])
        for round_index in range(2, 16):
            buffer = self._decrypt_ng_round_b(buffer, subkeys[round_index], self.ng_tables[round_index])
        buffer = self._decrypt_ng_round_a(buffer, subkeys[16], self.ng_tables[16])
        return buffer

    @staticmethod
    def _decrypt_ng_round_a(data: bytes, key: tuple[int, int, int, int], table: tuple[tuple[int, ...], ...]) -> bytes:
        x1 = table[0][data[0]] ^ table[1][data[1]] ^ table[2][data[2]] ^ table[3][data[3]] ^ key[0]
        x2 = table[4][data[4]] ^ table[5][data[5]] ^ table[6][data[6]] ^ table[7][data[7]] ^ key[1]
        x3 = table[8][data[8]] ^ table[9][data[9]] ^ table[10][data[10]] ^ table[11][data[11]] ^ key[2]
        x4 = table[12][data[12]] ^ table[13][data[13]] ^ table[14][data[14]] ^ table[15][data[15]] ^ key[3]
        return struct.pack("<4I", x1, x2, x3, x4)

    @staticmethod
    def _decrypt_ng_round_b(data: bytes, key: tuple[int, int, int, int], table: tuple[tuple[int, ...], ...]) -> bytes:
        x1 = table[0][data[0]] ^ table[7][data[7]] ^ table[10][data[10]] ^ table[13][data[13]] ^ key[0]
        x2 = table[1][data[1]] ^ table[4][data[4]] ^ table[11][data[11]] ^ table[14][data[14]] ^ key[1]
        x3 = table[2][data[2]] ^ table[5][data[5]] ^ table[8][data[8]] ^ table[15][data[15]] ^ key[2]
        x4 = table[3][data[3]] ^ table[6][data[6]] ^ table[9][data[9]] ^ table[12][data[12]] ^ key[3]
        return struct.pack("<4I", x1, x2, x3, x4)


def get_game_crypto() -> GameCrypto | None:
    return _default_crypto


def set_game_crypto(value: GameCrypto | None) -> GameCrypto | None:
    global _default_crypto
    _default_crypto = value
    return _default_crypto


def clear_game_crypto() -> None:
    set_game_crypto(None)


def ensure_game_crypto(*, aes_key: bytes | str | None = None, magic_path: str | Path | None = None) -> GameCrypto:
    crypto = get_game_crypto()
    if crypto is not None:
        return crypto
    crypto = GameCrypto.from_aes_key(aes_key or _DEFAULT_AES_KEY_B64, magic_path=magic_path)
    set_game_crypto(crypto)
    return crypto


def load_game_keys(
    root_or_exe: str | Path,
    *,
    magic_path: str | Path | None = None,
    aes_key: bytes | str | None = None,
    gen9: bool = False,
    cache_path: str | Path | None = None,
    use_cache: bool = True,
) -> GameCrypto:
    crypto = (
        GameCrypto.from_aes_key(aes_key, magic_path=magic_path)
        if aes_key is not None
        else GameCrypto.from_game(
            root_or_exe,
            magic_path=magic_path,
            gen9=gen9,
            cache_path=cache_path,
            use_cache=use_cache,
        )
    )
    set_game_crypto(crypto)
    return crypto


__all__ = [
    "AES_ENCRYPTION",
    "GameCrypto",
    "NG_ENCRYPTION",
    "NONE_ENCRYPTION",
    "OPEN_ENCRYPTION",
    "clear_game_crypto",
    "ensure_game_crypto",
    "get_game_crypto",
    "load_game_keys",
    "set_game_crypto",
    "_build_windows_aes_decryptor",
]




