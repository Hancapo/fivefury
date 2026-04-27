#include "py_bindings.h"

namespace fivefury_py {

PyMethodDef module_methods[] = {
    {"index_new", mod_index_new, METH_NOARGS, nullptr},
    {"index_clear", mod_index_clear, METH_VARARGS, nullptr},
    {"index_count", mod_index_count, METH_VARARGS, nullptr},
    {"index_add", mod_index_add, METH_VARARGS, nullptr},
    {"index_find_path_id", mod_index_find_path_id, METH_VARARGS, nullptr},
    {"index_find_hash_ids", mod_index_find_hash_ids, METH_VARARGS, nullptr},
    {"index_find_kind_ids", mod_index_find_kind_ids, METH_VARARGS, nullptr},
    {"index_get_path", mod_index_get_path, METH_VARARGS, nullptr},
    {"index_get_kind", mod_index_get_kind, METH_VARARGS, nullptr},
    {"index_get_size", mod_index_get_size, METH_VARARGS, nullptr},
    {"index_get_uncompressed_size", mod_index_get_uncompressed_size, METH_VARARGS, nullptr},
    {"index_get_flags", mod_index_get_flags, METH_VARARGS, nullptr},
    {"index_get_archive_encryption", mod_index_get_archive_encryption, METH_VARARGS, nullptr},
    {"index_get_name_hash", mod_index_get_name_hash, METH_VARARGS, nullptr},
    {"index_get_short_hash", mod_index_get_short_hash, METH_VARARGS, nullptr},
    {"index_export_state", mod_index_export_state, METH_VARARGS, nullptr},
    {"index_import_state", mod_index_import_state, METH_VARARGS, nullptr},
    {"crypto_new", mod_crypto_new, METH_VARARGS, nullptr},
    {"crypto_can_decrypt", mod_crypto_can_decrypt, METH_VARARGS, nullptr},
    {"crypto_decrypt_archive_table", mod_crypto_decrypt_archive_table, METH_VARARGS, nullptr},
    {"crypto_decrypt_data", mod_crypto_decrypt_data, METH_VARARGS, nullptr},
    {"read_rpf_entry", mod_read_rpf_entry, METH_VARARGS, nullptr},
    {"read_rpf_entry_variants", mod_read_rpf_entry_variants, METH_VARARGS, nullptr},
    {"jenk_partial_hash", mod_jenk_partial_hash, METH_VARARGS, nullptr},
    {"jenk_finalize_hash", mod_jenk_finalize_hash, METH_VARARGS, nullptr},
    {"jenk_hash", mod_jenk_hash, METH_VARARGS, nullptr},
    {"scan_rpf_batch_into_index", mod_scan_rpf_batch_into_index, METH_VARARGS, nullptr},
    {"scan_rpf_into_index", mod_scan_rpf_into_index, METH_VARARGS, nullptr},
    {"bounds_triangle_area", mod_bounds_triangle_area, METH_VARARGS, nullptr},
    {"bounds_from_vertices", mod_bounds_from_vertices, METH_VARARGS, nullptr},
    {"bounds_sphere_radius_from_vertices", mod_bounds_sphere_radius_from_vertices, METH_VARARGS, nullptr},
    {"bounds_chunk_triangles", mod_bounds_chunk_triangles, METH_VARARGS, nullptr},
    {"bounds_build_octants", mod_bounds_build_octants, METH_VARARGS, nullptr},
    {"bounds_build_bvh", mod_bounds_build_bvh, METH_VARARGS, nullptr},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_native_abi3",
    "Native abi3 backend for fivefury",
    -1,
    module_methods,
    nullptr,
    nullptr,
    nullptr,
    nullptr,
};

}  // namespace fivefury_py

PyMODINIT_FUNC PyInit__native_abi3(void) {
    return PyModule_Create(&fivefury_py::module_def);
}
