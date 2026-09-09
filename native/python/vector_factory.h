#pragma once

#include "python/bridge.h"
#include <array>
#include <vector>

namespace fivefury_py {

// Fill nominal frozen-vector slots before exposing a new object to Python.
// Both decoded native arrays and Python component rows use this boundary.
class VectorFactory {
    PyObject* type_;
    PyHandle names_;
    PyHandle allocate_;
public:
    VectorFactory(PyObject* type, PyObject* names)
        : type_(type), names_(PySequence_Tuple(names)),
          allocate_(PyObject_GetAttrString(reinterpret_cast<PyObject*>(&PyBaseObject_Type), "__new__")) {}
    explicit operator bool() const { return names_ && allocate_; }
    Py_ssize_t dimensions() const { return PyTuple_Size(names_.get()); }
    PyObject* create() const {
        return PyObject_CallFunctionObjArgs(allocate_.get(), type_, nullptr);
    }
    bool assign(PyObject* object, Py_ssize_t index, PyObject* value) const {
        return value && PyObject_GenericSetAttr(object, PyTuple_GetItem(names_.get(), index), value) == 0;
    }
    template<std::size_t N>
    PyObject* materialize(const std::vector<std::array<double, N>>& rows) const {
        if (dimensions() != N) {
            PyErr_SetString(PyExc_ValueError, "Incorrect vector component count"); return nullptr;
        }
        PyHandle result(PyList_New(static_cast<Py_ssize_t>(rows.size())));
        if (!result) return nullptr;
        for (std::size_t i = 0; i < rows.size(); ++i) {
            PyHandle object(create());
            if (!object) return nullptr;
            for (std::size_t j = 0; j < N; ++j) {
                PyHandle value(PyFloat_FromDouble(rows[i][j]));
                if (!assign(object.get(), j, value.get())) return nullptr;
            }
            if (!list_take(result.get(), i, object.release())) return nullptr;
        }
        return result.release();
    }
};
}
