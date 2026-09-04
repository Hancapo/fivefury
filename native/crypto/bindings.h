#pragma once

#include "python/bridge.h"

namespace fivefury_py {

PyObject* mod_crypto_new(PyObject*, PyObject* args);
PyObject* mod_crypto_can_decrypt(PyObject*, PyObject* args);
PyObject* mod_crypto_enable_encryption(PyObject*, PyObject* args);
PyObject* mod_crypto_decrypt_archive_table(PyObject*, PyObject* args);
PyObject* mod_crypto_decrypt_data(PyObject*, PyObject* args);
PyObject* mod_crypto_encrypt_archive_table(PyObject*, PyObject* args);
PyObject* mod_crypto_encrypt_data(PyObject*, PyObject* args);
PyObject* mod_crypto_magic_mask(PyObject*, PyObject* args);

}  // namespace fivefury_py
