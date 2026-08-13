#include "py_bindings.h"

#include "vector_math.h"

#include <vector>

namespace fivefury_py {

namespace {

bool parse_vec4_sequence(PyObject* object, std::vector<fivefury_native::Vec4>& out) {
    PyObject* sequence = PySequence_Fast(object, "vectors must be a sequence");
    if (sequence == nullptr) {
        return false;
    }
    const auto count = PySequence_Size(sequence);
    out.reserve(static_cast<std::size_t>(count));
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        PyObject* components = item == nullptr
            ? nullptr
            : PySequence_Fast(item, "each vector must contain four components");
        Py_XDECREF(item);
        if (components == nullptr || PySequence_Size(components) != 4) {
            Py_XDECREF(components);
            Py_DECREF(sequence);
            if (PyErr_Occurred() == nullptr) {
                PyErr_SetString(PyExc_ValueError, "each vector must contain four components");
            }
            return false;
        }
        fivefury_native::Vec4 value;
        for (Py_ssize_t component = 0; component < 4; ++component) {
            PyObject* number = PySequence_GetItem(components, component);
            value[static_cast<std::size_t>(component)] = PyFloat_AsDouble(number);
            Py_XDECREF(number);
            if (PyErr_Occurred() != nullptr) {
                Py_DECREF(components);
                Py_DECREF(sequence);
                return false;
            }
        }
        Py_DECREF(components);
        out.push_back(value);
    }
    Py_DECREF(sequence);
    return true;
}

PyObject* make_vec4_list(const std::vector<fivefury_native::Vec4>& values) {
    PyObject* result = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (result == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(values.size()); ++index) {
        const auto& value = values[static_cast<std::size_t>(index)];
        PyObject* tuple = PyTuple_New(4);
        if (tuple == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        for (Py_ssize_t component = 0; component < 4; ++component) {
            PyTuple_SetItem(tuple, component, PyFloat_FromDouble(value[static_cast<std::size_t>(component)]));
        }
        PyList_SetItem(result, index, tuple);
    }
    return result;
}

}  // namespace

PyObject* mod_vector_interpolate_many(PyObject*, PyObject* args) {
    PyObject* starts_object = nullptr;
    PyObject* ends_object = nullptr;
    PyObject* rotations_object = nullptr;
    double amount = 0.0;
    if (!PyArg_ParseTuple(
            args,
            "OOdO:vector_interpolate_many",
            &starts_object,
            &ends_object,
            &amount,
            &rotations_object
        )) {
        return nullptr;
    }
    std::vector<fivefury_native::Vec4> starts;
    std::vector<fivefury_native::Vec4> ends;
    if (!parse_vec4_sequence(starts_object, starts) || !parse_vec4_sequence(ends_object, ends)) {
        return nullptr;
    }
    PyObject* rotations = PySequence_Fast(rotations_object, "rotations must be a sequence");
    if (rotations == nullptr) {
        return nullptr;
    }
    const auto count = static_cast<Py_ssize_t>(starts.size());
    if (ends.size() != starts.size() || PySequence_Size(rotations) != count) {
        Py_DECREF(rotations);
        PyErr_SetString(PyExc_ValueError, "starts, ends and rotations must have equal lengths");
        return nullptr;
    }
    std::vector<fivefury_native::Vec4> result;
    result.reserve(starts.size());
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* rotation_object = PySequence_GetItem(rotations, index);
        const auto is_rotation = PyObject_IsTrue(rotation_object);
        Py_XDECREF(rotation_object);
        if (is_rotation < 0) {
            Py_DECREF(rotations);
            return nullptr;
        }
        result.push_back(is_rotation
            ? fivefury_native::quat_nlerp(starts[static_cast<std::size_t>(index)], ends[static_cast<std::size_t>(index)], amount)
            : fivefury_native::vec4_lerp(starts[static_cast<std::size_t>(index)], ends[static_cast<std::size_t>(index)], amount));
    }
    Py_DECREF(rotations);
    return make_vec4_list(result);
}

}  // namespace fivefury_py
