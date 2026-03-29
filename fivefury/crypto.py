from __future__ import annotations

import base64
import ctypes
import hashlib
import importlib.resources
import json
import mmap
import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from .hashing import jenk_hash

NONE_ENCRYPTION: Final[int] = 0
OPEN_ENCRYPTION: Final[int] = 0x4E45504F
AES_ENCRYPTION: Final[int] = 0x0FFFFFF9
NG_ENCRYPTION: Final[int] = 0x0FEFFFFF

_AES_KEY_SHA1: Final[bytes] = bytes(
    [0xA0, 0x79, 0x61, 0x28, 0xA7, 0x75, 0x72, 0x0A, 0xC2, 0x04, 0xD9, 0x81, 0x9F, 0x68, 0xC1, 0x72, 0xE3, 0x95, 0x2C, 0x6D]
)
_NG_KEYS_SIZE: Final[int] = 27472
_NG_TABLES_SIZE: Final[int] = 278528
_NG_BLOB_SIZE: Final[int] = _NG_KEYS_SIZE + _NG_TABLES_SIZE
_MAGIC_SEGMENT_SIZES: Final[tuple[int, int, int, int]] = (_NG_KEYS_SIZE, _NG_TABLES_SIZE, 256, 16)

_default_crypto: "GameCrypto | None" = None


class DotNetRandom:
    _MBIG: Final[int] = 2147483647
    _MSEED: Final[int] = 161803398

    def __init__(self, seed: int) -> None:
        if seed == -2147483648:
            subtraction = self._MBIG
        else:
            subtraction = abs(int(seed))
        mj = self._MSEED - subtraction
        if mj < 0:
            mj += self._MBIG
        self._seed_array = [0] * 56
        self._seed_array[55] = mj
        mk = 1
        for i in range(1, 55):
            ii = (21 * i) % 55
            self._seed_array[ii] = mk
            mk = mj - mk
            if mk < 0:
                mk += self._MBIG
            mj = self._seed_array[ii]
        for _ in range(4):
            for i in range(1, 56):
                self._seed_array[i] -= self._seed_array[1 + (i + 30) % 55]
                if self._seed_array[i] < 0:
                    self._seed_array[i] += self._MBIG
        self._inext = 0
        self._inextp = 21

    def _internal_sample(self) -> int:
        loc_inext = self._inext + 1
        if loc_inext >= 56:
            loc_inext = 1
        loc_inextp = self._inextp + 1
        if loc_inextp >= 56:
            loc_inextp = 1
        ret = self._seed_array[loc_inext] - self._seed_array[loc_inextp]
        if ret == self._MBIG:
            ret -= 1
        if ret < 0:
            ret += self._MBIG
        self._seed_array[loc_inext] = ret
        self._inext = loc_inext
        self._inextp = loc_inextp
        return ret

    def next_bytes(self, buffer: bytearray) -> None:
        for i in range(len(buffer)):
            buffer[i] = self._internal_sample() % 256


class _AesEcbCipher:
    def __init__(self, key: bytes) -> None:
        self._key = bytes(key)
        self._decryptor = self._build_decryptor(self._key)

    def decrypt(self, data: bytes) -> bytes:
        if not data:
            return b""
        aligned = len(data) - (len(data) % 16)
        if aligned <= 0:
            return bytes(data)
        prefix = self._decryptor(data[:aligned])
        if aligned == len(data):
            return prefix
        return prefix + data[aligned:]

    @staticmethod
    def _build_decryptor(key: bytes):
        try:
            from Cryptodome.Cipher import AES  # type: ignore[import-not-found]

            cipher = AES.new(key, AES.MODE_ECB)
            return cipher.decrypt
        except Exception:
            pass
        try:
            from Crypto.Cipher import AES  # type: ignore[import-not-found]

            cipher = AES.new(key, AES.MODE_ECB)
            return cipher.decrypt
        except Exception:
            pass
        if os.name != "nt":
            raise RuntimeError("AES decryption requires PyCryptodome or Windows CNG")
        return _build_windows_aes_decryptor(key)


