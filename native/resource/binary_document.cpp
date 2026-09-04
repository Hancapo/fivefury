#include "resource/bindings.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <limits>
#include <type_traits>

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

}  // namespace

PyObject* mod_binary_document_new(PyObject*, PyObject* args) {
    PyObject* data_object = nullptr;
    if (!PyArg_ParseTuple(args, "O:binary_document_new", &data_object)) {
        return nullptr;
    }
    auto document = std::make_unique<BinaryDocument>();
    if (!document->buffer.acquire(data_object)) return nullptr;
    return owned_capsule(std::move(document), CAPSULE_NAME, destroy_document);
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
        !fivefury_native::binary::contains(
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

namespace {

struct ArrayLayout {
    BinaryDocument* document = nullptr;
    std::size_t offset = 0;
    std::size_t count = 0;
    std::size_t stride = 0;
    ScalarKind kind = ScalarKind::U8;
    bool big_endian = false;
    int components = 1;
};

bool parse_array_layout(PyObject* args, ArrayLayout& layout) {
    PyObject* capsule = nullptr;
    Py_ssize_t offset = 0, count = 0, stride = 0;
    int kind = 0, endian = 0;
    if (!PyArg_ParseTuple(args, "Onniini", &capsule, &offset, &count,
                         &kind, &endian, &stride, &layout.components)) return false;
    layout.document = get_document(capsule);
    if (layout.document == nullptr) return false;
    if (kind < 0 || kind > static_cast<int>(ScalarKind::F32)) {
        PyErr_SetString(PyExc_ValueError, "unknown binary scalar type");
        return false;
    }
    if (offset < 0 || count < 0 || stride < 0 ||
        layout.components < 1 || layout.components > 4 || endian < 0 || endian > 1) {
        PyErr_SetString(PyExc_ValueError, "invalid binary array dimensions or endian");
        return false;
    }
    layout.kind = static_cast<ScalarKind>(kind);
    layout.big_endian = endian != 0;
    layout.offset = static_cast<std::size_t>(offset);
    layout.count = static_cast<std::size_t>(count);
    const auto packed = scalar_size(layout.kind) * static_cast<std::size_t>(layout.components);
    layout.stride = stride == 0 ? packed : static_cast<std::size_t>(stride);
    if (layout.stride < packed) {
        PyErr_SetString(PyExc_ValueError, "array stride is smaller than one item");
        return false;
    }
    const auto total = static_cast<std::size_t>(layout.document->buffer.len);
    if (layout.offset > total || (layout.count != 0 &&
        (packed > total - layout.offset ||
         layout.count - 1 > (total - layout.offset - packed) / layout.stride))) {
        PyErr_SetString(PyExc_ValueError, "binary array is truncated");
        return false;
    }
    return true;
}

template <typename T, std::endian Order>
PyObject* read_rows(const ArrayLayout& layout) {
    PyHandle result(PyList_New(static_cast<Py_ssize_t>(layout.count)));
    if (!result) return nullptr;
    const auto* data = static_cast<const std::uint8_t*>(layout.document->buffer.buf) + layout.offset;
    for (std::size_t row = 0; row < layout.count; ++row) {
        PyHandle tuple(layout.components == 1 ? nullptr : PyTuple_New(layout.components));
        if (layout.components != 1 && !tuple) return nullptr;
        for (int component = 0; component < layout.components; ++component) {
            const T decoded = fivefury_native::binary::load<T, Order>(
                data + row * layout.stride + static_cast<std::size_t>(component) * sizeof(T));
            PyObject* value = nullptr;
            if constexpr (std::is_floating_point_v<T>) {
                value = PyFloat_FromDouble(decoded);
            } else if constexpr (std::is_signed_v<T>) {
                value = PyLong_FromLongLong(decoded);
            } else {
                value = PyLong_FromUnsignedLongLong(decoded);
            }
            if (layout.components == 1) {
                if (!list_take(result.get(), static_cast<Py_ssize_t>(row), value)) return nullptr;
            } else if (!tuple_take(tuple.get(), component, value)) {
                return nullptr;
            }
        }
        if (layout.components != 1 &&
            !list_take(result.get(), static_cast<Py_ssize_t>(row), tuple.release())) return nullptr;
    }
    return result.release();
}

template <std::endian Order>
PyObject* read_typed_rows(const ArrayLayout& layout) {
    switch (layout.kind) {
        case ScalarKind::U8: return read_rows<std::uint8_t, Order>(layout);
        case ScalarKind::I8: return read_rows<std::int8_t, Order>(layout);
        case ScalarKind::U16: return read_rows<std::uint16_t, Order>(layout);
        case ScalarKind::I16: return read_rows<std::int16_t, Order>(layout);
        case ScalarKind::U32: return read_rows<std::uint32_t, Order>(layout);
        case ScalarKind::I32: return read_rows<std::int32_t, Order>(layout);
        case ScalarKind::U64: return read_rows<std::uint64_t, Order>(layout);
        case ScalarKind::I64: return read_rows<std::int64_t, Order>(layout);
        case ScalarKind::F32: return read_rows<float, Order>(layout);
    }
    PyErr_SetString(PyExc_ValueError, "unknown binary scalar type");
    return nullptr;
}

}  // namespace

PyObject* mod_binary_document_read_array(PyObject*, PyObject* args) {
    ArrayLayout layout;
    if (!parse_array_layout(args, layout)) return nullptr;
    return layout.big_endian
        ? read_typed_rows<std::endian::big>(layout)
        : read_typed_rows<std::endian::little>(layout);
}

PyObject* mod_binary_document_array_view(PyObject*, PyObject* args) {
    ArrayLayout layout;
    if (!parse_array_layout(args, layout)) return nullptr;
    const char* formats[] = {"u1", "i1", "u2", "i2", "u4", "i4", "u8", "i8", "f4"};
    const auto format = std::string(layout.big_endian ? ">" : "<") +
        formats[static_cast<int>(layout.kind)];
    PyHandle view(PyMemoryView_FromObject(layout.document->buffer.obj));
    if (!view) return nullptr;
    return Py_BuildValue("(Nsnnni)", view.release(), format.c_str(),
        static_cast<Py_ssize_t>(layout.offset), static_cast<Py_ssize_t>(layout.count),
        static_cast<Py_ssize_t>(layout.stride), layout.components);
}

}  // namespace fivefury_py
