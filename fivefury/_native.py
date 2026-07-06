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
        return _ffi.index_count(self._capsule)

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
        return _ffi.index_find_path_id(self._capsule, str(path))

    def find_hash_ids(self, hash_value: int) -> list[int]:
        return _ffi.index_find_hash_ids(self._capsule, int(hash_value))

    def find_kind_ids(self, kind_value: int) -> list[int]:
        return _ffi.index_find_kind_ids(self._capsule, int(kind_value))

    def kind_short_hash_map(self, kind_value: int) -> dict[int, int]:
        return _ffi.index_kind_short_hash_map(self._capsule, int(kind_value))

    def kind_counts(self) -> dict[int, int]:
        return _ffi.index_kind_counts(self._capsule)

    def get_path(self, asset_id: int) -> str:
        return _ffi.index_get_path(self._capsule, int(asset_id))

    def get_kind(self, asset_id: int) -> int:
        return _ffi.index_get_kind(self._capsule, int(asset_id))

    def get_size(self, asset_id: int) -> int:
        return _ffi.index_get_size(self._capsule, int(asset_id))

    def get_uncompressed_size(self, asset_id: int) -> int:
        return _ffi.index_get_uncompressed_size(self._capsule, int(asset_id))

    def get_flags(self, asset_id: int) -> int:
        return _ffi.index_get_flags(self._capsule, int(asset_id))

    def get_archive_encryption(self, asset_id: int) -> int:
        return _ffi.index_get_archive_encryption(self._capsule, int(asset_id))

    def get_name_hash(self, asset_id: int) -> int:
        return _ffi.index_get_name_hash(self._capsule, int(asset_id))

    def get_short_hash(self, asset_id: int) -> int:
        return _ffi.index_get_short_hash(self._capsule, int(asset_id))

    def export_state(self) -> bytes:
        return _ffi.index_export_state(self._capsule)

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
        return _ffi.crypto_decrypt_archive_table(
            self._capsule, bytes(data), int(encryption),
            str(archive_name), int(archive_length), bytes(hash_lut),
        )

    def decrypt_data(
        self,
        data: bytes | bytearray | memoryview,
        encryption: int,
        entry_name: str,
        entry_length: int,
        hash_lut: bytes | bytearray | memoryview,
    ) -> bytes:
        return _ffi.crypto_decrypt_data(
            self._capsule, bytes(data), int(encryption),
            str(entry_name), int(entry_length), bytes(hash_lut),
        )


def crypto_magic_mask(seed: int, length: int, rounds: int = 4) -> bytes:
    return _ffi.crypto_magic_mask(int(seed), int(length), int(rounds))


def read_rpf_entry(
    path: str | Path,
    entry_path: str | Path,
    hash_lut: bytes | bytearray | memoryview,
    crypto: NativeCryptoContext | None = None,
    *,
    standalone: bool = False,
) -> bytes:
    crypto_capsule: Any = None if crypto is None else crypto._capsule
    return _ffi.read_rpf_entry(
        str(path),
        str(entry_path),
        bytes(hash_lut),
        crypto_capsule,
        1 if standalone else 0,
    )


def read_rpf_entry_variants(
    path: str | Path,
    entry_path: str | Path,
    hash_lut: bytes | bytearray | memoryview,
    crypto: NativeCryptoContext | None = None,
) -> tuple[bytes, bytes]:
    crypto_capsule: Any = None if crypto is None else crypto._capsule
    return _ffi.read_rpf_entry_variants(
        str(path),
        str(entry_path),
        bytes(hash_lut),
        crypto_capsule,
    )


def _bounds_triangle_area(
    vertex0: tuple[float, float, float],
    vertex1: tuple[float, float, float],
    vertex2: tuple[float, float, float],
) -> float:
    return _ffi.bounds_triangle_area(vertex0, vertex1, vertex2)


def _bounds_from_vertices(
    vertices: list[tuple[float, float, float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return _ffi.bounds_from_vertices(vertices)


def _bounds_sphere_radius_from_vertices(
    center: tuple[float, float, float],
    vertices: list[tuple[float, float, float]],
) -> float:
    return _ffi.bounds_sphere_radius_from_vertices(center, vertices)


def _bounds_quantize_vertices(
    vertices: list[tuple[float, float, float]],
    center: tuple[float, float, float],
    quantum: tuple[float, float, float],
) -> bytes:
    return _ffi.bounds_quantize_vertices(vertices, center, quantum)


def _bounds_chunk_triangles(
    triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]],
    *,
    max_vertices_per_child: int,
    max_triangles_per_child: int,
) -> list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]]:
    return _ffi.bounds_chunk_triangles(triangles, int(max_vertices_per_child), int(max_triangles_per_child))


def _bounds_build_octants(
    vertices: list[tuple[float, float, float]],
) -> list[list[int]]:
    return _ffi.bounds_build_octants(vertices)


def _bounds_indexed_triangle_areas(
    vertices: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
) -> list[float]:
    return _ffi.bounds_indexed_triangle_areas(vertices, triangles)


def _bounds_collect_triangles(
    positions: list[tuple[float, float, float]],
    indices: list[int],
    min_area: float = 1e-10,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
    return _ffi.bounds_collect_triangles(positions, indices, float(min_area))


def _ydr_pack_vertex_buffer(
    semantics: list[tuple[int, int]],
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    texcoords: list[list[tuple[float, float]]],
    tangents: list[tuple[float, float, float, float]],
    colours0: list[tuple[float, float, float, float]],
    colours1: list[tuple[float, float, float, float]],
    blend_weights: list[tuple[float, float, float, float]] | None = None,
    blend_indices: list[tuple[int, int, int, int]] | None = None,
) -> bytes:
    return _ffi.ydr_pack_vertex_buffer(
        semantics,
        positions,
        normals,
        texcoords,
        tangents,
        colours0,
        colours1,
        blend_weights,
        blend_indices,
    )


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
    return _ffi.bounds_build_bvh(
        items,
        fallback_minimum,
        fallback_maximum,
        int(item_threshold),
        int(max_tree_node_count),
    )


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


def resource_pack_block_sizes(
    block_sizes: list[int],
    version: int,
    *,
    max_page_count: int = 128,
    is_system: bool = True,
) -> int:
    return int(_ffi.resource_pack_block_sizes(
        [int(size) for size in block_sizes],
        int(version),
        int(max_page_count),
        bool(is_system),
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
    "resource_pack_block_sizes",
    "scan_rpf_batch_into_index",
    "scan_rpf_into_index",
]
