#include "py_bindings.h"

#include <algorithm>
#include <cstring>
#include <exception>
#include <limits>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>

using namespace fivefury_native;

namespace fivefury_py {

constexpr std::uint32_t STATE_MAGIC = 0x31464646U;  // FFF1
constexpr std::uint32_t STATE_VERSION = 1U;

struct BufferView {
    const char* data = nullptr;
    std::size_t size = 0;
    std::size_t offset = 0;
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

}  // namespace fivefury_py
