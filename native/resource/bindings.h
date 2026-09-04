#pragma once

#include "python/bridge.h"

namespace fivefury_py {

PyObject* mod_binary_document_new(PyObject*, PyObject* args);
PyObject* mod_binary_document_size(PyObject*, PyObject* args);
PyObject* mod_binary_document_slice(PyObject*, PyObject* args);
PyObject* mod_binary_document_c_string(PyObject*, PyObject* args);
PyObject* mod_binary_document_read_array(PyObject*, PyObject* args);
PyObject* mod_resource_layout_sections(PyObject*, PyObject* args);
PyObject* mod_resource_pack_block_sizes(PyObject*, PyObject* args);

}  // namespace fivefury_py
