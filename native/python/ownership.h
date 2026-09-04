#pragma once

#include <utility>

namespace fivefury_py {

class PyHandle {
public:
    explicit PyHandle(PyObject* object = nullptr) noexcept : object_(object) {}
    ~PyHandle() { Py_XDECREF(object_); }
    PyHandle(const PyHandle&) = delete;
    PyHandle& operator=(const PyHandle&) = delete;
    PyHandle(PyHandle&& other) noexcept : object_(other.release()) {}
    PyObject* get() const noexcept { return object_; }
    PyObject* release() noexcept { return std::exchange(object_, nullptr); }
    explicit operator bool() const noexcept { return object_ != nullptr; }

private:
    PyObject* object_;
};

class Buffer : public Py_buffer {
public:
    Buffer() noexcept : Py_buffer{} {}
    ~Buffer() { release(); }
    Buffer(const Buffer&) = delete;
    Buffer& operator=(const Buffer&) = delete;
    void release() noexcept {
        if (obj != nullptr) PyBuffer_Release(this);
    }
    bool acquire(PyObject* object, int flags = PyBUF_SIMPLE) {
        release();
        return PyObject_GetBuffer(object, this, flags) == 0;
    }
};

class GilRelease {
public:
    GilRelease() : state_(PyEval_SaveThread()) {}
    ~GilRelease() { PyEval_RestoreThread(state_); }
    GilRelease(const GilRelease&) = delete;
    GilRelease& operator=(const GilRelease&) = delete;

private:
    PyThreadState* state_;
};

inline bool tuple_take(PyObject* tuple, Py_ssize_t index, PyObject* value) {
    return value != nullptr && PyTuple_SetItem(tuple, index, value) == 0;
}

inline bool list_take(PyObject* list, Py_ssize_t index, PyObject* value) {
    return value != nullptr && PyList_SetItem(list, index, value) == 0;
}

}  // namespace fivefury_py
