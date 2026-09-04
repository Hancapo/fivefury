#pragma once

#ifndef PY_SSIZE_T_CLEAN
#define PY_SSIZE_T_CLEAN
#endif
#ifndef Py_LIMITED_API
#define Py_LIMITED_API 0x030B0000
#endif
#include <Python.h>
#include "python/ownership.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace fivefury_native {
class CompactIndex;
class NativeCryptoContext;
class TextureIndex;
}

namespace fivefury_py {

struct BytesView {
    char* data = nullptr;
    Py_ssize_t size = 0;
};

int parse_bytes_view(PyObject* object, void* destination);

inline constexpr const char* INDEX_CAPSULE_NAME = "fivefury.CompactIndex";
inline constexpr const char* CRYPTO_CAPSULE_NAME = "fivefury.NativeCryptoContext";
inline constexpr const char* YED_PROGRAM_CAPSULE_NAME = "fivefury.YedProgram";
inline constexpr const char* TEXTURE_INDEX_CAPSULE_NAME = "fivefury.TextureIndex";

void index_capsule_destructor(PyObject* capsule);
void crypto_capsule_destructor(PyObject* capsule);
void texture_index_capsule_destructor(PyObject* capsule);

fivefury_native::CompactIndex* require_index(PyObject* object);
fivefury_native::NativeCryptoContext* require_crypto(PyObject* object);
fivefury_native::TextureIndex* require_texture_index(PyObject* object);
bool unicode_to_utf8(PyObject* object, std::string& out, const char* argument_name);
PyObject* make_id_list(const std::vector<std::uint32_t>& ids);
PyObject* serialize_index_state(const fivefury_native::CompactIndex& index);
void deserialize_index_state(
    fivefury_native::CompactIndex& index,
    const char* data,
    Py_ssize_t size
);
PyObject* translate_cpp_exception();

template <PyCFunction Function>
PyObject* guarded_call(PyObject* self, PyObject* args) noexcept {
    try {
        return Function(self, args);
    } catch (...) {
        return translate_cpp_exception();
    }
}
void python_scan_log(void*, const char* message, std::size_t length);
void python_scan_log_line(const std::string& message);

}  // namespace fivefury_py
