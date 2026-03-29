#include "py_bindings.h"

#include <algorithm>
#include <atomic>
#include <string>
#include <thread>
#include <vector>

using namespace fivefury_native;

namespace fivefury_py {

struct BatchSource {
    std::string path;
    std::string source_prefix;
};

struct BatchScanResult {
    std::string source_prefix;
    std::size_t count = 0;
    std::string error;
};

PyObject* mod_read_rpf_entry(PyObject*, PyObject* args) {
    PyObject* path_object = nullptr;
    PyObject* entry_path_object = nullptr;
    PyObject* lut_object = nullptr;
    PyObject* crypto_capsule = Py_None;
    int mode = 0;
    if (!PyArg_ParseTuple(args, "OOO|Oi:read_rpf_entry", &path_object, &entry_path_object, &lut_object, &crypto_capsule, &mode)) {
        return nullptr;
    }
    std::string path;
    if (!unicode_to_utf8(path_object, path, "path")) {
        return nullptr;
    }
    std::string entry_path;
    if (!unicode_to_utf8(entry_path_object, entry_path, "entry_path")) {
        return nullptr;
    }
    const NativeCryptoContext* crypto = nullptr;
    if (crypto_capsule != Py_None) {
        crypto = require_crypto(crypto_capsule);
        if (crypto == nullptr) {
            return nullptr;
        }
    }
    Py_buffer lut_buf{};
    if (PyObject_GetBuffer(lut_object, &lut_buf, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    if (lut_buf.len < 256) {
        PyBuffer_Release(&lut_buf);
        PyErr_SetString(PyExc_ValueError, "LUT must be at least 256 bytes");
        return nullptr;
    }
    try {
        const auto payload = read_rpf_entry(
            path,
            entry_path,
            std::string(static_cast<const char*>(lut_buf.buf), 256),
            crypto,
            mode == 0 ? RpfReadMode::Stored : RpfReadMode::Standalone
        );
        PyBuffer_Release(&lut_buf);
        return PyBytes_FromStringAndSize(
            reinterpret_cast<const char*>(payload.data()),
            static_cast<Py_ssize_t>(payload.size())
        );
    } catch (const std::exception& exc) {
        PyBuffer_Release(&lut_buf);
        PyErr_SetString(PyExc_RuntimeError, exc.what());
        return nullptr;
    }
}

PyObject* mod_read_rpf_entry_variants(PyObject*, PyObject* args) {
    PyObject* path_object = nullptr;
    PyObject* entry_path_object = nullptr;
    PyObject* lut_object = nullptr;
    PyObject* crypto_capsule = Py_None;
    if (!PyArg_ParseTuple(args, "OOO|O:read_rpf_entry_variants", &path_object, &entry_path_object, &lut_object, &crypto_capsule)) {
        return nullptr;
    }
    std::string path;
    if (!unicode_to_utf8(path_object, path, "path")) {
        return nullptr;
    }
    std::string entry_path;
    if (!unicode_to_utf8(entry_path_object, entry_path, "entry_path")) {
        return nullptr;
    }
    const NativeCryptoContext* crypto = nullptr;
    if (crypto_capsule != Py_None) {
        crypto = require_crypto(crypto_capsule);
        if (crypto == nullptr) {
            return nullptr;
        }
    }
    Py_buffer lut_buf{};
    if (PyObject_GetBuffer(lut_object, &lut_buf, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    if (lut_buf.len < 256) {
        PyBuffer_Release(&lut_buf);
        PyErr_SetString(PyExc_ValueError, "LUT must be at least 256 bytes");
        return nullptr;
    }
    try {
        const auto payload = read_rpf_entry_variants(
            path,
            entry_path,
            std::string(static_cast<const char*>(lut_buf.buf), 256),
            crypto
        );
        PyBuffer_Release(&lut_buf);
        PyObject* tuple = PyTuple_New(2);
        if (tuple == nullptr) {
            return nullptr;
        }
        PyObject* stored = PyBytes_FromStringAndSize(
            reinterpret_cast<const char*>(payload.stored.data()),
            static_cast<Py_ssize_t>(payload.stored.size())
        );
        if (stored == nullptr) {
            Py_DECREF(tuple);
            return nullptr;
        }
        PyObject* standalone = PyBytes_FromStringAndSize(
            reinterpret_cast<const char*>(payload.standalone.data()),
            static_cast<Py_ssize_t>(payload.standalone.size())
        );
        if (standalone == nullptr) {
            Py_DECREF(stored);
            Py_DECREF(tuple);
            return nullptr;
        }
        if (PyTuple_SetItem(tuple, 0, stored) < 0) {
            Py_DECREF(stored);
            Py_DECREF(standalone);
            Py_DECREF(tuple);
            return nullptr;
        }
        if (PyTuple_SetItem(tuple, 1, standalone) < 0) {
            Py_DECREF(standalone);
            Py_DECREF(tuple);
            return nullptr;
        }
        return tuple;
    } catch (const std::exception& exc) {
        PyBuffer_Release(&lut_buf);
        PyErr_SetString(PyExc_RuntimeError, exc.what());
        return nullptr;
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

}  // namespace fivefury_py
