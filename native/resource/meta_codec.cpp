#include "resource/bindings.h"
#include <cmath>
#include <memory>
#include <vector>

namespace fivefury_py {
namespace {
namespace binary = fivefury_native::binary;
constexpr auto capsule_name = "fivefury.MetaScalars";
struct Field {
    PyHandle name, alias;
    int kind;
    Py_ssize_t offset;
};
struct Schema {
    Py_ssize_t size;
    std::vector<Field> fields;
};
std::size_t width(int kind) {
    switch (kind) {
    case 1: case 0x10: case 0x11: case 0x60: return 1;
    case 0x12: case 0x13: case 0x64: return 2;
    case 0x14: case 0x15: case 0x21: case 0x4a:
    case 0x62: case 0x63: case 0x65: return 4;
    case 0x33: return 12;
    case 0x34: return 16;
    default: throw std::invalid_argument("Unsupported META scalar type");
    }
}
void destroy_schema(PyObject* capsule) {
    delete static_cast<Schema*>(PyCapsule_GetPointer(capsule, capsule_name));
}
template<typename T> bool write_integer(char* out, PyObject* value) {
    PyHandle integer(PyNumber_Long(value));
    if (!integer) return false;
    const auto number = PyLong_AsLongLong(integer.get());
    if (PyErr_Occurred()) return false;
    if (number < static_cast<long long>(std::numeric_limits<T>::min()) ||
        number > static_cast<long long>(std::numeric_limits<T>::max())) {
        PyErr_SetString(PyExc_OverflowError, "META integer exceeds field range");
        return false;
    }
    binary::store<T>(out, static_cast<T>(number));
    return true;
}
bool write_float(char* out, PyObject* value) {
    PyHandle converted(PyNumber_Float(value));
    if (!converted) return false;
    const double number = PyFloat_AsDouble(converted.get());
    if (PyErr_Occurred()) return false;
    const auto packed = static_cast<float>(number);
    if (std::isfinite(number) && !std::isfinite(packed)) {
        PyErr_SetString(PyExc_OverflowError, "META float exceeds float32 range");
        return false;
    }
    binary::store<float>(out, packed);
    return true;
}
bool encode(char* out, int kind, PyObject* value, PyObject* hash) {
    if (value == Py_None) return true; // Payload is initialized to zero.
    if (kind != 0x4a && kind != 0x33 && kind != 0x34) {
        const int truth = PyObject_IsTrue(value);
        if (truth < 0) return false;
        if (!truth) return true;
    }
    switch (kind) {
    case 1: {
        int truth = PyObject_IsTrue(value);
        if (truth < 0) return false;
        *out = static_cast<char>(truth); return true;
    }
    case 0x10: return write_integer<std::int8_t>(out, value);
    case 0x11: case 0x60: return write_integer<std::uint8_t>(out, value);
    case 0x12: case 0x64: return write_integer<std::int16_t>(out, value);
    case 0x13: return write_integer<std::uint16_t>(out, value);
    case 0x14: case 0x62: case 0x63: case 0x65: return write_integer<std::int32_t>(out, value);
    case 0x15: return write_integer<std::uint32_t>(out, value);
    case 0x4a: {
        if (!PyUnicode_Check(value)) return write_integer<std::uint32_t>(out, value);
        PyHandle number(PyObject_CallFunctionObjArgs(hash, value, nullptr));
        return number && write_integer<std::uint32_t>(out, number.get());
    }
    case 0x21: return write_float(out, value);
    default: {
        if (PyUnicode_Check(value) || PyBytes_Check(value) || PyByteArray_Check(value)) {
            PyErr_SetString(PyExc_TypeError, "Vector values must be numeric iterables"); return false;
        }
        PyHandle components(PySequence_Tuple(value));
        if (!components) return false;
        const Py_ssize_t count = kind == 0x33 ? 3 : 4;
        if (PyTuple_Size(components.get()) != count) {
            PyErr_SetString(PyExc_ValueError, "Incorrect META vector dimension"); return false;
        }
        for (Py_ssize_t i = 0; i < count; ++i)
            if (!write_float(out + i * 4, PyTuple_GetItem(components.get(), i))) return false;
        return true;
    }
    }
}
PyObject* decode(const char* in, int kind) {
    switch (kind) {
    case 1: return PyBool_FromLong(*in != 0);
    case 0x10: return PyLong_FromLong(binary::load<std::int8_t>(in));
    case 0x11: case 0x60: return PyLong_FromLong(binary::load<std::uint8_t>(in));
    case 0x12: case 0x64: return PyLong_FromLong(binary::load<std::int16_t>(in));
    case 0x13: return PyLong_FromLong(binary::load<std::uint16_t>(in));
    case 0x14: case 0x62: case 0x63: case 0x65: return PyLong_FromLong(binary::load<std::int32_t>(in));
    case 0x15: case 0x4a: return PyLong_FromUnsignedLong(binary::load<std::uint32_t>(in));
    case 0x21: return PyFloat_FromDouble(binary::load<float>(in));
    default: {
        const Py_ssize_t count = kind == 0x33 ? 3 : 4;
        PyHandle result(PyTuple_New(count));
        if (!result) return nullptr;
        for (Py_ssize_t i = 0; i < count; ++i)
            if (!tuple_take(result.get(), i, PyFloat_FromDouble(binary::load<float>(in + i * 4)))) return nullptr;
        return result.release();
    }
    }
}
}

PyObject* mod_meta_scalars_new(PyObject*, PyObject* args) {
    Py_ssize_t size; PyObject* fields;
    if (!PyArg_ParseTuple(args, "nO", &size, &fields)) return nullptr;
    if (size < 0) throw std::invalid_argument("Negative META structure size");
    auto schema = std::make_unique<Schema>(); schema->size = size;
    PyHandle sequence(PySequence_Tuple(fields));
    if (!sequence) return nullptr;
    for (Py_ssize_t i = 0; i < PyTuple_Size(sequence.get()); ++i) {
        PyObject *name, *alias; int kind; Py_ssize_t offset;
        if (!PyArg_ParseTuple(PyTuple_GetItem(sequence.get(), i), "UUni", &name, &alias, &offset, &kind)) return nullptr;
        if (offset < 0 || !binary::contains(offset, width(kind), size))
            throw std::invalid_argument("META field exceeds structure size");
        Py_INCREF(name); Py_INCREF(alias);
        schema->fields.push_back({PyHandle(name), PyHandle(alias), kind, offset});
    }
    return owned_capsule(std::move(schema), capsule_name, destroy_schema);
}
PyObject* mod_meta_scalars_read(PyObject*, PyObject* args) {
    PyObject *capsule, *raw;
    if (!PyArg_ParseTuple(args, "OO", &capsule, &raw)) return nullptr;
    auto* schema = static_cast<Schema*>(PyCapsule_GetPointer(capsule, capsule_name));
    if (!schema) return nullptr;
    Buffer data; if (!data.acquire(raw)) return nullptr;
    if (data.len < schema->size) throw std::invalid_argument("META structure is truncated");
    PyHandle result(PyDict_New()); if (!result) return nullptr;
    for (const auto& field : schema->fields) {
        PyHandle value(decode(static_cast<const char*>(data.buf) + field.offset, field.kind));
        if (!value || PyDict_SetItem(result.get(), field.name.get(), value.get()) < 0) return nullptr;
    }
    return result.release();
}
PyObject* mod_meta_scalars_write(PyObject*, PyObject* args) {
    PyObject *capsule, *values, *hash;
    if (!PyArg_ParseTuple(args, "OOO", &capsule, &values, &hash)) return nullptr;
    auto* schema = static_cast<Schema*>(PyCapsule_GetPointer(capsule, capsule_name));
    if (!schema) return nullptr;
    PyHandle result(PyByteArray_FromStringAndSize(nullptr, schema->size));
    if (!result) return nullptr;
    auto* out = PyByteArray_AsString(result.get());
    std::memset(out, 0, schema->size);
    for (const auto& field : schema->fields) {
        PyHandle value(PyObject_GetItem(values, field.name.get()));
        if (!value) {
            if (!PyErr_ExceptionMatches(PyExc_KeyError)) return nullptr;
            PyErr_Clear();
            PyHandle alias(PyObject_GetItem(values, field.alias.get()));
            if (!alias) {
                if (!PyErr_ExceptionMatches(PyExc_KeyError)) return nullptr;
                PyErr_Clear(); continue;
            }
            if (!encode(out + field.offset, field.kind, alias.get(), hash)) return nullptr;
        } else if (!encode(out + field.offset, field.kind, value.get(), hash)) return nullptr;
    }
    return result.release();
}
} // namespace fivefury_py
