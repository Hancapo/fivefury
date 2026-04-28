#include "py_bindings.h"

#include <cstdint>
#include <string>
#include <vector>

#include "resource_layout.h"

namespace fivefury_py {

namespace {

bool bytes_to_string(PyObject* object, std::string& out, const char* argument_name) {
    if (!PyBytes_Check(object)) {
        PyErr_Format(PyExc_TypeError, "%s must be bytes", argument_name);
        return false;
    }
    char* data = nullptr;
    Py_ssize_t size = 0;
    if (PyBytes_AsStringAndSize(object, &data, &size) < 0) {
        return false;
    }
    out.assign(data, data + size);
    return true;
}

bool parse_resource_blocks(PyObject* object, std::vector<fivefury_native::resource::ResourceBlockSpan>& out) {
    PyObject* sequence = PySequence_Fast(object, "resource blocks must be a sequence");
    if (sequence == nullptr) {
        return false;
    }
    const auto count = PySequence_Size(sequence);
    if (count < 0) {
        Py_DECREF(sequence);
        return false;
    }
    out.clear();
    out.reserve(static_cast<std::size_t>(count));
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        if (item == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        PyObject* block = PySequence_Fast(item, "resource block must contain offset, size and relocate flag");
        Py_DECREF(item);
        if (block == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        const auto block_size = PySequence_Size(block);
        if (block_size != 3) {
            Py_DECREF(block);
            Py_DECREF(sequence);
            PyErr_SetString(PyExc_ValueError, "resource block must contain exactly 3 values");
            return false;
        }
        PyObject* offset_object = PySequence_GetItem(block, 0);
        PyObject* size_object = PySequence_GetItem(block, 1);
        PyObject* relocate_object = PySequence_GetItem(block, 2);
        if (offset_object == nullptr || size_object == nullptr || relocate_object == nullptr) {
            Py_XDECREF(offset_object);
            Py_XDECREF(size_object);
            Py_XDECREF(relocate_object);
            Py_DECREF(block);
            Py_DECREF(sequence);
            return false;
        }
        const auto offset = PyLong_AsUnsignedLongLong(offset_object);
        const auto size = PyLong_AsUnsignedLongLong(size_object);
        const auto relocate = PyObject_IsTrue(relocate_object);
        Py_DECREF(offset_object);
        Py_DECREF(size_object);
        Py_DECREF(relocate_object);
        Py_DECREF(block);
        if (PyErr_Occurred() != nullptr || relocate < 0) {
            Py_DECREF(sequence);
            return false;
        }
        out.push_back(fivefury_native::resource::ResourceBlockSpan{
            static_cast<std::uint64_t>(offset),
            static_cast<std::uint64_t>(size),
            relocate != 0,
        });
    }
    Py_DECREF(sequence);
    return true;
}

PyObject* build_layout_result(const fivefury_native::resource::ResourceLayoutResult& result) {
    PyObject* tuple = PyTuple_New(4);
    PyObject* system_data = PyBytes_FromStringAndSize(result.system_data.data(), static_cast<Py_ssize_t>(result.system_data.size()));
    PyObject* graphics_data = PyBytes_FromStringAndSize(result.graphics_data.data(), static_cast<Py_ssize_t>(result.graphics_data.size()));
    PyObject* system_flags = PyLong_FromUnsignedLong(result.system_flags);
    PyObject* graphics_flags = PyLong_FromUnsignedLong(result.graphics_flags);
    if (tuple == nullptr || system_data == nullptr || graphics_data == nullptr || system_flags == nullptr || graphics_flags == nullptr) {
        Py_XDECREF(tuple);
        Py_XDECREF(system_data);
        Py_XDECREF(graphics_data);
        Py_XDECREF(system_flags);
        Py_XDECREF(graphics_flags);
        return nullptr;
    }
    if (PyTuple_SetItem(tuple, 0, system_data) < 0 ||
        PyTuple_SetItem(tuple, 1, graphics_data) < 0 ||
        PyTuple_SetItem(tuple, 2, system_flags) < 0 ||
        PyTuple_SetItem(tuple, 3, graphics_flags) < 0) {
        Py_DECREF(tuple);
        return nullptr;
    }
    return tuple;
}

}  // namespace

PyObject* mod_resource_layout_sections(PyObject*, PyObject* args) {
    PyObject* system_data_object = nullptr;
    PyObject* system_blocks_object = nullptr;
    PyObject* graphics_data_object = nullptr;
    PyObject* graphics_blocks_object = nullptr;
    unsigned int version = 0;
    unsigned int max_page_count = 128;
    unsigned long long virtual_base = 0x50000000ULL;
    unsigned long long physical_base = 0x60000000ULL;
    if (!PyArg_ParseTuple(
            args,
            "OOOOIIKK:resource_layout_sections",
            &system_data_object,
            &system_blocks_object,
            &graphics_data_object,
            &graphics_blocks_object,
            &version,
            &max_page_count,
            &virtual_base,
            &physical_base
        )) {
        return nullptr;
    }

    std::string system_data;
    std::string graphics_data;
    std::vector<fivefury_native::resource::ResourceBlockSpan> system_blocks;
    std::vector<fivefury_native::resource::ResourceBlockSpan> graphics_blocks;
    if (!bytes_to_string(system_data_object, system_data, "system_data") ||
        !bytes_to_string(graphics_data_object, graphics_data, "graphics_data") ||
        !parse_resource_blocks(system_blocks_object, system_blocks) ||
        !parse_resource_blocks(graphics_blocks_object, graphics_blocks)) {
        return nullptr;
    }

    try {
        return build_layout_result(fivefury_native::resource::layout_resource_sections_impl(
            system_data,
            system_blocks,
            graphics_data,
            graphics_blocks,
            static_cast<std::uint32_t>(version),
            static_cast<std::uint32_t>(max_page_count),
            static_cast<std::uint64_t>(virtual_base),
            static_cast<std::uint64_t>(physical_base)
        ));
    } catch (...) {
        return translate_cpp_exception();
    }
}

}  // namespace fivefury_py
