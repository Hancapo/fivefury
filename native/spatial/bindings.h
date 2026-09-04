#pragma once

#include "python/bridge.h"

namespace fivefury_py {

PyObject* mod_bounds_decode_polygons(PyObject*, PyObject* args);
PyObject* mod_bounds_decode_bvh_records(PyObject*, PyObject* args);
PyObject* mod_ynv_decode_edge_list(PyObject*, PyObject* args);

}  // namespace fivefury_py
