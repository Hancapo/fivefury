#define Py_LIMITED_API 0x030B0000
#include <Python.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <exception>
#include <limits>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
#include <thread>
#include <atomic>
#include <vector>

#include "rpf_index.h"
#include "rpf_scan.h"

using namespace fivefury_native;

namespace {

constexpr const char* INDEX_CAPSULE_NAME = "fivefury.CompactIndex";
constexpr const char* CRYPTO_CAPSULE_NAME = "fivefury.NativeCryptoContext";
constexpr std::uint32_t STATE_MAGIC = 0x31464646U;  // FFF1
constexpr std::uint32_t STATE_VERSION = 1U;

struct BufferView {
    const char* data = nullptr;
    std::size_t size = 0;
    std::size_t offset = 0;
};

struct BatchSource {
    std::string path;
    std::string source_prefix;
};

struct BatchScanResult {
    std::string source_prefix;
    std::size_t count = 0;
    std::string error;
};

void append_u32(std::string& out, std::uint32_t value) {
    out.push_back(static_cast<char>(value & 0xFFU));
    out.push_back(static_cast<char>((value >> 8U) & 0xFFU));
    out.push_back(static_cast<char>((value >> 16U) & 0xFFU));
    out.push_back(static_cast<char>((value >> 24U) & 0xFFU));
}

void append_u64(std::string& out, std::uint64_t value) {
    for (int shift = 0; shift < 64; shift += 8) {
        out.push_back(static_cast<char>((value >> shift) & 0xFFU));
    }
}

void append_i32(std::string& out, std::int32_t value) {
    append_u32(out, static_cast<std::uint32_t>(value));
}

std::uint32_t read_u32(BufferView& view) {
    if (view.offset + 4U > view.size) {
        throw std::invalid_argument("native index blob is truncated");
    }
    const auto* data = reinterpret_cast<const unsigned char*>(view.data + view.offset);
    view.offset += 4U;
    return static_cast<std::uint32_t>(data[0]) |
           (static_cast<std::uint32_t>(data[1]) << 8U) |
           (static_cast<std::uint32_t>(data[2]) << 16U) |
           (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t read_u64(BufferView& view) {
    if (view.offset + 8U > view.size) {
        throw std::invalid_argument("native index blob is truncated");
    }
    const auto* data = reinterpret_cast<const unsigned char*>(view.data + view.offset);
    view.offset += 8U;
    std::uint64_t value = 0;
    for (int shift = 0; shift < 64; shift += 8) {
        value |= static_cast<std::uint64_t>(data[shift / 8]) << shift;
    }
    return value;
}

std::string read_string(BufferView& view) {
    const auto length = read_u32(view);
    if (view.offset + length > view.size) {
        throw std::invalid_argument("native index blob is truncated");
    }
    std::string value(view.data + view.offset, view.data + view.offset + length);
    view.offset += length;
    return value;
}

void python_scan_log(void*, const char* message, std::size_t length) {
    const auto safe_length = static_cast<int>(
        std::min<std::size_t>(length, static_cast<std::size_t>(std::numeric_limits<int>::max()))
    );
    PyGILState_STATE gil_state = PyGILState_Ensure();
    PySys_WriteStdout("%.*s\n", safe_length, message);
    PyGILState_Release(gil_state);
}

void python_scan_log_line(const std::string& message) {
    python_scan_log(nullptr, message.data(), message.size());
}

template <typename T>
void append_vector_bytes(std::string& out, const std::vector<T>& values) {
    if (!values.empty()) {
        out.append(reinterpret_cast<const char*>(values.data()), values.size() * sizeof(T));
    }
}

template <typename T>
std::vector<T> read_vector(BufferView& view, std::size_t count) {
    const auto bytes = count * sizeof(T);
    if (view.offset + bytes > view.size) {
        throw std::invalid_argument("native index blob is truncated");
    }
    std::vector<T> values(count);
    if (bytes != 0U) {
        std::memcpy(values.data(), view.data + view.offset, bytes);
    }
    view.offset += bytes;
    return values;
}

void index_capsule_destructor(PyObject* capsule) {
    void* raw = PyCapsule_GetPointer(capsule, INDEX_CAPSULE_NAME);
    if (raw == nullptr) {
        PyErr_Clear();
        return;
    }
    delete static_cast<CompactIndex*>(raw);
}

void crypto_capsule_destructor(PyObject* capsule) {
    void* raw = PyCapsule_GetPointer(capsule, CRYPTO_CAPSULE_NAME);
    if (raw == nullptr) {
        PyErr_Clear();
        return;
    }
    delete static_cast<NativeCryptoContext*>(raw);
}

CompactIndex* require_index(PyObject* object) {
    auto* index = static_cast<CompactIndex*>(PyCapsule_GetPointer(object, INDEX_CAPSULE_NAME));
    return index;
}

NativeCryptoContext* require_crypto(PyObject* object) {
    auto* crypto = static_cast<NativeCryptoContext*>(PyCapsule_GetPointer(object, CRYPTO_CAPSULE_NAME));
    return crypto;
}

bool unicode_to_utf8(PyObject* object, std::string& out, const char* argument_name) {
    if (!PyUnicode_Check(object)) {
        PyErr_Format(PyExc_TypeError, "%s must be str", argument_name);
        return false;
    }
    Py_ssize_t size = 0;
    const char* data = PyUnicode_AsUTF8AndSize(object, &size);
    if (data == nullptr) {
        return false;
    }
    out.assign(data, static_cast<std::size_t>(size));
    return true;
}

PyObject* make_id_list(const std::vector<std::uint32_t>& ids) {
    PyObject* list = PyList_New(static_cast<Py_ssize_t>(ids.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(ids.size()); ++index) {
        PyObject* value = PyLong_FromUnsignedLong(ids[static_cast<std::size_t>(index)]);
        if (value == nullptr) {
            Py_DECREF(list);
            return nullptr;
        }
        if (PyList_SetItem(list, index, value) < 0) {
            Py_DECREF(value);
            Py_DECREF(list);
            return nullptr;
        }
    }
    return list;
}

PyObject* serialize_index_state(const CompactIndex& index) {
    const auto paths = index.export_paths();
    const auto kinds = index.export_kinds();
    const auto sizes = index.export_sizes();
    const auto uncompressed_sizes = index.export_uncompressed_sizes();
    const auto flags = index.export_flags();
    const auto archive_encryptions = index.export_archive_encryptions();
    const auto name_hashes = index.export_name_hashes();
    const auto short_hashes = index.export_short_hashes();

    const auto count = paths.size();
    std::string payload;
    payload.reserve(
        16U +
        (count * sizeof(std::int32_t)) +
        (count * sizeof(std::uint64_t) * 2U) +
        (count * sizeof(std::uint8_t)) +
        (count * sizeof(std::uint32_t) * 3U)
    );

    append_u32(payload, STATE_MAGIC);
    append_u32(payload, STATE_VERSION);
    append_u32(payload, static_cast<std::uint32_t>(count));
    append_u32(payload, 0U);
    for (const auto& path : paths) {
        if (path.size() > std::numeric_limits<std::uint32_t>::max()) {
            throw std::overflow_error("path is too large to serialize");
        }
        append_u32(payload, static_cast<std::uint32_t>(path.size()));
        payload.append(path);
    }
    append_vector_bytes(payload, kinds);
    append_vector_bytes(payload, sizes);
    append_vector_bytes(payload, uncompressed_sizes);
    append_vector_bytes(payload, flags);
    append_vector_bytes(payload, archive_encryptions);
    append_vector_bytes(payload, name_hashes);
    append_vector_bytes(payload, short_hashes);

    return PyBytes_FromStringAndSize(payload.data(), static_cast<Py_ssize_t>(payload.size()));
}

void deserialize_index_state(CompactIndex& index, const char* data, Py_ssize_t size) {
    BufferView view{data, static_cast<std::size_t>(size), 0U};
    const auto magic = read_u32(view);
    const auto version = read_u32(view);
    const auto count = read_u32(view);
    static_cast<void>(read_u32(view));
    if (magic != STATE_MAGIC || version != STATE_VERSION) {
        throw std::invalid_argument("unsupported native index state");
    }

    std::vector<std::string> paths;
    paths.reserve(count);
    for (std::uint32_t i = 0; i < count; ++i) {
        paths.push_back(read_string(view));
    }
    auto kinds = read_vector<std::int32_t>(view, count);
    auto sizes = read_vector<std::uint64_t>(view, count);
    auto uncompressed_sizes = read_vector<std::uint64_t>(view, count);
    auto flags = read_vector<std::uint8_t>(view, count);
    auto archive_encryptions = read_vector<std::uint32_t>(view, count);
    auto name_hashes = read_vector<std::uint32_t>(view, count);
    auto short_hashes = read_vector<std::uint32_t>(view, count);
    if (view.offset != view.size) {
        throw std::invalid_argument("native index blob has trailing data");
    }
    index.import_columns(
        std::move(paths),
        std::move(kinds),
        std::move(sizes),
        std::move(uncompressed_sizes),
        std::move(flags),
        std::move(archive_encryptions),
        std::move(name_hashes),
        std::move(short_hashes)
    );
}

PyObject* translate_cpp_exception() {
    try {
        throw;
    } catch (const std::invalid_argument& exc) {
        PyErr_SetString(PyExc_ValueError, exc.what());
    } catch (const std::out_of_range& exc) {
        PyErr_SetString(PyExc_IndexError, exc.what());
    } catch (const std::overflow_error& exc) {
        PyErr_SetString(PyExc_OverflowError, exc.what());
    } catch (const std::bad_alloc&) {
        PyErr_NoMemory();
    } catch (const std::exception& exc) {
        PyErr_SetString(PyExc_RuntimeError, exc.what());
    } catch (...) {
        PyErr_SetString(PyExc_RuntimeError, "unknown native error");
    }
    return nullptr;
}

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

PyObject* mod_crypto_new(PyObject*, PyObject* args) {
    PyObject* aes_object = nullptr;
    PyObject* ng_object = nullptr;
    if (!PyArg_ParseTuple(args, "OO:crypto_new", &aes_object, &ng_object)) {
        return nullptr;
    }
    Py_buffer aes_buffer{};
    Py_buffer ng_buffer{};
    if (PyObject_GetBuffer(aes_object, &aes_buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    if (PyObject_GetBuffer(ng_object, &ng_buffer, PyBUF_SIMPLE) < 0) {
        PyBuffer_Release(&aes_buffer);
        return nullptr;
    }
    try {
        std::vector<std::uint8_t> aes(
            static_cast<const std::uint8_t*>(aes_buffer.buf),
            static_cast<const std::uint8_t*>(aes_buffer.buf) + aes_buffer.len
        );
        std::vector<std::uint8_t> ng(
            static_cast<const std::uint8_t*>(ng_buffer.buf),
            static_cast<const std::uint8_t*>(ng_buffer.buf) + ng_buffer.len
        );
        auto* crypto = new NativeCryptoContext(std::move(aes), std::move(ng));
        PyBuffer_Release(&ng_buffer);
        PyBuffer_Release(&aes_buffer);
        return PyCapsule_New(crypto, CRYPTO_CAPSULE_NAME, crypto_capsule_destructor);
    } catch (...) {
        PyBuffer_Release(&ng_buffer);
        PyBuffer_Release(&aes_buffer);
        return translate_cpp_exception();
    }
}

PyObject* mod_crypto_can_decrypt(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    if (!PyArg_ParseTuple(args, "O:crypto_can_decrypt", &capsule)) {
        return nullptr;
    }
    auto* crypto = require_crypto(capsule);
    if (crypto == nullptr) {
        return nullptr;
    }
    try {
        if (crypto->can_decrypt()) {
            Py_RETURN_TRUE;
        }
        Py_RETURN_FALSE;
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_crypto_decrypt_data(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    PyObject* data_object = nullptr;
    unsigned int encryption = 0;
    const char* entry_name = nullptr;
    Py_ssize_t entry_name_len = 0;
    unsigned int entry_length = 0;
    PyObject* lut_object = nullptr;
    if (!PyArg_ParseTuple(args, "OOIs#IO:crypto_decrypt_data",
            &capsule, &data_object, &encryption,
            &entry_name, &entry_name_len, &entry_length, &lut_object)) {
        return nullptr;
    }
    auto* crypto = require_crypto(capsule);
    if (crypto == nullptr) {
        return nullptr;
    }
    Py_buffer data_buf{};
    if (PyObject_GetBuffer(data_object, &data_buf, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    Py_buffer lut_buf{};
    if (PyObject_GetBuffer(lut_object, &lut_buf, PyBUF_SIMPLE) < 0) {
        PyBuffer_Release(&data_buf);
        return nullptr;
    }
    try {
        std::vector<std::uint8_t> data(
            static_cast<const std::uint8_t*>(data_buf.buf),
            static_cast<const std::uint8_t*>(data_buf.buf) + data_buf.len
        );
        std::string name(entry_name, static_cast<std::size_t>(entry_name_len));
        std::string lut(static_cast<const char*>(lut_buf.buf),
                        std::min(static_cast<std::size_t>(lut_buf.len), std::size_t{256}));
        PyBuffer_Release(&lut_buf);
        PyBuffer_Release(&data_buf);
        auto result = crypto->decrypt_data(data, encryption, name, entry_length, lut);
        return PyBytes_FromStringAndSize(
            reinterpret_cast<const char*>(result.data()),
            static_cast<Py_ssize_t>(result.size())
        );
    } catch (...) {
        PyBuffer_Release(&lut_buf);
        PyBuffer_Release(&data_buf);
        return translate_cpp_exception();
    }
}

PyObject* mod_scan_rpf_batch_into_index(PyObject*, PyObject* args) {
    PyObject* index_capsule = nullptr;
    PyObject* sources_object = nullptr;
    PyObject* hash_lut_object = nullptr;
    PyObject* crypto_capsule = Py_None;
    unsigned int skip_mask = 0;
    int workers = 0;
    int verbose = 0;
    if (!PyArg_ParseTuple(
            args,
            "OOO|OIip:scan_rpf_batch_into_index",
            &index_capsule,
            &sources_object,
            &hash_lut_object,
            &crypto_capsule,
            &skip_mask,
            &workers,
            &verbose
        )) {
        return nullptr;
    }
    auto* index = require_index(index_capsule);
    if (index == nullptr) {
        return nullptr;
    }
    const NativeCryptoContext* crypto = nullptr;
    if (crypto_capsule != Py_None) {
        crypto = require_crypto(crypto_capsule);
        if (crypto == nullptr) {
            return nullptr;
        }
    }

    const auto source_count = PySequence_Size(sources_object);
    if (source_count < 0) {
        return nullptr;
    }

    std::vector<BatchSource> sources;
    sources.reserve(static_cast<std::size_t>(source_count));
    for (Py_ssize_t index_value = 0; index_value < source_count; ++index_value) {
        PyObject* item = PySequence_GetItem(sources_object, index_value);
        if (item == nullptr) {
            return nullptr;
        }
        const auto item_size = PySequence_Size(item);
        if (item_size != 2) {
            Py_DECREF(item);
            PyErr_SetString(PyExc_ValueError, "each source must be a pair of (path, source_prefix)");
            return nullptr;
        }
        PyObject* path_object = PySequence_GetItem(item, 0);
        PyObject* source_prefix_object = PySequence_GetItem(item, 1);
        Py_DECREF(item);
        if (path_object == nullptr || source_prefix_object == nullptr) {
            Py_XDECREF(path_object);
            Py_XDECREF(source_prefix_object);
            return nullptr;
        }
        BatchSource source;
        const auto ok = unicode_to_utf8(path_object, source.path, "path")
            && unicode_to_utf8(source_prefix_object, source.source_prefix, "source_prefix");
        Py_DECREF(path_object);
        Py_DECREF(source_prefix_object);
        if (!ok) {
            return nullptr;
        }
        sources.push_back(std::move(source));
    }

    Py_buffer hash_lut_buffer{};
    if (PyObject_GetBuffer(hash_lut_object, &hash_lut_buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    if (hash_lut_buffer.len != 256) {
        PyBuffer_Release(&hash_lut_buffer);
        PyErr_SetString(PyExc_ValueError, "hash_lut must contain 256 bytes");
        return nullptr;
    }

    std::vector<BatchScanResult> results(sources.size());
    for (std::size_t index_value = 0; index_value < sources.size(); ++index_value) {
        results[index_value].source_prefix = sources[index_value].source_prefix;
    }

    const auto requested_workers = workers <= 0 ? static_cast<std::size_t>(std::thread::hardware_concurrency()) : static_cast<std::size_t>(workers);
    const auto default_workers = requested_workers == 0 ? std::size_t{1} : requested_workers;
    const auto worker_count = std::max<std::size_t>(1, std::min<std::size_t>(default_workers, sources.size() == 0 ? 1 : sources.size()));
    const auto hash_lut = std::string(
        static_cast<const char*>(hash_lut_buffer.buf),
        static_cast<std::size_t>(hash_lut_buffer.len)
    );
    std::atomic_size_t next_index{0};
    std::string failure;

    const auto worker_fn = [&]() {
        while (true) {
            const auto batch_index = next_index.fetch_add(1);
            if (batch_index >= sources.size()) {
                break;
            }
            const auto& source = sources[batch_index];
            auto& result = results[batch_index];
            if (verbose) {
                python_scan_log_line(
                    "[GameFileCache] scan archive " + source.source_prefix +
                    " [archive " + std::to_string(batch_index + 1) + "/" + std::to_string(sources.size()) + "]"
                );
            }
            try {
                result.count = scan_rpf_into_index(
                    *index,
                    source.path,
                    source.source_prefix,
                    hash_lut,
                    crypto,
                    static_cast<std::uint32_t>(skip_mask),
                    verbose ? python_scan_log : nullptr,
                    nullptr
                );
                if (verbose) {
                    python_scan_log_line(
                        "[GameFileCache] scan archive done " + source.source_prefix +
                        " entries=" + std::to_string(result.count)
                    );
                }
            } catch (const std::exception& exc) {
                result.error = exc.what();
                if (verbose) {
                    python_scan_log_line(
                        "[GameFileCache] scan error " + source.source_prefix + ": " + result.error
                    );
                }
            } catch (...) {
                result.error = "unknown native error";
                if (verbose) {
                    python_scan_log_line(
                        "[GameFileCache] scan error " + source.source_prefix + ": " + result.error
                    );
                }
            }
        }
    };

    PyThreadState* thread_state = PyEval_SaveThread();
    try {
        if (sources.empty()) {
            // no-op
        } else if (worker_count <= 1) {
            worker_fn();
        } else {
            std::vector<std::thread> threads;
            threads.reserve(worker_count - 1);
            for (std::size_t index_value = 1; index_value < worker_count; ++index_value) {
                threads.emplace_back(worker_fn);
            }
            worker_fn();
            for (auto& thread : threads) {
                thread.join();
            }
        }
    } catch (const std::exception& exc) {
        failure = exc.what();
    } catch (...) {
        failure = "unknown native error";
    }
    PyEval_RestoreThread(thread_state);
    PyBuffer_Release(&hash_lut_buffer);
    if (!failure.empty()) {
        PyErr_SetString(PyExc_RuntimeError, failure.c_str());
        return nullptr;
    }

    PyObject* list = PyList_New(static_cast<Py_ssize_t>(results.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index_value = 0; index_value < static_cast<Py_ssize_t>(results.size()); ++index_value) {
        const auto& result = results[static_cast<std::size_t>(index_value)];
        PyObject* tuple = PyTuple_New(3);
        if (tuple == nullptr) {
            Py_DECREF(list);
            return nullptr;
        }
        PyObject* source_prefix = PyUnicode_FromStringAndSize(
            result.source_prefix.data(),
            static_cast<Py_ssize_t>(result.source_prefix.size())
        );
        PyObject* count = PyLong_FromSize_t(result.count);
        PyObject* error = nullptr;
        if (result.error.empty()) {
            Py_INCREF(Py_None);
            error = Py_None;
        } else {
            error = PyUnicode_FromStringAndSize(
                result.error.data(),
                static_cast<Py_ssize_t>(result.error.size())
            );
        }
        if (source_prefix == nullptr || count == nullptr || error == nullptr) {
            Py_XDECREF(source_prefix);
            Py_XDECREF(count);
            Py_XDECREF(error);
            Py_DECREF(tuple);
            Py_DECREF(list);
            return nullptr;
        }
        if (PyTuple_SetItem(tuple, 0, source_prefix) < 0 ||
            PyTuple_SetItem(tuple, 1, count) < 0 ||
            PyTuple_SetItem(tuple, 2, error) < 0 ||
            PyList_SetItem(list, index_value, tuple) < 0) {
            Py_DECREF(tuple);
            Py_DECREF(list);
            return nullptr;
        }
    }
    return list;
}

PyObject* mod_scan_rpf_into_index(PyObject*, PyObject* args) {
    PyObject* index_capsule = nullptr;
    PyObject* path_object = nullptr;
    PyObject* source_prefix_object = nullptr;
    PyObject* hash_lut_object = nullptr;
    PyObject* crypto_capsule = Py_None;
    unsigned int skip_mask = 0;
    int verbose = 0;
    if (!PyArg_ParseTuple(
            args,
            "OUUO|OIp:scan_rpf_into_index",
            &index_capsule,
            &path_object,
            &source_prefix_object,
            &hash_lut_object,
            &crypto_capsule,
            &skip_mask,
            &verbose
        )) {
        return nullptr;
    }
    auto* index = require_index(index_capsule);
    if (index == nullptr) {
        return nullptr;
    }
    const NativeCryptoContext* crypto = nullptr;
    if (crypto_capsule != Py_None) {
        crypto = require_crypto(crypto_capsule);
        if (crypto == nullptr) {
            return nullptr;
        }
    }
    std::string path;
    std::string source_prefix;
    if (!unicode_to_utf8(path_object, path, "path") || !unicode_to_utf8(source_prefix_object, source_prefix, "source_prefix")) {
        return nullptr;
    }
    Py_buffer hash_lut_buffer{};
    if (PyObject_GetBuffer(hash_lut_object, &hash_lut_buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    if (hash_lut_buffer.len != 256) {
        PyBuffer_Release(&hash_lut_buffer);
        PyErr_SetString(PyExc_ValueError, "hash_lut must contain 256 bytes");
        return nullptr;
    }

    std::size_t result = 0;
    std::string failure;
    PyThreadState* thread_state = PyEval_SaveThread();
    try {
        result = scan_rpf_into_index(
            *index,
            path,
            source_prefix,
            std::string(static_cast<const char*>(hash_lut_buffer.buf), static_cast<std::size_t>(hash_lut_buffer.len)),
            crypto,
            static_cast<std::uint32_t>(skip_mask),
            verbose ? python_scan_log : nullptr,
            nullptr
        );
    } catch (const std::exception& exc) {
        failure = exc.what();
    } catch (...) {
        failure = "unknown native error";
    }
    PyEval_RestoreThread(thread_state);
    PyBuffer_Release(&hash_lut_buffer);
    if (!failure.empty()) {
        PyErr_SetString(PyExc_RuntimeError, failure.c_str());
        return nullptr;
    }
    return PyLong_FromSize_t(result);
}

PyMethodDef module_methods[] = {
    {"index_new", mod_index_new, METH_NOARGS, nullptr},
    {"index_clear", mod_index_clear, METH_VARARGS, nullptr},
    {"index_count", mod_index_count, METH_VARARGS, nullptr},
    {"index_add", mod_index_add, METH_VARARGS, nullptr},
    {"index_find_path_id", mod_index_find_path_id, METH_VARARGS, nullptr},
    {"index_find_hash_ids", mod_index_find_hash_ids, METH_VARARGS, nullptr},
    {"index_find_kind_ids", mod_index_find_kind_ids, METH_VARARGS, nullptr},
    {"index_get_path", mod_index_get_path, METH_VARARGS, nullptr},
    {"index_get_kind", mod_index_get_kind, METH_VARARGS, nullptr},
    {"index_get_size", mod_index_get_size, METH_VARARGS, nullptr},
    {"index_get_uncompressed_size", mod_index_get_uncompressed_size, METH_VARARGS, nullptr},
    {"index_get_flags", mod_index_get_flags, METH_VARARGS, nullptr},
    {"index_get_archive_encryption", mod_index_get_archive_encryption, METH_VARARGS, nullptr},
    {"index_get_name_hash", mod_index_get_name_hash, METH_VARARGS, nullptr},
    {"index_get_short_hash", mod_index_get_short_hash, METH_VARARGS, nullptr},
    {"index_export_state", mod_index_export_state, METH_VARARGS, nullptr},
    {"index_import_state", mod_index_import_state, METH_VARARGS, nullptr},
    {"crypto_new", mod_crypto_new, METH_VARARGS, nullptr},
    {"crypto_can_decrypt", mod_crypto_can_decrypt, METH_VARARGS, nullptr},
    {"crypto_decrypt_data", mod_crypto_decrypt_data, METH_VARARGS, nullptr},
    {"jenk_hash", mod_jenk_hash, METH_VARARGS, nullptr},
    {"scan_rpf_batch_into_index", mod_scan_rpf_batch_into_index, METH_VARARGS, nullptr},
    {"scan_rpf_into_index", mod_scan_rpf_into_index, METH_VARARGS, nullptr},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_native_abi3",
    "Native abi3 backend for fivefury",
    -1,
    module_methods,
    nullptr,
    nullptr,
    nullptr,
    nullptr,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_abi3(void) {
    return PyModule_Create(&module_def);
}
