#pragma once

#include "python/bridge.h"

namespace fivefury_py {
bool meta_scalar_write(PyObject*, PyObject*, PyObject*, std::vector<char>&);
bool meta_primitive_write(int, PyObject*, PyObject*, std::vector<char>&);
PyObject* mod_meta_graph_new(PyObject*, PyObject*);
PyObject* mod_meta_graph_write(PyObject*, PyObject*);
PyObject* mod_meta_scalars_new(PyObject*, PyObject*);
PyObject* mod_meta_scalars_read(PyObject*, PyObject*);
PyObject* mod_meta_scalars_write(PyObject*, PyObject*);
PyObject* mod_meta_model_new(PyObject*, PyObject*);
PyObject* mod_meta_model_read(PyObject*, PyObject*);
PyObject* mod_meta_models_read(PyObject*, PyObject*);
PyObject* mod_meta_model_array_read(PyObject*, PyObject*);
PyObject* mod_meta_struct_values(PyObject*, PyObject*);

PyObject* mod_binary_document_new(PyObject*, PyObject* args);
PyObject* mod_binary_document_size(PyObject*, PyObject* args);
PyObject* mod_binary_document_slice(PyObject*, PyObject* args);
PyObject* mod_binary_document_c_string(PyObject*, PyObject* args);
PyObject* mod_binary_document_read_array(PyObject*, PyObject* args);
PyObject* mod_binary_document_array_view(PyObject*, PyObject* args);
PyObject* mod_resource_layout_sections(PyObject*, PyObject* args);
PyObject* mod_resource_pack_block_sizes(PyObject*, PyObject* args);

}  // namespace fivefury_py
