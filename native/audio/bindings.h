#pragma once

#include "python/bridge.h"

namespace fivefury_py {

PyObject* mod_awc_build_peak_values(PyObject*, PyObject* args);
PyObject* mod_awc_split_interleaved_pcm16(PyObject*, PyObject* args);
PyObject* mod_awc_interleave_pcm16(PyObject*, PyObject* args);
PyObject* mod_awc_decode_adpcm(PyObject*, PyObject* args);
PyObject* mod_awc_rsxxtea(PyObject*, PyObject* args);
PyObject* mod_awc_parse_pcm_wav(PyObject*, PyObject* args);
PyObject* mod_awc_build_pcm_wav(PyObject*, PyObject* args);
PyObject* mod_awc_extract_multichannel_blocks(PyObject*, PyObject* args);

}  // namespace fivefury_py
