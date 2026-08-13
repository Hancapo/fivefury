#pragma once

#ifndef PY_SSIZE_T_CLEAN
#define PY_SSIZE_T_CLEAN
#endif
#ifndef Py_LIMITED_API
#define Py_LIMITED_API 0x030B0000
#endif
#include <Python.h>

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "rpf_index.h"
#include "rpf_scan.h"
#include "texture_index.h"

namespace fivefury_py {

inline constexpr const char* INDEX_CAPSULE_NAME = "fivefury.CompactIndex";
inline constexpr const char* CRYPTO_CAPSULE_NAME = "fivefury.NativeCryptoContext";
inline constexpr const char* YED_PROGRAM_CAPSULE_NAME = "fivefury.YedProgram";
inline constexpr const char* TEXTURE_INDEX_CAPSULE_NAME = "fivefury.TextureIndex";

void index_capsule_destructor(PyObject* capsule);
void crypto_capsule_destructor(PyObject* capsule);
void texture_index_capsule_destructor(PyObject* capsule);

fivefury_native::CompactIndex* require_index(PyObject* object);
fivefury_native::NativeCryptoContext* require_crypto(PyObject* object);
fivefury_native::TextureIndex* require_texture_index(PyObject* object);
bool unicode_to_utf8(PyObject* object, std::string& out, const char* argument_name);
PyObject* make_id_list(const std::vector<std::uint32_t>& ids);
PyObject* serialize_index_state(const fivefury_native::CompactIndex& index);
void deserialize_index_state(fivefury_native::CompactIndex& index, const char* data, Py_ssize_t size);
PyObject* translate_cpp_exception();
void python_scan_log(void*, const char* message, std::size_t length);
void python_scan_log_line(const std::string& message);

PyObject* mod_index_new(PyObject*, PyObject*);
PyObject* mod_index_clear(PyObject*, PyObject* args);
PyObject* mod_index_count(PyObject*, PyObject* args);
PyObject* mod_index_add(PyObject*, PyObject* args);
PyObject* mod_index_find_path_id(PyObject*, PyObject* args);
PyObject* mod_index_find_hash_ids(PyObject*, PyObject* args);
PyObject* mod_index_find_hashes_ids(PyObject*, PyObject* args);
PyObject* mod_index_find_kind_ids(PyObject*, PyObject* args);
PyObject* mod_index_find_container_ids(PyObject*, PyObject* args);
PyObject* mod_index_find_stem_prefix_ids(PyObject*, PyObject* args);
PyObject* mod_index_kind_short_hash_map(PyObject*, PyObject* args);
PyObject* mod_index_kind_counts(PyObject*, PyObject* args);
PyObject* mod_index_get_path(PyObject*, PyObject* args);
PyObject* mod_index_export_paths(PyObject*, PyObject* args);
PyObject* mod_index_get_kind(PyObject*, PyObject* args);
PyObject* mod_index_get_size(PyObject*, PyObject* args);
PyObject* mod_index_get_uncompressed_size(PyObject*, PyObject* args);
PyObject* mod_index_get_flags(PyObject*, PyObject* args);
PyObject* mod_index_get_archive_encryption(PyObject*, PyObject* args);
PyObject* mod_index_get_name_hash(PyObject*, PyObject* args);
PyObject* mod_index_get_short_hash(PyObject*, PyObject* args);
PyObject* mod_index_export_state(PyObject*, PyObject* args);
PyObject* mod_index_import_state(PyObject*, PyObject* args);
PyObject* mod_jenk_partial_hash(PyObject*, PyObject* args);
PyObject* mod_jenk_finalize_hash(PyObject*, PyObject* args);
PyObject* mod_jenk_hash(PyObject*, PyObject* args);
PyObject* mod_jenk_hash_many(PyObject*, PyObject* args);
PyObject* mod_texture_index_new(PyObject*, PyObject*);
PyObject* mod_texture_index_clear(PyObject*, PyObject* args);
PyObject* mod_texture_index_count(PyObject*, PyObject* args);
PyObject* mod_texture_index_add(PyObject*, PyObject* args);
PyObject* mod_texture_index_add_many(PyObject*, PyObject* args);
PyObject* mod_texture_index_find_texture(PyObject*, PyObject* args);
PyObject* mod_texture_index_find_dictionary(PyObject*, PyObject* args);

PyObject* mod_crypto_new(PyObject*, PyObject* args);
PyObject* mod_crypto_can_decrypt(PyObject*, PyObject* args);
PyObject* mod_crypto_decrypt_archive_table(PyObject*, PyObject* args);
PyObject* mod_crypto_decrypt_data(PyObject*, PyObject* args);
PyObject* mod_crypto_magic_mask(PyObject*, PyObject* args);

PyObject* mod_read_rpf_entry(PyObject*, PyObject* args);
PyObject* mod_read_rpf_entry_variants(PyObject*, PyObject* args);
PyObject* mod_scan_rpf_batch_into_index(PyObject*, PyObject* args);
PyObject* mod_scan_rpf_into_index(PyObject*, PyObject* args);
PyObject* mod_bounds_triangle_area(PyObject*, PyObject* args);
PyObject* mod_bounds_quantize_vertices(PyObject*, PyObject* args);
PyObject* mod_bounds_from_vertices(PyObject*, PyObject* args);
PyObject* mod_bounds_sphere_radius_from_vertices(PyObject*, PyObject* args);
PyObject* mod_bounds_chunk_triangles(PyObject*, PyObject* args);
PyObject* mod_bounds_build_octants(PyObject*, PyObject* args);
PyObject* mod_bounds_build_bvh(PyObject*, PyObject* args);
PyObject* mod_bounds_indexed_triangle_areas(PyObject*, PyObject* args);
PyObject* mod_bounds_collect_triangles(PyObject*, PyObject* args);
PyObject* mod_ydr_pack_vertex_buffer(PyObject*, PyObject* args);
PyObject* mod_ydr_decode_vertex_buffer(PyObject*, PyObject* args);
PyObject* mod_ydr_split_mesh_indices(PyObject*, PyObject* args);
PyObject* mod_skin_compose_matrices(PyObject*, PyObject* args);
PyObject* mod_skin_pack_palette_into(PyObject*, PyObject* args);
PyObject* mod_skin_vertices_into(PyObject*, PyObject* args);
PyObject* mod_bounds_decode_polygons(PyObject*, PyObject* args);
PyObject* mod_bounds_decode_bvh_records(PyObject*, PyObject* args);
PyObject* mod_ynv_decode_edge_list(PyObject*, PyObject* args);
PyObject* mod_binary_document_new(PyObject*, PyObject* args);
PyObject* mod_binary_document_size(PyObject*, PyObject* args);
PyObject* mod_binary_document_slice(PyObject*, PyObject* args);
PyObject* mod_binary_document_c_string(PyObject*, PyObject* args);
PyObject* mod_binary_document_read_array(PyObject*, PyObject* args);
PyObject* mod_resource_layout_sections(PyObject*, PyObject* args);
PyObject* mod_resource_pack_block_sizes(PyObject*, PyObject* args);
PyObject* mod_awc_build_peak_values(PyObject*, PyObject* args);
PyObject* mod_awc_split_interleaved_pcm16(PyObject*, PyObject* args);
PyObject* mod_awc_interleave_pcm16(PyObject*, PyObject* args);
PyObject* mod_awc_decode_adpcm(PyObject*, PyObject* args);
PyObject* mod_awc_rsxxtea(PyObject*, PyObject* args);
PyObject* mod_awc_parse_pcm_wav(PyObject*, PyObject* args);
PyObject* mod_awc_build_pcm_wav(PyObject*, PyObject* args);
PyObject* mod_awc_extract_multichannel_blocks(PyObject*, PyObject* args);
PyObject* mod_yed_compile(PyObject*, PyObject* args);
PyObject* mod_yed_evaluate(PyObject*, PyObject* args);
PyObject* mod_ycd_decode_frame_channels(PyObject*, PyObject* args);
PyObject* mod_ycd_encode_frame_channels(PyObject*, PyObject* args);
PyObject* mod_ycd_decode_quantized_values(PyObject*, PyObject* args);
PyObject* mod_ycd_decode_linear_values(PyObject*, PyObject* args);
PyObject* mod_vector_interpolate_many(PyObject*, PyObject* args);

extern PyMethodDef module_methods[];
extern PyModuleDef module_def;

}  // namespace fivefury_py

PyMODINIT_FUNC PyInit__native_abi3(void);
