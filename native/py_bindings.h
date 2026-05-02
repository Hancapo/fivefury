#pragma once

#define Py_LIMITED_API 0x030B0000
#include <Python.h>

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "rpf_index.h"
#include "rpf_scan.h"

namespace fivefury_py {

inline constexpr const char* INDEX_CAPSULE_NAME = "fivefury.CompactIndex";
inline constexpr const char* CRYPTO_CAPSULE_NAME = "fivefury.NativeCryptoContext";

void index_capsule_destructor(PyObject* capsule);
void crypto_capsule_destructor(PyObject* capsule);

fivefury_native::CompactIndex* require_index(PyObject* object);
fivefury_native::NativeCryptoContext* require_crypto(PyObject* object);
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
PyObject* mod_index_find_kind_ids(PyObject*, PyObject* args);
PyObject* mod_index_get_path(PyObject*, PyObject* args);
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
PyObject* mod_bounds_from_vertices(PyObject*, PyObject* args);
PyObject* mod_bounds_sphere_radius_from_vertices(PyObject*, PyObject* args);
PyObject* mod_bounds_chunk_triangles(PyObject*, PyObject* args);
PyObject* mod_bounds_build_octants(PyObject*, PyObject* args);
PyObject* mod_bounds_build_bvh(PyObject*, PyObject* args);
PyObject* mod_resource_layout_sections(PyObject*, PyObject* args);

extern PyMethodDef module_methods[];
extern PyModuleDef module_def;

}  // namespace fivefury_py

PyMODINIT_FUNC PyInit__native_abi3(void);
