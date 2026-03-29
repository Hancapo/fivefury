#include "py_bindings.h"

using namespace fivefury_native;

namespace fivefury_py {

PyObject* mod_index_new(PyObject*, PyObject*) {
    try {
        auto* index = new CompactIndex();
        return PyCapsule_New(index, INDEX_CAPSULE_NAME, index_capsule_destructor);
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_clear(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    if (!PyArg_ParseTuple(args, "O:index_clear", &capsule)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        index->clear();
        Py_RETURN_NONE;
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_count(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    if (!PyArg_ParseTuple(args, "O:index_count", &capsule)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return PyLong_FromSize_t(index->count());
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_add(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    PyObject* path_object = nullptr;
    int kind = 0;
    unsigned long long size = 0;
    unsigned long long uncompressed_size = 0;
    unsigned int flags = 0;
    unsigned int archive_encryption = 0;
    unsigned int name_hash = 0;
    unsigned int short_hash = 0;
    if (!PyArg_ParseTuple(
            args,
            "OUiKK|IIII:index_add",
            &capsule,
            &path_object,
            &kind,
            &size,
            &uncompressed_size,
            &flags,
            &archive_encryption,
            &name_hash,
            &short_hash
        )) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    if (flags > 0xFFU) {
        PyErr_SetString(PyExc_ValueError, "flags must fit in uint8");
        return nullptr;
    }
    std::string path;
    if (!unicode_to_utf8(path_object, path, "path")) {
        return nullptr;
    }
    try {
        const auto asset_id = index->add(
            std::move(path),
            static_cast<std::int32_t>(kind),
            static_cast<std::uint64_t>(size),
            static_cast<std::uint64_t>(uncompressed_size),
            static_cast<std::uint8_t>(flags),
            static_cast<std::uint32_t>(archive_encryption),
            static_cast<std::uint32_t>(name_hash),
            static_cast<std::uint32_t>(short_hash)
        );
        return PyLong_FromUnsignedLong(asset_id);
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_find_path_id(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    PyObject* path_object = nullptr;
    if (!PyArg_ParseTuple(args, "OU:index_find_path_id", &capsule, &path_object)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    std::string path;
    if (!unicode_to_utf8(path_object, path, "path")) {
        return nullptr;
    }
    try {
        const auto asset_id = index->find_path_id(path);
        if (!asset_id.has_value()) {
            Py_RETURN_NONE;
        }
        return PyLong_FromUnsignedLong(asset_id.value());
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_find_hash_ids(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int hash_value = 0;
    if (!PyArg_ParseTuple(args, "OI:index_find_hash_ids", &capsule, &hash_value)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return make_id_list(index->find_hash_ids(static_cast<std::uint32_t>(hash_value)));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_find_kind_ids(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    int kind_value = 0;
    if (!PyArg_ParseTuple(args, "Oi:index_find_kind_ids", &capsule, &kind_value)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return make_id_list(index->find_kind_ids(static_cast<std::int32_t>(kind_value)));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_get_path(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int asset_id = 0;
    if (!PyArg_ParseTuple(args, "OI:index_get_path", &capsule, &asset_id)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        const auto path = index->get_path(static_cast<std::uint32_t>(asset_id));
        return PyUnicode_FromStringAndSize(path.data(), static_cast<Py_ssize_t>(path.size()));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_get_kind(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int asset_id = 0;
    if (!PyArg_ParseTuple(args, "OI:index_get_kind", &capsule, &asset_id)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return PyLong_FromLong(index->get_kind(static_cast<std::uint32_t>(asset_id)));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_get_size(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int asset_id = 0;
    if (!PyArg_ParseTuple(args, "OI:index_get_size", &capsule, &asset_id)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return PyLong_FromUnsignedLongLong(index->get_size(static_cast<std::uint32_t>(asset_id)));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_get_uncompressed_size(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int asset_id = 0;
    if (!PyArg_ParseTuple(args, "OI:index_get_uncompressed_size", &capsule, &asset_id)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return PyLong_FromUnsignedLongLong(index->get_uncompressed_size(static_cast<std::uint32_t>(asset_id)));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_get_flags(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int asset_id = 0;
    if (!PyArg_ParseTuple(args, "OI:index_get_flags", &capsule, &asset_id)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return PyLong_FromUnsignedLong(index->get_flags(static_cast<std::uint32_t>(asset_id)));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_get_archive_encryption(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int asset_id = 0;
    if (!PyArg_ParseTuple(args, "OI:index_get_archive_encryption", &capsule, &asset_id)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return PyLong_FromUnsignedLong(index->get_archive_encryption(static_cast<std::uint32_t>(asset_id)));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_get_name_hash(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int asset_id = 0;
    if (!PyArg_ParseTuple(args, "OI:index_get_name_hash", &capsule, &asset_id)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return PyLong_FromUnsignedLong(index->get_name_hash(static_cast<std::uint32_t>(asset_id)));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_get_short_hash(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int asset_id = 0;
    if (!PyArg_ParseTuple(args, "OI:index_get_short_hash", &capsule, &asset_id)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return PyLong_FromUnsignedLong(index->get_short_hash(static_cast<std::uint32_t>(asset_id)));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_export_state(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    if (!PyArg_ParseTuple(args, "O:index_export_state", &capsule)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return serialize_index_state(*index);
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_index_import_state(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    PyObject* payload_object = nullptr;
    if (!PyArg_ParseTuple(args, "OO:index_import_state", &capsule, &payload_object)) {
        return nullptr;
    }
    auto* index = require_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    Py_buffer buffer{};
    if (PyObject_GetBuffer(payload_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    try {
        deserialize_index_state(*index, static_cast<const char*>(buffer.buf), buffer.len);
        PyBuffer_Release(&buffer);
        Py_RETURN_NONE;
    } catch (...) {
        PyBuffer_Release(&buffer);
        return translate_cpp_exception();
    }
}

PyObject* mod_jenk_hash(PyObject*, PyObject* args) {
    const char* value = nullptr;
    Py_ssize_t value_len = 0;
    PyObject* lut_object = nullptr;
    if (!PyArg_ParseTuple(args, "s#O:jenk_hash", &value, &value_len, &lut_object)) {
        return nullptr;
    }
    Py_buffer lut_buffer{};
    if (PyObject_GetBuffer(lut_object, &lut_buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    if (lut_buffer.len < 256) {
        PyBuffer_Release(&lut_buffer);
        PyErr_SetString(PyExc_ValueError, "LUT must be at least 256 bytes");
        return nullptr;
    }
    const auto result = jenk_hash(
        std::string_view(value, static_cast<std::size_t>(value_len)),
        std::string_view(static_cast<const char*>(lut_buffer.buf), 256)
    );
    PyBuffer_Release(&lut_buffer);
    return PyLong_FromUnsignedLong(result);
}

}  // namespace fivefury_py
