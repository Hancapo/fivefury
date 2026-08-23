#include "py_bindings.h"

#include <cstdint>
#include <limits>
#include <string>
#include <vector>

#include "crypto_magic.h"

using namespace fivefury_native;

namespace fivefury_py {

namespace {

using CryptoTransform = std::vector<std::uint8_t> (NativeCryptoContext::*)(
    const std::vector<std::uint8_t>&,
    std::uint32_t,
    const std::string&,
    std::uint32_t,
    const std::string&
) const;

PyObject* transform_crypto(PyObject* args, const CryptoTransform transform) {
    PyObject* capsule = nullptr;
    PyObject* data_object = nullptr;
    unsigned int encryption = 0;
    PyObject* name_object = nullptr;
    unsigned int length = 0;
    PyObject* lut_object = nullptr;
    if (!PyArg_ParseTuple(args, "OOIOIO:crypto_transform",
            &capsule, &data_object, &encryption, &name_object, &length, &lut_object)) {
        return nullptr;
    }
    std::string name;
    if (!unicode_to_utf8(name_object, name, "name")) {
        return nullptr;
    }
    auto* crypto = require_crypto(capsule);
    if (crypto == nullptr) {
        return nullptr;
    }
    Py_buffer data_buffer{};
    if (PyObject_GetBuffer(data_object, &data_buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    Py_buffer lut_buffer{};
    if (PyObject_GetBuffer(lut_object, &lut_buffer, PyBUF_SIMPLE) < 0) {
        PyBuffer_Release(&data_buffer);
        return nullptr;
    }
    try {
        std::vector<std::uint8_t> data(
            static_cast<const std::uint8_t*>(data_buffer.buf),
            static_cast<const std::uint8_t*>(data_buffer.buf) + data_buffer.len
        );
        std::string lut(
            static_cast<const char*>(lut_buffer.buf),
            std::min(static_cast<std::size_t>(lut_buffer.len), std::size_t{256})
        );
        auto result = (crypto->*transform)(data, encryption, name, length, lut);
        PyBuffer_Release(&lut_buffer);
        PyBuffer_Release(&data_buffer);
        return PyBytes_FromStringAndSize(
            reinterpret_cast<const char*>(result.data()),
            static_cast<Py_ssize_t>(result.size())
        );
    } catch (...) {
        PyBuffer_Release(&lut_buffer);
        PyBuffer_Release(&data_buffer);
        return translate_cpp_exception();
    }
}

}  // namespace

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

PyObject* mod_crypto_enable_encryption(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    PyObject* blob_object = nullptr;
    if (!PyArg_ParseTuple(args, "OO:crypto_enable_encryption", &capsule, &blob_object)) {
        return nullptr;
    }
    auto* crypto = require_crypto(capsule);
    if (crypto == nullptr) {
        return nullptr;
    }
    Py_buffer buffer{};
    if (PyObject_GetBuffer(blob_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    try {
        std::vector<std::uint8_t> blob(
            static_cast<const std::uint8_t*>(buffer.buf),
            static_cast<const std::uint8_t*>(buffer.buf) + buffer.len
        );
        crypto->enable_encryption(std::move(blob));
        PyBuffer_Release(&buffer);
        Py_RETURN_NONE;
    } catch (...) {
        PyBuffer_Release(&buffer);
        return translate_cpp_exception();
    }
}

PyObject* mod_crypto_decrypt_archive_table(PyObject*, PyObject* args) {
    return transform_crypto(args, &NativeCryptoContext::decrypt_archive_table);
}

PyObject* mod_crypto_decrypt_data(PyObject*, PyObject* args) {
    return transform_crypto(args, &NativeCryptoContext::decrypt_data);
}

PyObject* mod_crypto_encrypt_archive_table(PyObject*, PyObject* args) {
    return transform_crypto(args, &NativeCryptoContext::encrypt_archive_table);
}

PyObject* mod_crypto_encrypt_data(PyObject*, PyObject* args) {
    return transform_crypto(args, &NativeCryptoContext::encrypt_data);
}

PyObject* mod_crypto_magic_mask(PyObject*, PyObject* args) {
    int seed = 0;
    unsigned long long length = 0;
    unsigned int rounds = 4;
    if (!PyArg_ParseTuple(args, "iK|I:crypto_magic_mask", &seed, &length, &rounds)) {
        return nullptr;
    }
    if (length > static_cast<unsigned long long>(std::numeric_limits<Py_ssize_t>::max())) {
        PyErr_SetString(PyExc_OverflowError, "mask length is too large");
        return nullptr;
    }
    std::string mask = build_magic_mask(static_cast<std::int32_t>(seed), static_cast<std::size_t>(length), rounds);
    return PyBytes_FromStringAndSize(mask.data(), static_cast<Py_ssize_t>(mask.size()));
}

}  // namespace fivefury_py