def _build_windows_aes_decryptor(key: bytes):
    class _WindowsAesDecryptor:
        def __init__(self, material: bytes) -> None:
            bcrypt = ctypes.WinDLL("bcrypt")
            self._c_void_p = ctypes.c_void_p
            self._u32 = ctypes.c_ulong
            self._uchar_p = ctypes.POINTER(ctypes.c_ubyte)
            self._bcrypt = bcrypt

            self._BCryptOpenAlgorithmProvider = bcrypt.BCryptOpenAlgorithmProvider
            self._BCryptOpenAlgorithmProvider.argtypes = [ctypes.POINTER(self._c_void_p), ctypes.c_wchar_p, ctypes.c_wchar_p, self._u32]
            self._BCryptOpenAlgorithmProvider.restype = ctypes.c_long

            self._BCryptSetProperty = bcrypt.BCryptSetProperty
            self._BCryptSetProperty.argtypes = [self._c_void_p, ctypes.c_wchar_p, self._uchar_p, self._u32, self._u32]
            self._BCryptSetProperty.restype = ctypes.c_long

            self._BCryptGetProperty = bcrypt.BCryptGetProperty
            self._BCryptGetProperty.argtypes = [self._c_void_p, ctypes.c_wchar_p, self._uchar_p, self._u32, ctypes.POINTER(self._u32), self._u32]
            self._BCryptGetProperty.restype = ctypes.c_long

            self._BCryptGenerateSymmetricKey = bcrypt.BCryptGenerateSymmetricKey
            self._BCryptGenerateSymmetricKey.argtypes = [self._c_void_p, ctypes.POINTER(self._c_void_p), self._uchar_p, self._u32, self._uchar_p, self._u32, self._u32]
            self._BCryptGenerateSymmetricKey.restype = ctypes.c_long

            self._BCryptDecrypt = bcrypt.BCryptDecrypt
            self._BCryptDecrypt.argtypes = [self._c_void_p, self._uchar_p, self._u32, self._c_void_p, self._uchar_p, self._u32, self._uchar_p, self._u32, ctypes.POINTER(self._u32), self._u32]
            self._BCryptDecrypt.restype = ctypes.c_long

            self._BCryptDestroyKey = bcrypt.BCryptDestroyKey
            self._BCryptDestroyKey.argtypes = [self._c_void_p]
            self._BCryptDestroyKey.restype = ctypes.c_long

            self._BCryptCloseAlgorithmProvider = bcrypt.BCryptCloseAlgorithmProvider
            self._BCryptCloseAlgorithmProvider.argtypes = [self._c_void_p, self._u32]
            self._BCryptCloseAlgorithmProvider.restype = ctypes.c_long

            self._alg = self._c_void_p()
            self._key_handle = self._c_void_p()
            self._key_obj = None
            self._key_buf = None

            self._check(
                self._BCryptOpenAlgorithmProvider(ctypes.byref(self._alg), "AES", None, 0),
                "BCryptOpenAlgorithmProvider",
            )
            try:
                mode = ctypes.create_unicode_buffer("ChainingModeECB")
                self._check(
                    self._BCryptSetProperty(
                        self._alg,
                        "ChainingMode",
                        ctypes.cast(mode, self._uchar_p),
                        ctypes.sizeof(mode),
                        0,
                    ),
                    "BCryptSetProperty",
                )
                obj_len = self._u32()
                cb_result = self._u32()
                self._check(
                    self._BCryptGetProperty(
                        self._alg,
                        "ObjectLength",
                        ctypes.cast(ctypes.byref(obj_len), self._uchar_p),
                        ctypes.sizeof(obj_len),
                        ctypes.byref(cb_result),
                        0,
                    ),
                    "BCryptGetProperty",
                )
                self._key_obj = (ctypes.c_ubyte * obj_len.value)()
                self._key_buf = (ctypes.c_ubyte * len(material)).from_buffer_copy(material)
                self._check(
                    self._BCryptGenerateSymmetricKey(
                        self._alg,
                        ctypes.byref(self._key_handle),
                        self._key_obj,
                        obj_len.value,
                        self._key_buf,
                        len(material),
                        0,
                    ),
                    "BCryptGenerateSymmetricKey",
                )
            except Exception:
                self.close()
                raise

        @staticmethod
        def _check(status: int, message: str) -> None:
            if status < 0:
                raise OSError(f"{message} failed with NTSTATUS 0x{status & 0xFFFFFFFF:08X}")

        def decrypt(self, payload: bytes) -> bytes:
            if not payload:
                return b""
            in_buf = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
            out_buf = (ctypes.c_ubyte * len(payload))()
            out_len = self._u32()
            self._check(
                self._BCryptDecrypt(
                    self._key_handle,
                    in_buf,
                    len(payload),
                    None,
                    None,
                    0,
                    out_buf,
                    len(payload),
                    ctypes.byref(out_len),
                    0,
                ),
                "BCryptDecrypt",
            )
            return bytes(out_buf[: out_len.value])

        def close(self) -> None:
            if getattr(self, "_key_handle", None) is not None and self._key_handle.value:
                try:
                    self._BCryptDestroyKey(self._key_handle)
                except Exception:
                    pass
                self._key_handle = self._c_void_p()
            if getattr(self, "_alg", None) is not None and self._alg.value:
                try:
                    self._BCryptCloseAlgorithmProvider(self._alg, 0)
                except Exception:
                    pass
                self._alg = self._c_void_p()

        def __del__(self) -> None:
            self.close()

    return _WindowsAesDecryptor(key).decrypt


