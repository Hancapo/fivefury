from __future__ import annotations

import ctypes
import os
import zlib


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
    "_AesEcbCipher",
    "_build_windows_aes_decryptor",
    "_decompress_any",
    "_to_signed_i32",
]
