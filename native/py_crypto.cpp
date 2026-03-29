#include "py_bindings.h"

#include <string>
#include <vector>

using namespace fivefury_native;

namespace fivefury_py {

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

}  // namespace fivefury_py