def _decompress_any(data: bytes) -> bytes:
    for wbits in (-15, zlib.MAX_WBITS, zlib.MAX_WBITS | 32):
        try:
            return zlib.decompress(data, wbits)
        except zlib.error:
            pass
    raise ValueError("Unable to decompress deflate stream")


def _to_signed_i32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value if value < 0x80000000 else value - 0x100000000


def _search_sha1_window(exe_path: Path, digest: bytes, *, length: int, align: int = 8) -> bytes:
    with exe_path.open("rb") as fh:
        with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            limit = max(0, len(mm) - length + 1)
            for offset in range(0, limit, align):
                block = mm[offset : offset + length]
                if hashlib.sha1(block).digest() == digest:
                    return bytes(block)
    raise ValueError(f"Unable to locate AES key in {exe_path}")


def _default_magic_path() -> Path:
    package_magic = importlib.resources.files("fivefury").joinpath("data", "magic.dat")
    if package_magic.is_file():
        return Path(str(package_magic))
    fallback = Path(__file__).resolve().parents[1] / "references" / "CodeWalker.Core" / "Resources" / "magic.dat"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError("magic.dat was not found")


def _read_packaged_data(name: str) -> tuple[bytes, str] | None:
    resource = importlib.resources.files("fivefury").joinpath("data", name)
    if resource.is_file():
        return resource.read_bytes(), str(resource)
    fallback = Path(__file__).resolve().parent / "data" / name
    if fallback.is_file():
        return fallback.read_bytes(), str(fallback)
    return None


def _default_cache_path() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else (Path.home() / ".cache")
    return base / "fivefury" / "keys.json"


