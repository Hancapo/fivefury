from __future__ import annotations

from typing import Any

try:
    from . import _native_abi3 as _ffi
except ImportError as exc:
    raise ImportError(
        "fivefury native backend is required; install the bundled abi3 wheel"
    ) from exc


class CompactIndex:
    __slots__ = ("_capsule",)

    def __init__(self) -> None:
        self._capsule = _ffi.index_new()

    def __len__(self) -> int:
        return int(_ffi.index_count(self._capsule))

    def clear(self) -> None:
        _ffi.index_clear(self._capsule)

    def add(
        self,
        path: str,
        kind: int,
        size: int,
        uncompressed_size: int,
        flags: int = 0,
        archive_encryption: int = 0,
        name_hash: int = 0,
        short_hash: int = 0,
    ) -> int:
        return int(
            _ffi.index_add(
                self._capsule,
                str(path),
                int(kind),
                int(size),
                int(uncompressed_size),
                int(flags),
                int(archive_encryption),
                int(name_hash),
                int(short_hash),
            )
        )

    def find_path_id(self, path: str) -> int | None:
        value = _ffi.index_find_path_id(self._capsule, str(path))
        return None if value is None else int(value)

    def find_hash_ids(self, hash_value: int) -> list[int]:
        return [int(item) for item in _ffi.index_find_hash_ids(self._capsule, int(hash_value))]

    def find_kind_ids(self, kind_value: int) -> list[int]:
        return [int(item) for item in _ffi.index_find_kind_ids(self._capsule, int(kind_value))]

    def get_path(self, asset_id: int) -> str:
        return str(_ffi.index_get_path(self._capsule, int(asset_id)))

    def get_kind(self, asset_id: int) -> int:
        return int(_ffi.index_get_kind(self._capsule, int(asset_id)))

    def get_size(self, asset_id: int) -> int:
        return int(_ffi.index_get_size(self._capsule, int(asset_id)))

    def get_uncompressed_size(self, asset_id: int) -> int:
        return int(_ffi.index_get_uncompressed_size(self._capsule, int(asset_id)))

    def get_flags(self, asset_id: int) -> int:
        return int(_ffi.index_get_flags(self._capsule, int(asset_id)))

    def get_archive_encryption(self, asset_id: int) -> int:
        return int(_ffi.index_get_archive_encryption(self._capsule, int(asset_id)))

    def get_name_hash(self, asset_id: int) -> int:
        return int(_ffi.index_get_name_hash(self._capsule, int(asset_id)))

    def get_short_hash(self, asset_id: int) -> int:
        return int(_ffi.index_get_short_hash(self._capsule, int(asset_id)))

    def export_state(self) -> bytes:
        return bytes(_ffi.index_export_state(self._capsule))

    def import_state(self, payload: bytes | bytearray | memoryview) -> None:
        _ffi.index_import_state(self._capsule, bytes(payload))


class NativeCryptoContext:
    __slots__ = ("_capsule",)

    def __init__(self, aes_key: bytes | bytearray | memoryview, ng_blob: bytes | bytearray | memoryview) -> None:
        self._capsule = _ffi.crypto_new(bytes(aes_key), bytes(ng_blob))

    def can_decrypt(self) -> bool:
        return bool(_ffi.crypto_can_decrypt(self._capsule))

    def decrypt_data(
        self,
        data: bytes | bytearray | memoryview,
        encryption: int,
        entry_name: str,
        entry_length: int,
        hash_lut: bytes | bytearray | memoryview,
    ) -> bytes:
        return bytes(_ffi.crypto_decrypt_data(
            self._capsule, bytes(data), int(encryption),
            str(entry_name), int(entry_length), bytes(hash_lut),
        ))


def scan_rpf_into_index(
    index: CompactIndex,
    path: str,
    source_prefix: str,
    hash_lut: bytes | bytearray | memoryview,
    crypto: NativeCryptoContext | None = None,
    skip_mask: int = 0,
    verbose: bool = False,
) -> int:
    crypto_capsule: Any = None if crypto is None else crypto._capsule
    return int(
        _ffi.scan_rpf_into_index(
            index._capsule,
            str(path),
            str(source_prefix),
            bytes(hash_lut),
            crypto_capsule,
            int(skip_mask),
            bool(verbose),
        )
    )


__all__ = [
    "CompactIndex",
    "NativeCryptoContext",
    "scan_rpf_into_index",
]
