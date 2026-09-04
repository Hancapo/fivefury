#pragma once

#include "python/bridge.h"

namespace fivefury_py {

PyObject* mod_rpf_reader_new(PyObject*, PyObject* args);
PyObject* mod_rpf_reader_read(PyObject*, PyObject* args);
PyObject* mod_rpf_reader_table_count(PyObject*, PyObject* args);

PyObject* mod_read_rpf_entry(PyObject*, PyObject* args);
PyObject* mod_read_rpf_entry_variants(PyObject*, PyObject* args);
PyObject* mod_scan_rpf_batch_into_index(PyObject*, PyObject* args);
PyObject* mod_scan_rpf_into_index(PyObject*, PyObject* args);

}  // namespace fivefury_py