def _load_cache(path: Path) -> dict[str, dict[str, object]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(path: Path, payload: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _resolve_exe_path(root_or_exe: str | Path | None, *, gen9: bool = False) -> Path:
    if root_or_exe is None:
        raise ValueError("game root or exe path is required")
    path = Path(root_or_exe)
    if path.is_file():
        return path
    candidates = ["gta5_enhanced.exe", "gta5.exe"] if gen9 else ["gta5.exe", "gta5_enhanced.exe"]
    for name in candidates:
        candidate = path / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not locate a GTA V executable in {path}")


def _decode_magic_payload(aes_key: bytes, magic_bytes: bytes) -> bytes:
    random_bytes = []
    rng = DotNetRandom(_to_signed_i32(jenk_hash(aes_key)))
    for _ in range(4):
        block = bytearray(len(magic_bytes))
        rng.next_bytes(block)
        random_bytes.append(block)
    decoded = bytearray(len(magic_bytes))
    rb1, rb2, rb3, rb4 = random_bytes
    for i, value in enumerate(magic_bytes):
        decoded[i] = (value - rb1[i] - rb2[i] - rb3[i] - rb4[i]) & 0xFF
    decrypted = _AesEcbCipher(aes_key).decrypt(bytes(decoded))
    return _decompress_any(decrypted)


def _decode_magic_sections(aes_key: bytes, magic_path: Path) -> tuple[tuple[bytes, ...], tuple[tuple[tuple[int, ...], ...], ...]]:
    payload = _decode_magic_payload(aes_key, magic_path.read_bytes())
    return _decode_ng_blob(payload)


def _decode_ng_blob(payload: bytes) -> tuple[tuple[bytes, ...], tuple[tuple[tuple[int, ...], ...], ...]]:
    if len(payload) < _NG_BLOB_SIZE:
        raise ValueError(f"NG payload is truncated: expected at least {_NG_BLOB_SIZE} bytes, got {len(payload)}")
    keys_data = payload[:_NG_KEYS_SIZE]
    tables_data = payload[_NG_KEYS_SIZE : _NG_KEYS_SIZE + _NG_TABLES_SIZE]
    ng_keys = tuple(keys_data[i : i + 272] for i in range(0, len(keys_data), 272))
    tables: list[tuple[tuple[int, ...], ...]] = []
    offset = 0
    for _ in range(17):
        round_tables: list[tuple[int, ...]] = []
        for _ in range(16):
            round_tables.append(struct.unpack_from("<256I", tables_data, offset))
            offset += 1024
        tables.append(tuple(round_tables))
    return ng_keys, tuple(tables)


def _load_ng_sections(ng_path: Path) -> tuple[tuple[bytes, ...], tuple[tuple[tuple[int, ...], ...], ...]]:
    return _decode_ng_blob(ng_path.read_bytes())


@dataclass(slots=True)
class GameCrypto:
    aes_key: bytes
    ng_keys: tuple[bytes, ...]
    ng_tables: tuple[tuple[tuple[int, ...], ...], ...]
    ng_blob: bytes = b""
    magic_path: str = ""
    _aes: _AesEcbCipher = field(init=False, repr=False, compare=False)
    _ng_subkeys: tuple[tuple[tuple[int, int, int, int], ...], ...] = field(init=False, repr=False, compare=False)
    _native_context: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.aes_key = bytes(self.aes_key)
        self.ng_keys = tuple(bytes(key) for key in self.ng_keys)
        self.ng_tables = tuple(tuple(tuple(table) for table in round_tables) for round_tables in self.ng_tables)
        self.ng_blob = bytes(self.ng_blob)
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
        if source_path is not None:
            if source_path.name.lower() == "ng.dat" or source_path.stat().st_size == _NG_BLOB_SIZE:
                ng_blob = source_path.read_bytes()
                ng_keys, ng_tables = _decode_ng_blob(ng_blob)
            else:
                ng_blob = _decode_magic_payload(aes_bytes, source_path.read_bytes())
                ng_keys, ng_tables = _decode_ng_blob(ng_blob)
            return cls(
                aes_key=aes_bytes,
                ng_keys=ng_keys,
                ng_tables=ng_tables,
                ng_blob=ng_blob,
                magic_path=str(source_path),
            )

        packaged_ng = _read_packaged_data("ng.dat")
        if packaged_ng is not None:
            ng_blob = packaged_ng[0]
            ng_keys, ng_tables = _decode_ng_blob(ng_blob)
            return cls(
                aes_key=aes_bytes,
                ng_keys=ng_keys,
                ng_tables=ng_tables,
                ng_blob=ng_blob,
                magic_path=packaged_ng[1],
            )

        magic = _default_magic_path()
        ng_blob = _decode_magic_payload(aes_bytes, magic.read_bytes())
        ng_keys, ng_tables = _decode_ng_blob(ng_blob)
        return cls(
            aes_key=aes_bytes,
            ng_keys=ng_keys,
            ng_tables=ng_tables,
            ng_blob=ng_blob,
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
        from .hashing import _get_lut
        return self.native_context().decrypt_archive_table(data, encryption, archive_name, archive_size, _get_lut())

    def decrypt_entry_payload(self, data: bytes, encryption: int, *, entry_name: str, entry_length: int) -> bytes:
        if not data:
            return b""
        if encryption in (NONE_ENCRYPTION, OPEN_ENCRYPTION):
            return data
        from .hashing import _get_lut
        return self.native_context().decrypt_data(data, encryption, entry_name, entry_length, _get_lut())

    def clone_for_worker(self) -> "GameCrypto":
        clone = object.__new__(GameCrypto)
        clone.aes_key = self.aes_key
        clone.ng_keys = self.ng_keys
        clone.ng_tables = self.ng_tables
        clone.ng_blob = self.ng_blob
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
            from ._native import NativeCryptoContext

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
    "get_game_crypto",
    "load_game_keys",
    "set_game_crypto",
]
