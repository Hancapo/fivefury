#pragma once

#include "python/bridge.h"

namespace fivefury_py {

PyObject* mod_ydr_pack_vertex_buffer(PyObject*, PyObject* args);
PyObject* mod_ydr_decode_vertex_buffer(PyObject*, PyObject* args);
PyObject* mod_ydr_split_mesh_indices(PyObject*, PyObject* args);
PyObject* mod_skin_compose_matrices(PyObject*, PyObject* args);
PyObject* mod_skin_pack_palette_into(PyObject*, PyObject* args);
PyObject* mod_skin_vertices_into(PyObject*, PyObject* args);
PyObject* mod_vector_interpolate_many(PyObject*, PyObject* args);

}  // namespace fivefury_py
