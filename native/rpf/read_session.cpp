#include "rpf/bindings.h"
#include "rpf/archive.h"

#include <exception>
#include <memory>

namespace fivefury_py {
namespace {
constexpr const char* READER_CAPSULE = "fivefury.RpfReader";

struct Reader {
    std::string path;
    std::string lut;
    const fivefury_native::NativeCryptoContext* crypto = nullptr;
    PyObject* crypto_owner = nullptr;
    fivefury_native::rpf_internal::ReadCache cache;

    ~Reader() { Py_XDECREF(crypto_owner); }
};

void destroy_reader(PyObject* capsule) {
    auto* reader = static_cast<Reader*>(PyCapsule_GetPointer(capsule, READER_CAPSULE));
    if (reader == nullptr) { PyErr_Clear(); return; }
    delete reader;
}
}

PyObject* mod_rpf_reader_new(PyObject*, PyObject* args) {
    const char* path = nullptr;
    BytesView lut;
    PyObject* crypto_owner = Py_None;
    if (!PyArg_ParseTuple(args, "sO&O:rpf_reader_new", &path, parse_bytes_view, &lut, &crypto_owner)) return nullptr;
    if (lut.size != 256) {
        PyErr_SetString(PyExc_ValueError, "hash LUT must contain 256 bytes");
        return nullptr;
    }
    try {
        auto reader = std::make_unique<Reader>();
        reader->path = path;
        reader->lut.assign(lut.data, static_cast<std::size_t>(lut.size));
        if (crypto_owner != Py_None) {
            reader->crypto = require_crypto(crypto_owner);
            if (reader->crypto == nullptr) return nullptr;
            Py_INCREF(crypto_owner);
            reader->crypto_owner = crypto_owner;
        }
        return owned_capsule(std::move(reader), READER_CAPSULE, destroy_reader);
    } catch (...) { return translate_cpp_exception(); }
}

PyObject* mod_rpf_reader_read(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    const char* entry = nullptr;
    int mode = 0;
    if (!PyArg_ParseTuple(args, "Osi:rpf_reader_read", &capsule, &entry, &mode)) return nullptr;
    auto* reader = static_cast<Reader*>(PyCapsule_GetPointer(capsule, READER_CAPSULE));
    if (reader == nullptr) return nullptr;
    if (mode < 0 || mode > 2) {
        PyErr_SetString(PyExc_ValueError, "unknown RPF read mode");
        return nullptr;
    }
    try {
        std::vector<std::uint8_t> bytes;
        fivefury_native::RpfReadVariants variants;
        {
            GilRelease gil_release;
            if (mode == 2) {
                variants = fivefury_native::read_rpf_entry_variants(
                    reader->path, entry, reader->lut, reader->crypto, &reader->cache);
            } else {
                bytes = fivefury_native::read_rpf_entry(
                    reader->path, entry, reader->lut, reader->crypto,
                    mode == 0 ? fivefury_native::RpfReadMode::Stored : fivefury_native::RpfReadMode::Standalone,
                    &reader->cache);
            }
        }
        if (mode == 2) {
            auto* stored = PyBytes_FromStringAndSize(
                reinterpret_cast<const char*>(variants.stored.data()),
                static_cast<Py_ssize_t>(variants.stored.size()));
            if (stored == nullptr) return nullptr;
            auto* standalone = PyBytes_FromStringAndSize(
                reinterpret_cast<const char*>(variants.standalone.data()),
                static_cast<Py_ssize_t>(variants.standalone.size()));
            if (standalone == nullptr) { Py_DECREF(stored); return nullptr; }
            return Py_BuildValue("(NN)", stored, standalone);
        }
        return PyBytes_FromStringAndSize(reinterpret_cast<const char*>(bytes.data()),
            static_cast<Py_ssize_t>(bytes.size()));
    } catch (...) { return translate_cpp_exception(); }
}

PyObject* mod_rpf_reader_table_count(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    if (!PyArg_ParseTuple(args, "O:rpf_reader_table_count", &capsule)) return nullptr;
    auto* reader = static_cast<Reader*>(PyCapsule_GetPointer(capsule, READER_CAPSULE));
    if (reader == nullptr) return nullptr;
    std::lock_guard<std::mutex> lock(reader->cache.mutex);
    return PyLong_FromSize_t(reader->cache.tables.size());
}
}
