from __future__ import annotations

from pathlib import Path
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

    def kind_short_hash_map(self, kind_value: int) -> dict[int, int]:
        return {int(key): int(value) for key, value in _ffi.index_kind_short_hash_map(self._capsule, int(kind_value)).items()}

    def kind_counts(self) -> dict[int, int]:
        return {int(key): int(value) for key, value in _ffi.index_kind_counts(self._capsule).items()}

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

    def decrypt_archive_table(
        self,
        data: bytes | bytearray | memoryview,
        encryption: int,
        archive_name: str,
        archive_length: int,
        hash_lut: bytes | bytearray | memoryview,
    ) -> bytes:
        return bytes(_ffi.crypto_decrypt_archive_table(
            self._capsule, bytes(data), int(encryption),
            str(archive_name), int(archive_length), bytes(hash_lut),
        ))

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


def crypto_magic_mask(seed: int, length: int, rounds: int = 4) -> bytes:
    return bytes(_ffi.crypto_magic_mask(int(seed), int(length), int(rounds)))


def read_rpf_entry(
    path: str | Path,
    entry_path: str | Path,
    hash_lut: bytes | bytearray | memoryview,
    crypto: NativeCryptoContext | None = None,
    *,
    standalone: bool = False,
) -> bytes:
    crypto_capsule: Any = None if crypto is None else crypto._capsule
    return bytes(
        _ffi.read_rpf_entry(
            str(path),
            str(entry_path),
            bytes(hash_lut),
            crypto_capsule,
            1 if standalone else 0,
        )
    )


def read_rpf_entry_variants(
    path: str | Path,
    entry_path: str | Path,
    hash_lut: bytes | bytearray | memoryview,
    crypto: NativeCryptoContext | None = None,
) -> tuple[bytes, bytes]:
    crypto_capsule: Any = None if crypto is None else crypto._capsule
    stored, standalone = _ffi.read_rpf_entry_variants(
        str(path),
        str(entry_path),
        bytes(hash_lut),
        crypto_capsule,
    )
    return bytes(stored), bytes(standalone)


_HAS_BOUNDS_BACKEND = all(
    hasattr(_ffi, name)
    for name in (
        "bounds_triangle_area",
        "bounds_from_vertices",
        "bounds_sphere_radius_from_vertices",
        "bounds_chunk_triangles",
        "bounds_build_octants",
        "bounds_build_bvh",
    )
)


if _HAS_BOUNDS_BACKEND:
    def _bounds_triangle_area(
        vertex0: tuple[float, float, float],
        vertex1: tuple[float, float, float],
        vertex2: tuple[float, float, float],
    ) -> float:
        return float(_ffi.bounds_triangle_area(vertex0, vertex1, vertex2))


    def _bounds_from_vertices(
        vertices: list[tuple[float, float, float]],
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        minimum, maximum = _ffi.bounds_from_vertices(vertices)
        return tuple(minimum), tuple(maximum)


    def _bounds_sphere_radius_from_vertices(
        center: tuple[float, float, float],
        vertices: list[tuple[float, float, float]],
    ) -> float:
        return float(_ffi.bounds_sphere_radius_from_vertices(center, vertices))


    def _bounds_chunk_triangles(
        triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]],
        *,
        max_vertices_per_child: int,
        max_triangles_per_child: int,
    ) -> list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]]:
        return [
            (
                [tuple(vertex) for vertex in vertices],
                [tuple(indices) for indices in chunk_triangles],
            )
            for vertices, chunk_triangles in _ffi.bounds_chunk_triangles(
                triangles,
                int(max_vertices_per_child),
                int(max_triangles_per_child),
            )
        ]


    def _bounds_build_octants(
        vertices: list[tuple[float, float, float]],
    ) -> list[list[int]]:
        return [list(map(int, item)) for item in _ffi.bounds_build_octants(vertices)]


    def _bounds_build_bvh(
        items: list[tuple[tuple[float, float, float], tuple[float, float, float], int]],
        fallback_minimum: tuple[float, float, float],
        fallback_maximum: tuple[float, float, float],
        *,
        item_threshold: int,
        max_tree_node_count: int,
    ) -> tuple[
        list[int],
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        list[tuple[tuple[float, float, float], tuple[float, float, float], int, int]],
        list[tuple[tuple[float, float, float], tuple[float, float, float], int, int]],
    ]:
        order, overall_minimum, overall_maximum, center, quantum_inverse, quantum, nodes, trees = _ffi.bounds_build_bvh(
            items,
            fallback_minimum,
            fallback_maximum,
            int(item_threshold),
            int(max_tree_node_count),
        )
        return (
            list(map(int, order)),
            tuple(overall_minimum),
            tuple(overall_maximum),
            tuple(center),
            tuple(quantum_inverse),
            tuple(quantum),
            [
                (tuple(minimum), tuple(maximum), int(item_id), int(item_count))
                for minimum, maximum, item_id, item_count in nodes
            ],
            [
                (tuple(minimum), tuple(maximum), int(node_index), int(node_index2))
                for minimum, maximum, node_index, node_index2 in trees
            ],
        )
else:
    _bounds_triangle_area = None
    _bounds_from_vertices = None
    _bounds_sphere_radius_from_vertices = None
    _bounds_chunk_triangles = None
    _bounds_build_octants = None
    _bounds_build_bvh = None


def resource_layout_sections(
    system_data: bytes | bytearray | memoryview,
    system_blocks: list[tuple[int, int, bool]],
    graphics_data: bytes | bytearray | memoryview,
    graphics_blocks: list[tuple[int, int, bool]],
    *,
    version: int,
    max_page_count: int,
    virtual_base: int,
    physical_base: int,
) -> tuple[bytes, bytes, int, int]:
    system, graphics, system_flags, graphics_flags = _ffi.resource_layout_sections(
        bytes(system_data),
        [(int(offset), int(size), bool(relocate)) for offset, size, relocate in system_blocks],
        bytes(graphics_data),
        [(int(offset), int(size), bool(relocate)) for offset, size, relocate in graphics_blocks],
        int(version),
        int(max_page_count),
        int(virtual_base),
        int(physical_base),
    )
    return bytes(system), bytes(graphics), int(system_flags), int(graphics_flags)


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


def scan_rpf_batch_into_index(
    index: CompactIndex,
    sources: list[tuple[str, str]] | tuple[tuple[str, str], ...],
    hash_lut: bytes | bytearray | memoryview,
    crypto: NativeCryptoContext | None = None,
    skip_mask: int = 0,
    workers: int = 0,
    verbose: bool = False,
) -> list[tuple[str, int, str | None]]:
    crypto_capsule: Any = None if crypto is None else crypto._capsule
    normalized = [(str(path), str(source_prefix)) for path, source_prefix in sources]
    raw_results = _ffi.scan_rpf_batch_into_index(
        index._capsule,
        normalized,
        bytes(hash_lut),
        crypto_capsule,
        int(skip_mask),
        int(workers),
        bool(verbose),
    )
    return [
        (
            str(source_prefix),
            int(count),
            None if error is None else str(error),
        )
        for source_prefix, count, error in raw_results
    ]


__all__ = [
    "CompactIndex",
    "crypto_magic_mask",
    "NativeCryptoContext",
    "read_rpf_entry",
    "read_rpf_entry_variants",
    "resource_layout_sections",
    "scan_rpf_batch_into_index",
    "scan_rpf_into_index",
]
