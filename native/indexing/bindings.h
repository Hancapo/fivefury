#pragma once

#include "python/bridge.h"

namespace fivefury_py {

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
PyObject* mod_meta_extract_ytyp_texture_relationships(PyObject*, PyObject* args);
PyObject* mod_jenk_partial_hash(PyObject*, PyObject* args);
PyObject* mod_jenk_continue_hash(PyObject*, PyObject* args);
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

}  // namespace fivefury_py
