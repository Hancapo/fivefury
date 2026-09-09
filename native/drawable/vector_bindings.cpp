#include "drawable/bindings.h"

#include "math/vector.h"
#include "python/vector_factory.h"

#include <vector>
#include <cstring>

namespace fivefury_py {

PyObject* mod_vector_component_buffer(PyObject*, PyObject* args) {
    PyObject* values;
    int dimensions;
    if (!PyArg_ParseTuple(args, "Oi", &values, &dimensions)) return nullptr;
    if (dimensions < 2 || dimensions > 4) {
        PyErr_SetString(PyExc_ValueError, "Vectors require 2 to 4 components"); return nullptr;
    }
    PyHandle sequence(PySequence_Fast(values, "vectors must be a sequence"));
    if (!sequence) return nullptr;
    const auto count = PySequence_Size(sequence.get());
    if (count < 0) return nullptr;
    PyHandle result(PyBytes_FromStringAndSize(nullptr, checked_buffer_size(count, dimensions * sizeof(double))));
    if (!result) return nullptr;
    char* output = PyBytes_AsString(result.get());
    if (!output) return nullptr;
    const char* names[] = {"x", "y", "z", "w"};
    for (Py_ssize_t row = 0; row < count; ++row) {
        PyHandle value(PySequence_GetItem(sequence.get(), row));
        if (!value) return nullptr;
        for (int column = 0; column < dimensions; ++column) {
            PyHandle component(PyObject_GetAttrString(value.get(), names[column]));
            if (!component) return nullptr;
            const double number = PyFloat_AsDouble(component.get());
            if (PyErr_Occurred()) return nullptr;
            std::memcpy(output + (row * dimensions + column) * sizeof(double), &number, sizeof(number));
        }
    }
    return result.release();
}

PyObject* mod_vector_materialize(PyObject*, PyObject* args) {
    PyObject *rows, *cls, *names;
    if (!PyArg_ParseTuple(args, "OOO", &rows, &cls, &names)) return nullptr;
    PyHandle fields(PySequence_Tuple(names));
    PyHandle sequence(PySequence_Tuple(rows));
    if (!fields || !sequence) return nullptr;
    const auto dimensions = PyTuple_Size(fields.get());
    if (dimensions < 2 || dimensions > 4) {
        PyErr_SetString(PyExc_ValueError, "Vectors require 2 to 4 components"); return nullptr;
    }
    VectorFactory factory(cls, fields.get());
    if (!factory) return nullptr;
    const auto count = PyTuple_Size(sequence.get());
    PyHandle result(PyList_New(count));
    if (!result) return nullptr;
    for (Py_ssize_t i = 0; i < count; ++i) {
        PyHandle components(PySequence_Tuple(PyTuple_GetItem(sequence.get(), i)));
        if (!components) return nullptr;
        if (PyTuple_Size(components.get()) != dimensions) {
            PyErr_SetString(PyExc_ValueError, "Incorrect vector component count"); return nullptr;
        }
        // The Python boundary supplies the nominal vector class. Match its
        // float coercion while filling frozen slots before exposing the object.
        PyHandle object(factory.create());
        if (!object) return nullptr;
        for (Py_ssize_t j = 0; j < dimensions; ++j) {
            PyHandle value(PyNumber_Float(PyTuple_GetItem(components.get(), j)));
            if (!factory.assign(object.get(), j, value.get())) return nullptr;
        }
        if (!list_take(result.get(), i, object.release())) return nullptr;
    }
    return result.release();
}

namespace {

bool parse_vec4_sequence(PyObject* object, std::vector<fivefury_native::Vec4>& out) {
    PyHandle sequence_owner(PySequence_Fast(object, "vectors must be a sequence"));
    PyObject* sequence = sequence_owner.get();
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
                return false;
            }
        }
        Py_DECREF(components);
        out.push_back(value);
    }
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
    PyHandle rotations_owner(PySequence_Fast(rotations_object, "rotations must be a sequence"));
    PyObject* rotations = rotations_owner.get();
    if (rotations == nullptr) {
        return nullptr;
    }
    const auto count = static_cast<Py_ssize_t>(starts.size());
    if (ends.size() != starts.size() || PySequence_Size(rotations) != count) {
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
            return nullptr;
        }
        result.push_back(is_rotation
            ? fivefury_native::quat_nlerp(starts[static_cast<std::size_t>(index)], ends[static_cast<std::size_t>(index)], amount)
            : fivefury_native::vec4_lerp(starts[static_cast<std::size_t>(index)], ends[static_cast<std::size_t>(index)], amount));
    }
    return make_vec4_list(result);
}

}  // namespace fivefury_py
