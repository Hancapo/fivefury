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

    def record(
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

    def find_hashes_ids(
        self, hash_values: list[int], kind_value: int | None = None
    ) -> dict[int, list[int]]:
        return _ffi.index_find_hashes_ids(
            self._capsule,
            [int(value) & 0xFFFFFFFF for value in hash_values],
            kind_value,
        )

    def find_kind_ids(self, kind_value: int) -> list[int]:
        return _ffi.index_find_kind_ids(self._capsule, int(kind_value))

    def find_container_ids(
        self,
        container: str,
        *,
        include_prefixed: bool = False,
        kind_value: int | None = None,
    ) -> list[int]:
        return _ffi.index_find_container_ids(
            self._capsule,
            str(container),
            bool(include_prefixed),
            kind_value,
        )

    def find_stem_prefix_ids(self, prefix: str, kind_value: int) -> list[int]:
        return _ffi.index_find_stem_prefix_ids(
            self._capsule, str(prefix), int(kind_value)
        )

    def kind_short_hash_map(self, kind_value: int) -> dict[int, int]:
        return _ffi.index_kind_short_hash_map(self._capsule, int(kind_value))

    def kind_counts(self) -> dict[int, int]:
        return _ffi.index_kind_counts(self._capsule)

    def get_path(self, asset_id: int) -> str:
        return _ffi.index_get_path(self._capsule, int(asset_id))

    def paths(self) -> list[str]:
        return _ffi.index_export_paths(self._capsule)

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


class NativeTextureIndex:
    __slots__ = ("_capsule",)

    def __init__(self) -> None:
        self._capsule = _ffi.texture_index_new()

    def __len__(self) -> int:
        return int(_ffi.texture_index_count(self._capsule))

    def clear(self) -> None:
        _ffi.texture_index_clear(self._capsule)

    def bind(self, texture_hash: int, dictionary_id: int) -> int:
        return int(
            _ffi.texture_index_add(
                self._capsule,
                int(texture_hash) & 0xFFFFFFFF,
                int(dictionary_id) & 0xFFFFFFFF,
            )
        )

    def bind_many(self, texture_hashes: list[int], dictionary_id: int) -> int:
        return int(
            _ffi.texture_index_add_many(
                self._capsule,
                [int(value) & 0xFFFFFFFF for value in texture_hashes],
                int(dictionary_id) & 0xFFFFFFFF,
            )
        )

    def find_texture(self, texture_hash: int) -> list[int]:
        return _ffi.texture_index_find_texture(
            self._capsule,
            int(texture_hash) & 0xFFFFFFFF,
        )

    def find_dictionary(self, dictionary_id: int) -> list[int]:
        return _ffi.texture_index_find_dictionary(
            self._capsule,
            int(dictionary_id) & 0xFFFFFFFF,
        )


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


class NativeYedProgram:
    __slots__ = ("_capsule",)

    def __init__(self, expressions: tuple[object, ...], defaults: tuple[object, ...]) -> None:
        self._capsule = _ffi.yed_compile(expressions, defaults)

    def evaluate(
        self,
        tracks: object,
        variables: object,
        time: float,
        delta_time: float,
    ) -> tuple[dict, dict, dict, list]:
        return _ffi.yed_evaluate(
            self._capsule,
            tracks,
            variables,
            float(time),
            float(delta_time),
        )


def _ycd_decode_frame_channels(
    data: bytes,
    num_frames: int,
    frame_offset: int,
    frame_length: int,
    descriptors: list[tuple[int, int, int, float, float]],
) -> list[list[float] | list[int]]:
    return _ffi.ycd_decode_frame_channels(
        data,
        int(num_frames),
        int(frame_offset),
        int(frame_length),
        descriptors,
    )


def _ycd_encode_frame_channels(
    num_frames: int,
    descriptors: list[tuple[int, int, list[float] | list[int]]],
) -> tuple[bytes, int]:
    data, frame_length = _ffi.ycd_encode_frame_channels(
        int(num_frames), descriptors
    )
    return bytes(data), int(frame_length)


def _ycd_decode_quantized_values(
    data: bytes,
    bit_offset: int,
    count: int,
    bit_count: int,
    quantum: float,
    offset: float,
) -> tuple[list[float], list[int]]:
    return _ffi.ycd_decode_quantized_values(
        data,
        int(bit_offset),
        int(count),
        int(bit_count),
        float(quantum),
        float(offset),
    )


def _ycd_decode_linear_values(
    data: bytes,
    bit_offset: int,
    num_frames: int,
    chunk_size: int,
    counts: int,
    quantum: float,
    offset: float,
) -> tuple[list[float], list[int]]:
    return _ffi.ycd_decode_linear_values(
        data,
        int(bit_offset),
        int(num_frames),
        int(chunk_size),
        int(counts),
        float(quantum),
        float(offset),
    )


def crypto_magic_mask(seed: int, length: int, rounds: int = 4) -> bytes:
    return _ffi.crypto_magic_mask(int(seed), int(length), int(rounds))


def _awc_build_peak_values(data: bytes, sample_count: int, block_size: int) -> list[int]:
    return _ffi.awc_build_peak_values(data, int(sample_count), int(block_size))


def _awc_split_interleaved_pcm16(data: bytes, channels: int) -> list[bytes]:
    return _ffi.awc_split_interleaved_pcm16(data, int(channels))


def _awc_interleave_pcm16(channels: list[bytes], sample_count: int | None) -> bytes:
    if sample_count is None:
        return _ffi.awc_interleave_pcm16(channels)
    return _ffi.awc_interleave_pcm16(channels, int(sample_count))


def _awc_decode_adpcm(data: bytes, sample_count: int) -> bytes:
    return _ffi.awc_decode_adpcm(data, int(sample_count))


def _awc_rsxxtea(data: bytes, key: tuple[int, int, int, int], *, decrypt: bool) -> bytes:
    return _ffi.awc_rsxxtea(data, key, bool(decrypt))


def _awc_parse_pcm_wav(data: bytes) -> tuple[bytes, int, int, int]:
    return _ffi.awc_parse_pcm_wav(data)


def _awc_build_pcm_wav(
    data: bytes, sample_rate: int, channels: int, bits_per_sample: int
) -> bytes:
    return _ffi.awc_build_pcm_wav(
        data, int(sample_rate), int(channels), int(bits_per_sample)
    )


def _awc_extract_multichannel_blocks(
    data: bytes, block_count: int, block_size: int, channel_count: int
) -> list[list[tuple[int, bytes]]]:
    return _ffi.awc_extract_multichannel_blocks(
        data, int(block_count), int(block_size), int(channel_count)
    )


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


def _ydr_decode_vertex_buffer(
    data: bytes,
    vertex_count: int,
    stride: int,
    flags: int,
    types_value: int,
    component_offsets: tuple[int, ...] | None,
) -> dict[str, object]:
    return _ffi.ydr_decode_vertex_buffer(
        data,
        int(vertex_count),
        int(stride),
        int(flags),
        int(types_value),
        component_offsets,
    )


def _ydr_split_mesh_indices(
    indices: list[int],
    vertex_count: int,
    max_vertices: int,
) -> list[tuple[list[int], list[int]]] | None:
    return _ffi.ydr_split_mesh_indices(
        indices,
        int(vertex_count),
        int(max_vertices),
    )


def _skin_compose_matrices(
    local_matrices: memoryview,
    parent_indices: memoryview,
    count: int,
) -> bytearray:
    return _ffi.skin_compose_matrices(local_matrices, parent_indices, int(count))


def _skin_vertices_into(
    positions: object,
    matrices: object,
    blend_indices: object,
    blend_weights: object,
    normals: object | None,
    output_positions: object,
    output_normals: object | None,
    vertex_count: int,
    bone_count: int,
    influence_count: int,
    normalize_weights: bool,
) -> None:
    _ffi.skin_vertices_into(
        positions,
        matrices,
        blend_indices,
        blend_weights,
        normals,
        output_positions,
        output_normals,
        int(vertex_count),
        int(bone_count),
        int(influence_count),
        bool(normalize_weights),
    )


def _skin_pack_palette_into(
    matrices: object,
    output: object,
    bone_count: int,
) -> None:
    _ffi.skin_pack_palette_into(matrices, output, int(bone_count))


def _bounds_decode_polygons(
    data: bytes,
    start: int,
    count: int,
) -> list[tuple[int, bytes, tuple[object, ...]]]:
    return _ffi.bounds_decode_polygons(data, int(start), int(count))


def _bounds_decode_bvh_records(
    data: bytes,
    start: int,
    count: int,
    center: tuple[float, float, float],
    quantum: tuple[float, float, float],
) -> list[tuple[tuple[float, float, float], tuple[float, float, float], int, int]]:
    return _ffi.bounds_decode_bvh_records(data, int(start), int(count), center, quantum)


def _ynv_decode_edge_list(
    data: bytes,
    list_parts_pointer: int,
    list_parts_count: int,
    adjacent_area_ids: list[int],
) -> list[tuple[int, int, int, int, int, int, int, int]]:
    return _ffi.ynv_decode_edge_list(
        data,
        int(list_parts_pointer),
        int(list_parts_count),
        adjacent_area_ids,
    )


def _binary_document_new(data: bytes) -> object:
    return _ffi.binary_document_new(data)


def _binary_document_size(document: object) -> int:
    return int(_ffi.binary_document_size(document))


def _binary_document_slice(document: object, offset: int, length: int) -> bytes:
    return _ffi.binary_document_slice(document, int(offset), int(length))


def _binary_document_c_string(document: object, offset: int, maximum: int) -> bytes:
    return _ffi.binary_document_c_string(document, int(offset), int(maximum))


def _binary_document_read_array(
    document: object,
    offset: int,
    count: int,
    scalar_type: int,
    endian: int,
    stride: int,
    components: int,
) -> list[object]:
    return _ffi.binary_document_read_array(
        document,
        int(offset),
        int(count),
        int(scalar_type),
        int(endian),
        int(stride),
        int(components),
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
    system_blocks: list[tuple[int, int, bool, tuple[int, ...] | None]],
    graphics_data: bytes | bytearray | memoryview,
    graphics_blocks: list[tuple[int, int, bool, tuple[int, ...] | None]],
    *,
    version: int,
    max_page_count: int,
    virtual_base: int,
    physical_base: int,
) -> tuple[bytes, bytes, int, int]:
    system, graphics, system_flags, graphics_flags = _ffi.resource_layout_sections(
        bytes(system_data),
        [
            (
                int(offset),
                int(size),
                bool(relocate),
                None if pointer_offsets is None else tuple(int(value) for value in pointer_offsets),
            )
            for offset, size, relocate, pointer_offsets in system_blocks
        ],
        bytes(graphics_data),
        [
            (
                int(offset),
                int(size),
                bool(relocate),
                None if pointer_offsets is None else tuple(int(value) for value in pointer_offsets),
            )
            for offset, size, relocate, pointer_offsets in graphics_blocks
        ],
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
    "NativeCryptoContext",
    "crypto_magic_mask",
    "read_rpf_entry",
    "read_rpf_entry_variants",
    "resource_layout_sections",
    "resource_pack_block_sizes",
    "scan_rpf_batch_into_index",
    "scan_rpf_into_index",
]
