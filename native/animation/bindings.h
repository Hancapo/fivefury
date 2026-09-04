#pragma once

#include "python/bridge.h"

namespace fivefury_py {

PyObject* mod_yed_compile(PyObject*, PyObject* args);
PyObject* mod_yed_evaluate(PyObject*, PyObject* args);
PyObject* mod_ycd_decode_frame_channels(PyObject*, PyObject* args);
PyObject* mod_ycd_encode_frame_channels(PyObject*, PyObject* args);
PyObject* mod_ycd_decode_quantized_values(PyObject*, PyObject* args);
PyObject* mod_ycd_decode_linear_values(PyObject*, PyObject* args);
PyObject* mod_ycd_track_sampler_new(PyObject*, PyObject* args);
PyObject* mod_ycd_track_sampler_window(PyObject*, PyObject* args);
PyObject* mod_ycd_track_sampler_retained_count(PyObject*, PyObject* args);

}  // namespace fivefury_py
