from __future__ import annotations

import ctypes
import os
import zlib
from typing import Final


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


__all__ = [
    "DotNetRandom",
    "_AesEcbCipher",
    "_build_windows_aes_decryptor",
    "_decompress_any",
    "_to_signed_i32",
]
