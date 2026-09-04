#include "indexing/bindings.h"

#include "indexing/texture_index.h"

using namespace fivefury_native;

namespace fivefury_py {

void texture_index_capsule_destructor(PyObject* capsule) {
    void* raw = PyCapsule_GetPointer(capsule, TEXTURE_INDEX_CAPSULE_NAME);
    if (raw == nullptr) {
        PyErr_Clear();
        return;
    }
    delete static_cast<TextureIndex*>(raw);
}

TextureIndex* require_texture_index(PyObject* object) {
    return static_cast<TextureIndex*>(
        PyCapsule_GetPointer(object, TEXTURE_INDEX_CAPSULE_NAME)
    );
}

PyObject* mod_texture_index_new(PyObject*, PyObject*) {
    try {
        return PyCapsule_New(
            new TextureIndex(),
            TEXTURE_INDEX_CAPSULE_NAME,
            texture_index_capsule_destructor
        );
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_texture_index_clear(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    if (!PyArg_ParseTuple(args, "O:texture_index_clear", &capsule)) {
        return nullptr;
    }
    auto* index = require_texture_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    index->clear();
    Py_RETURN_NONE;
}

PyObject* mod_texture_index_count(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    if (!PyArg_ParseTuple(args, "O:texture_index_count", &capsule)) {
        return nullptr;
    }
    auto* index = require_texture_index(capsule);
    return index == nullptr ? nullptr : PyLong_FromSize_t(index->count());
}

PyObject* mod_texture_index_add(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int texture_hash = 0;
    unsigned int dictionary_id = 0;
    if (!PyArg_ParseTuple(
            args,
            "OII:texture_index_add",
            &capsule,
            &texture_hash,
            &dictionary_id
        )) {
        return nullptr;
    }
    auto* index = require_texture_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    try {
        return PyLong_FromUnsignedLong(index->add(texture_hash, dictionary_id));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_texture_index_add_many(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    PyObject* hashes_object = nullptr;
    unsigned int dictionary_id = 0;
    if (!PyArg_ParseTuple(
            args,
            "OOI:texture_index_add_many",
            &capsule,
            &hashes_object,
            &dictionary_id
        )) {
        return nullptr;
    }
    auto* index = require_texture_index(capsule);
    if (index == nullptr) {
        return nullptr;
    }
    PyObject* sequence = PySequence_Fast(hashes_object, "texture_hashes must be a sequence");
    if (sequence == nullptr) {
        return nullptr;
    }
    const auto count = PySequence_Size(sequence);
    std::vector<std::uint32_t> hashes;
    hashes.reserve(static_cast<std::size_t>(count));
    for (Py_ssize_t item_index = 0; item_index < count; ++item_index) {
        PyObject* item = PySequence_GetItem(sequence, item_index);
        if (item == nullptr) {
            Py_DECREF(sequence);
            return nullptr;
        }
        const auto value = PyLong_AsUnsignedLong(item);
        Py_DECREF(item);
        if (PyErr_Occurred() != nullptr || value > 0xFFFFFFFFUL) {
            Py_DECREF(sequence);
            if (PyErr_Occurred() == nullptr) {
                PyErr_SetString(PyExc_OverflowError, "texture hash must fit in uint32");
            }
            return nullptr;
        }
        hashes.push_back(static_cast<std::uint32_t>(value));
    }
    Py_DECREF(sequence);
    try {
        return PyLong_FromUnsignedLong(index->add_many(hashes, dictionary_id));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_texture_index_find_texture(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int texture_hash = 0;
    if (!PyArg_ParseTuple(args, "OI:texture_index_find_texture", &capsule, &texture_hash)) {
        return nullptr;
    }
    auto* index = require_texture_index(capsule);
    return index == nullptr ? nullptr : make_id_list(index->find_texture(texture_hash));
}

PyObject* mod_texture_index_find_dictionary(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    unsigned int dictionary_id = 0;
    if (!PyArg_ParseTuple(args, "OI:texture_index_find_dictionary", &capsule, &dictionary_id)) {
        return nullptr;
    }
    auto* index = require_texture_index(capsule);
    return index == nullptr ? nullptr : make_id_list(index->find_dictionary(dictionary_id));
}

}  // namespace fivefury_py
