#pragma once

#include "python/bridge.h"
#include <array>
#include <span>
#include <vector>

namespace fivefury_py {

// Fill prepared record/vector slots before exposing a new object to Python.
// Callers own field conversion and validation; descriptors still participate in assignment.
class RecordFactory {
    PyObject* type_;
    PyHandle names_;
    PyHandle allocate_;
    allocfunc allocate_native_ = nullptr;
    struct Setter { PyHandle descriptor; descrsetfunc assign; };
    std::vector<Setter> setters_;
    bool valid_ = false;
public:
    RecordFactory(PyObject* type, PyObject* names)
        : type_(type), names_(PySequence_Tuple(names)),
          allocate_(PyObject_GetAttrString(type, "__new__")) {
        if (!names_ || !allocate_) return;
        if (PyType_Check(type)) {
            auto* cls = reinterpret_cast<PyTypeObject*>(type);
            auto* create = PyType_GetSlot(cls, Py_tp_new);
            if (create == reinterpret_cast<void*>(PyType_GenericNew) || create == PyType_GetSlot(&PyBaseObject_Type, Py_tp_new))
                allocate_native_ = reinterpret_cast<allocfunc>(PyType_GetSlot(cls, Py_tp_alloc));
            if (PyErr_Occurred()) return;
        }
        for (Py_ssize_t i = 0; i < dimensions(); ++i) {
            PyHandle descriptor(PyObject_GetAttr(type, PyTuple_GetItem(names_.get(), i)));
            descrsetfunc setter = nullptr;
            if (descriptor) {
                setter = reinterpret_cast<descrsetfunc>(PyType_GetSlot(Py_TYPE(descriptor.get()), Py_tp_descr_set));
                if (PyErr_Occurred()) return;
            } else if (PyErr_ExceptionMatches(PyExc_AttributeError)) PyErr_Clear();
            else return;
            setters_.push_back({std::move(descriptor), setter});
        }
        valid_ = true;
    }
    explicit operator bool() const { return valid_; }
    Py_ssize_t dimensions() const { return PyTuple_Size(names_.get()); }
    PyObject* create() const {
        if (allocate_native_) return allocate_native_(reinterpret_cast<PyTypeObject*>(type_), 0);
        return PyObject_CallFunctionObjArgs(allocate_.get(), type_, nullptr);
    }
    bool assign(PyObject* object, Py_ssize_t index, PyObject* value) const {
        const auto& setter = setters_[index];
        if (setter.assign) return value && setter.assign(setter.descriptor.get(), object, value) == 0;
        return value && PyObject_GenericSetAttr(object, PyTuple_GetItem(names_.get(), index), value) == 0;
    }
    PyObject* numeric(PyObject* values) const {
        PyHandle components(PySequence_Tuple(values));
        if (!components) return nullptr;
        if (PyTuple_Size(components.get()) != dimensions()) {
            PyErr_SetString(PyExc_ValueError, "Incorrect vector component count"); return nullptr;
        }
        PyHandle object(create());
        if (!object) return nullptr;
        for (Py_ssize_t i = 0; i < dimensions(); ++i) {
            PyHandle value(PyNumber_Float(PyTuple_GetItem(components.get(), i)));
            if (!assign(object.get(), i, value.get())) return nullptr;
        }
        return object.release();
    }
    PyObject* numeric(std::span<const double> values) const {
        if (static_cast<Py_ssize_t>(values.size()) != dimensions()) {
            PyErr_SetString(PyExc_ValueError, "Incorrect vector component count"); return nullptr;
        }
        PyHandle object(create());
        if (!object) return nullptr;
        for (Py_ssize_t i = 0; i < dimensions(); ++i) {
            PyHandle value(PyFloat_FromDouble(values[i]));
            if (!assign(object.get(), i, value.get())) return nullptr;
        }
        return object.release();
    }
    PyObject* scalar(PyObject* value) const {
        PyHandle object(create());
        if (!object) return nullptr;
        for (Py_ssize_t i = 0; i < dimensions(); ++i)
            if (!assign(object.get(), i, value)) return nullptr;
        return object.release();
    }
    template<std::size_t N>
    PyObject* materialize(const std::vector<std::array<double, N>>& rows) const {
        if (dimensions() != N) {
            PyErr_SetString(PyExc_ValueError, "Incorrect vector component count"); return nullptr;
        }
        PyHandle result(PyList_New(static_cast<Py_ssize_t>(rows.size())));
        if (!result) return nullptr;
        for (std::size_t i = 0; i < rows.size(); ++i) {
            PyHandle object(numeric(std::span<const double>(rows[i])));
            if (!object) return nullptr;
            if (!list_take(result.get(), i, object.release())) return nullptr;
        }
        return result.release();
    }
};
}
