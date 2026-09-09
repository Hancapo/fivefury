#include "python/bridge.h"

namespace fivefury_py {
namespace {
// All other attributes go directly through the normal descriptor protocol.
// Keeping this in tp_setattro avoids a Python frame for every numeric field
// assigned by a dataclass constructor, while preserving hash coercion on edits.
int set_hash_field(PyObject* self, PyObject* name, PyObject* value) {
    if (value == nullptr) return PyObject_GenericSetAttr(self, name, nullptr);
    auto* cls = reinterpret_cast<PyObject*>(Py_TYPE(self));
    constexpr const char* fields[] = {"_hash_fields", "_hash_list_fields"};
    constexpr const char* coercers[] = {"_coerce_hash_field", "_coerce_hash_list_field"};
    for (int i = 0; i < 2; ++i) {
        PyHandle names(PyObject_GetAttrString(cls, fields[i]));
        if (!names) return -1;
        const int contains = PySequence_Contains(names.get(), name);
        if (contains < 0) return -1;
        if (contains == 0) continue;
        PyHandle coerce(PyObject_GetAttrString(cls, coercers[i]));
        if (!coerce) return -1;
        PyHandle converted(PyObject_CallFunctionObjArgs(coerce.get(), value, nullptr));
        if (!converted) return -1;
        return PyObject_GenericSetAttr(self, name, converted.get());
    }
    return PyObject_GenericSetAttr(self, name, value);
}
}

PyObject* create_hash_fields_type() {
    PyType_Slot slots[] = {
        {Py_tp_setattro, reinterpret_cast<void*>(set_hash_field)},
        {Py_tp_new, reinterpret_cast<void*>(PyType_GenericNew)},
        {0, nullptr},
    };
    PyType_Spec spec = {
        "fivefury._native_abi3.HashFields", sizeof(PyObject), 0,
        Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, slots,
    };
    return PyType_FromSpec(&spec);
}
} // namespace fivefury_py
