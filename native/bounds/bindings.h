#pragma once

#include "python/bridge.h"

namespace fivefury_py {

PyObject* mod_bounds_triangle_area(PyObject*, PyObject* args);
PyObject* mod_bounds_quantize_vertices(PyObject*, PyObject* args);
PyObject* mod_bounds_from_vertices(PyObject*, PyObject* args);
PyObject* mod_bounds_sphere_radius_from_vertices(PyObject*, PyObject* args);
PyObject* mod_bounds_chunk_triangles(PyObject*, PyObject* args);
PyObject* mod_bounds_build_octants(PyObject*, PyObject* args);
PyObject* mod_bounds_build_bvh(PyObject*, PyObject* args);
PyObject* mod_bounds_indexed_triangle_areas(PyObject*, PyObject* args);
PyObject* mod_bounds_collect_triangles(PyObject*, PyObject* args);

}  // namespace fivefury_py
