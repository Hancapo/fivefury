#include "resource/bindings.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <limits>
#include <vector>

namespace fivefury_py {

namespace {

constexpr const char* CAPSULE_NAME = "fivefury.BinaryDocument";

enum class ScalarKind : int {
    U8 = 0,
    I8 = 1,
    U16 = 2,
    I16 = 3,
    U32 = 4,
    I32 = 5,
    U64 = 6,
    I64 = 7,
    F32 = 8,
};

struct BinaryDocument {
    Buffer buffer{};
};

std::size_t scalar_size(ScalarKind kind) {
    switch (kind) {
        case ScalarKind::U8:
        case ScalarKind::I8: return 1U;
        case ScalarKind::U16:
        case ScalarKind::I16: return 2U;
        case ScalarKind::U32:
        case ScalarKind::I32:
        case ScalarKind::F32: return 4U;
        case ScalarKind::U64:
        case ScalarKind::I64: return 8U;
    }
    return 0U;
}

std::uint64_t read_unsigned(const std::uint8_t* data, std::size_t size, bool big_endian) {
    std::uint64_t value = 0;
    if (big_endian) {
        for (std::size_t index = 0; index < size; ++index) {
            value = (value << 8U) | data[index];
        }
    } else {
        for (std::size_t index = 0; index < size; ++index) {
            value |= static_cast<std::uint64_t>(data[index]) << (index * 8U);
        }
    }
    return value;
}

std::int64_t sign_extend(std::uint64_t value, std::size_t size) {
    if (size == 8U) {
        return static_cast<std::int64_t>(value);
    }
    const auto bits = size * 8U;
    const auto sign_bit = std::uint64_t{1} << (bits - 1U);
    if ((value & sign_bit) != 0U) {
        value |= std::numeric_limits<std::uint64_t>::max() << bits;
    }
    return static_cast<std::int64_t>(value);
}

BinaryDocument* get_document(PyObject* capsule) {
    return static_cast<BinaryDocument*>(PyCapsule_GetPointer(capsule, CAPSULE_NAME));
}

void destroy_document(PyObject* capsule) {
    auto* document = static_cast<BinaryDocument*>(PyCapsule_GetPointer(capsule, CAPSULE_NAME));
    if (document == nullptr) {
        PyErr_Clear();
        return;
    }
    document->buffer.release();
    delete document;
}

bool checked_range(std::size_t offset, std::size_t length, std::size_t total) {
    return offset <= total && length <= total - offset;
}

}  // namespace

PyObject* mod_binary_document_new(PyObject*, PyObject* args) {
    PyObject* data_object = nullptr;
    if (!PyArg_ParseTuple(args, "O:binary_document_new", &data_object)) {
        return nullptr;
    }
    auto* document = new BinaryDocument{};
    if (PyObject_GetBuffer(data_object, &document->buffer, PyBUF_SIMPLE) < 0) {
        delete document;
        return nullptr;
    }
    PyObject* capsule = PyCapsule_New(document, CAPSULE_NAME, destroy_document);
    if (capsule == nullptr) {
        document->buffer.release();
        delete document;
    }
    return capsule;
}

PyObject* mod_binary_document_size(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    if (!PyArg_ParseTuple(args, "O:binary_document_size", &capsule)) {
        return nullptr;
    }
    auto* document = get_document(capsule);
    if (document == nullptr) {
        return nullptr;
    }
    return PyLong_FromSsize_t(document->buffer.len);
}

PyObject* mod_binary_document_slice(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    Py_ssize_t offset_value = 0;
    Py_ssize_t length_value = 0;
    if (!PyArg_ParseTuple(args, "Onn:binary_document_slice", &capsule, &offset_value, &length_value)) {
        return nullptr;
    }
    auto* document = get_document(capsule);
    if (document == nullptr) {
        return nullptr;
    }
    if (offset_value < 0 || length_value < 0 ||
        !checked_range(
            static_cast<std::size_t>(offset_value),
            static_cast<std::size_t>(length_value),
            static_cast<std::size_t>(document->buffer.len)
        )) {
        PyErr_SetString(PyExc_ValueError, "binary slice is outside the document");
        return nullptr;
    }
    const auto* data = static_cast<const char*>(document->buffer.buf);
    return PyBytes_FromStringAndSize(data + offset_value, length_value);
}

PyObject* mod_binary_document_c_string(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    Py_ssize_t offset_value = 0;
    Py_ssize_t maximum_value = -1;
    if (!PyArg_ParseTuple(args, "Onn:binary_document_c_string", &capsule, &offset_value, &maximum_value)) {
        return nullptr;
    }
    auto* document = get_document(capsule);
    if (document == nullptr) {
        return nullptr;
    }
    if (offset_value < 0 || offset_value > document->buffer.len) {
        PyErr_SetString(PyExc_ValueError, "string offset is outside the document");
        return nullptr;
    }
    const auto available = document->buffer.len - offset_value;
    const auto limit = maximum_value < 0 ? available : std::min(maximum_value, available);
    const auto* start = static_cast<const char*>(document->buffer.buf) + offset_value;
    const auto* end = static_cast<const char*>(std::memchr(start, 0, static_cast<std::size_t>(limit)));
    const auto length = end == nullptr ? limit : static_cast<Py_ssize_t>(end - start);
    return PyBytes_FromStringAndSize(start, length);
}

PyObject* mod_binary_document_read_array(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    Py_ssize_t offset_value = 0;
    Py_ssize_t count_value = 0;
    int kind_value = 0;
    int endian_value = 0;
    Py_ssize_t stride_value = 0;
    int components = 1;
    if (!PyArg_ParseTuple(
            args,
            "Onniini:binary_document_read_array",
            &capsule,
            &offset_value,
            &count_value,
            &kind_value,
            &endian_value,
            &stride_value,
            &components
        )) {
        return nullptr;
    }
    auto* document = get_document(capsule);
    if (document == nullptr) {
        return nullptr;
    }
    if (kind_value < static_cast<int>(ScalarKind::U8) || kind_value > static_cast<int>(ScalarKind::F32)) {
        PyErr_SetString(PyExc_ValueError, "unknown binary scalar type");
        return nullptr;
    }
    if (offset_value < 0 || count_value < 0 || components <= 0 || components > 4) {
        PyErr_SetString(PyExc_ValueError, "array offset, count, and component count are invalid");
        return nullptr;
    }
    const auto kind = static_cast<ScalarKind>(kind_value);
    const auto item_size = scalar_size(kind);
    const auto packed_size = item_size * static_cast<std::size_t>(components);
    const auto stride = stride_value == 0 ? packed_size : static_cast<std::size_t>(stride_value);
    if (stride < packed_size) {
        PyErr_SetString(PyExc_ValueError, "array stride is smaller than one item");
        return nullptr;
    }
    const auto offset = static_cast<std::size_t>(offset_value);
    const auto count = static_cast<std::size_t>(count_value);
    const auto total = static_cast<std::size_t>(document->buffer.len);
    if ((count > 1U && stride > (std::numeric_limits<std::size_t>::max() - packed_size) / (count - 1U)) ||
        count > std::numeric_limits<std::size_t>::max() / static_cast<std::size_t>(components)) {
        PyErr_SetString(PyExc_OverflowError, "binary array dimensions overflow address space");
        return nullptr;
    }
    const auto required = count == 0U ? 0U : ((count - 1U) * stride) + packed_size;
    if (!checked_range(offset, required, total)) {
        PyErr_SetString(PyExc_ValueError, "binary array is truncated");
        return nullptr;
    }

    const auto value_count = count * static_cast<std::size_t>(components);
    std::vector<std::uint64_t> integers;
    std::vector<double> floats;
    if (kind == ScalarKind::F32) {
        floats.resize(value_count);
    } else {
        integers.resize(value_count);
    }
    const auto* data = static_cast<const std::uint8_t*>(document->buffer.buf);
    const bool big_endian = endian_value != 0;
    {
    GilRelease gil_release;
    for (std::size_t row = 0; row < count; ++row) {
        for (int component = 0; component < components; ++component) {
            const auto source = data + offset + (row * stride) + (static_cast<std::size_t>(component) * item_size);
            const auto raw = read_unsigned(source, item_size, big_endian);
            const auto target = (row * static_cast<std::size_t>(components)) + static_cast<std::size_t>(component);
            if (kind == ScalarKind::F32) {
                const auto bits = static_cast<std::uint32_t>(raw);
                float value = 0.0F;
                std::memcpy(&value, &bits, sizeof(value));
                floats[target] = value;
            } else {
                integers[target] = raw;
            }
        }
    }
    }

    const bool signed_kind = kind == ScalarKind::I8 || kind == ScalarKind::I16 ||
        kind == ScalarKind::I32 || kind == ScalarKind::I64;
    PyObject* result = PyList_New(count_value);
    if (result == nullptr) {
        return nullptr;
    }
    for (std::size_t row = 0; row < count; ++row) {
        PyObject* item = components == 1 ? nullptr : PyTuple_New(components);
        if (components != 1 && item == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        for (int component = 0; component < components; ++component) {
            const auto index = (row * static_cast<std::size_t>(components)) + static_cast<std::size_t>(component);
            PyObject* value = nullptr;
            if (kind == ScalarKind::F32) {
                value = PyFloat_FromDouble(floats[index]);
            } else if (signed_kind) {
                value = PyLong_FromLongLong(sign_extend(integers[index], item_size));
            } else {
                value = PyLong_FromUnsignedLongLong(integers[index]);
            }
            if (value == nullptr) {
                Py_XDECREF(item);
                Py_DECREF(result);
                return nullptr;
            }
            if (components == 1) {
                item = value;
            } else {
                PyTuple_SetItem(item, component, value);
            }
        }
        PyList_SetItem(result, static_cast<Py_ssize_t>(row), item);
    }
    return result;
}

}  // namespace fivefury_py
