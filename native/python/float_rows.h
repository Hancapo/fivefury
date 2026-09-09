#pragma once

#include "python/bridge.h"
#include <cstring>

namespace fivefury_py {

// Checked, potentially unaligned float64 rows at the Python buffer boundary.
struct FloatRows {
    Buffer buffer;

    bool acquire(PyObject* object, Py_ssize_t width) {
        if (PyObject_GetBuffer(object, &buffer, PyBUF_FORMAT | PyBUF_ND | PyBUF_STRIDES) < 0)
            return false;
        if (buffer.ndim != 2 || buffer.itemsize != sizeof(double) ||
            !buffer.format || std::strcmp(buffer.format, "d") != 0 ||
            buffer.shape[1] != width || !PyBuffer_IsContiguous(&buffer, 'C')) {
            PyErr_SetString(PyExc_ValueError, "expected contiguous float64 rows with matching component count");
            return false;
        }
        return true;
    }

    double value(Py_ssize_t row, Py_ssize_t column) const {
        double result;
        const auto offset = (row * buffer.shape[1] + column) * sizeof(double);
        std::memcpy(&result, static_cast<const char*>(buffer.buf) + offset, sizeof(result));
        return result;
    }
};

}  // namespace fivefury_py
