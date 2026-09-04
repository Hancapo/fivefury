#pragma once

#include "python/bridge.h"

namespace fivefury_py {

PyObject* mod_read_rpf_entry(PyObject*, PyObject* args);
PyObject* mod_read_rpf_entry_variants(PyObject*, PyObject* args);
PyObject* mod_scan_rpf_batch_into_index(PyObject*, PyObject* args);
PyObject* mod_scan_rpf_into_index(PyObject*, PyObject* args);

}  // namespace fivefury_py
