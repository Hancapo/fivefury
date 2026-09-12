#include "resource/bindings.h"
#include <deque>
#include <unordered_map>
#include <unordered_set>

namespace fivefury_py {
namespace {
namespace binary = fivefury_native::binary;
constexpr auto capsule_name = "fivefury.MetaGraph";
struct Field {
    PyHandle name, alias;
    Py_ssize_t offset;
    int kind, element_kind;
    unsigned int reference, element_reference;
};
struct Plan {
    PyHandle scalar;
    std::vector<Field> fields;
};
void destroy_plan(PyObject* capsule) {
    delete static_cast<Plan*>(PyCapsule_GetPointer(capsule, capsule_name));
}
struct Recursion {
    bool entered = Py_EnterRecursiveCall(" while encoding a META graph") == 0;
    ~Recursion() { if (entered) Py_LeaveRecursiveCall(); }
};
struct Block {
    unsigned int name;
    std::vector<char> data;
};
void pad(std::vector<char>& data, std::size_t alignment) {
    data.resize(data.size() + binary::alignment_padding(data.size(), alignment));
}
std::uint64_t pointer_bits(std::size_t block, std::size_t offset) {
    if (block > 0xfff || offset > 0xfffff)
        throw std::overflow_error("META pointer exceeds packed block or offset limits");
    return (static_cast<std::uint64_t>(offset) << 12) | block;
}
void reference(std::vector<char>& out, std::uint64_t pointer, Py_ssize_t count = -1) {
    if (count > 0xffff) throw std::overflow_error("META reference count exceeds uint16 range");
    out.assign(count < 0 ? 8 : 16, 0);
    binary::store<std::uint64_t>(out.data(), pointer);
    if (count >= 0) {
        binary::store<std::uint16_t>(out.data() + 8, static_cast<std::uint16_t>(count));
        binary::store<std::uint16_t>(out.data() + 10, static_cast<std::uint16_t>(count));
    }
}
bool unsigned_hash(PyObject* value, unsigned int& result) {
    PyHandle number(PyNumber_Long(value));
    if (!number) return false;
    const auto raw = PyLong_AsUnsignedLongLong(number.get());
    if (PyErr_Occurred()) return false;
    if (raw > 0xffffffff) throw std::overflow_error("META structure hash exceeds uint32 range");
    result = static_cast<unsigned int>(raw);
    return true;
}
bool copy_bytes(PyObject* value, std::vector<char>& out) {
    PyHandle raw(PyObject_CallFunctionObjArgs(reinterpret_cast<PyObject*>(&PyBytes_Type), value, nullptr));
    if (!raw) return false;
    char* data; Py_ssize_t size;
    if (PyBytes_AsStringAndSize(raw.get(), &data, &size) < 0) return false;
    out.assign(data, data + size);
    return true;
}
PyObject* field_value(PyObject* values, const Field& field) {
    // Complex fields historically use membership, then get(alias), including custom Mapping overrides.
    if (PyDict_CheckExact(values)) {
        auto* result = PyDict_GetItemWithError(values, field.name.get());
        if (!result && !PyErr_Occurred()) result = PyDict_GetItemWithError(values, field.alias.get());
        if (PyErr_Occurred()) return nullptr;
        if (!result) result = Py_None;
        Py_INCREF(result);
        return result;
    }
    const int present = PySequence_Contains(values, field.name.get());
    if (present < 0) return nullptr;
    if (present) return PyObject_GetItem(values, field.name.get());
    return PyObject_CallMethod(values, "get", "O", field.alias.get());
}
struct Graph {
    PyObject *resolve, *raw_type, *mapping_type, *float_xyz, *inline_size, *hash;
    unsigned int float_xyz_hash;
    Py_ssize_t max_block_length;
    std::vector<Block> blocks;
    std::unordered_map<unsigned int, std::deque<std::size_t>> groups;
    std::unordered_map<unsigned int, PyHandle> plans;
    std::unordered_set<unsigned int> used;

    std::size_t reserve(unsigned int name, bool group = true) {
        pointer_bits(blocks.size() + 1, 0);
        const auto index = blocks.size();
        blocks.push_back({name, {}});
        if (group) groups[name].push_back(index);
        return index;
    }
    std::uint64_t add(unsigned int name, std::vector<char> data, std::size_t alignment = 16, bool group = true) {
        pad(data, alignment);
        if (group) {
            auto& indices = groups[name];
            while (!indices.empty()) {
                const auto index = indices.front();
                auto& block = blocks[index].data;
                if (max_block_length <= 0 || block.size() >= static_cast<std::size_t>(max_block_length)) {
                    indices.pop_front();
                    continue;
                }
                const auto pointer = pointer_bits(index + 1, block.size());
                block.insert(block.end(), data.begin(), data.end());
                return pointer;
            }
        }
        // Ungrouped data pointers still register their newly allocated block for subsequent grouped items.
        const auto index = reserve(name);
        blocks[index].data = std::move(data);
        return pointer_bits(index + 1, 0);
    }
    Plan* plan(unsigned int name) {
        auto found = plans.find(name);
        if (found == plans.end()) {
            PyHandle capsule(PyObject_CallFunction(resolve, "I", name));
            if (!capsule) return nullptr;
            found = plans.emplace(name, std::move(capsule)).first;
        }
        return static_cast<Plan*>(PyCapsule_GetPointer(found->second.get(), capsule_name));
    }
    bool target_hash(PyObject* value, unsigned int fallback, unsigned int& result) {
        int instance = PyObject_IsInstance(value, raw_type);
        if (instance < 0) return false;
        if (instance) {
            PyHandle name(PyObject_GetAttrString(value, "name_hash"));
            return name && unsigned_hash(name.get(), result);
        }
        instance = PyObject_IsInstance(value, mapping_type);
        if (instance < 0) return false;
        if (instance) {
            PyHandle name(PyObject_CallMethod(value, "get", "s", "_meta_name_hash"));
            if (!name) return false;
            const int truth = PyObject_IsTrue(name.get());
            if (truth < 0) return false;
            if (truth) return unsigned_hash(name.get(), result);
        }
        if (fallback) { result = fallback; return true; }
        PyErr_SetString(PyExc_ValueError, "Structure hash is required for pointer/inline structure encoding");
        return false;
    }
    bool structure(unsigned int name, PyObject* value, std::vector<char>& out) {
        Recursion recursion;
        if (!recursion.entered) return false;
        used.insert(name);
        if (name == float_xyz_hash) {
            PyHandle xyz(PyObject_CallFunctionObjArgs(float_xyz, value, nullptr));
            if (!xyz) return false;
            PyHandle items(PyTuple_Pack(1, xyz.get()));
            return items && meta_primitive_write(0x33, items.get(), hash, out);
        }
        const int raw = PyObject_IsInstance(value, raw_type);
        if (raw < 0) return false;
        if (raw) {
            PyHandle data(PyObject_GetAttrString(value, "data"));
            if (!data || !copy_bytes(data.get(), out)) return false;
            pad(out, 16);
            return true;
        }
        auto* schema = plan(name);
        if (!schema || !meta_scalar_write(schema->scalar.get(), value, hash, out)) return false;
        for (const auto& field : schema->fields) {
            PyHandle item(field_value(value, field));
            if (!item) return false;
            std::vector<char> encoded;
            if (!encode_field(field, item.get(), encoded)) return false;
            if (field.offset < 0 || !binary::contains(field.offset, encoded.size(), out.size()))
                throw std::invalid_argument("META complex field exceeds structure size");
            std::copy(encoded.begin(), encoded.end(), out.begin() + field.offset);
        }
        return true;
    }
    bool array(const Field& field, PyObject* value, std::vector<char>& out) {
        const int truth = PyObject_IsTrue(value);
        if (truth < 0) return false;
        if (!truth) { out.assign(16, 0); return true; }
        PyHandle items(PySequence_Tuple(value));
        if (!items) return false;
        const auto count = PyTuple_Size(items.get());
        if (!count || field.element_kind < 0) { out.assign(16, 0); return true; }
        if (count > 0xffff) throw std::overflow_error("META reference count exceeds uint16 range");
        std::vector<char> data;
        unsigned int block_name;
        if (field.element_kind == 0x07 || field.element_kind == 0x05) {
            block_name = field.element_kind == 0x07 ? 0x07 : field.element_reference;
            if (field.element_kind == 0x05) used.insert(block_name);
            for (Py_ssize_t i = 0; i < count; ++i) {
                auto* item = PyTuple_GetItem(items.get(), i);
                unsigned int name = field.element_reference;
                if (field.element_kind == 0x07 && !target_hash(item, 0, name)) return false;
                std::vector<char> payload;
                if (!structure(name, item, payload)) return false;
                if (field.element_kind == 0x07) {
                    const auto pointer = add(name, std::move(payload));
                    const auto offset = data.size();
                    data.resize(offset + 8);
                    binary::store<std::uint64_t>(data.data() + offset, pointer);
                } else {
                    // Inline array records concatenate without per-record alignment.
                    data.insert(data.end(), payload.begin(), payload.end());
                }
            }
        } else {
            if (!meta_primitive_write(field.element_kind, items.get(), hash, data)) return false;
            block_name = static_cast<unsigned int>(field.element_kind);
        }
        reference(out, add(block_name, std::move(data)), count);
        return true;
    }
    bool encode_field(const Field& field, PyObject* value, std::vector<char>& out) {
        switch (field.kind) {
        case 0x40: {
            const int truth = PyObject_IsTrue(value);
            if (truth < 0) return false;
            if (truth) {
                PyHandle text;
                if (PyUnicode_CheckExact(value)) {
                    text = PyHandle(PyUnicode_AsEncodedString(value, "ascii", "ignore"));
                } else {
                    PyHandle method(PyObject_GetAttrString(value, "encode"));
                    PyHandle args(Py_BuildValue("(s)", "ascii"));
                    PyHandle kwargs(Py_BuildValue("{s:s}", "errors", "ignore"));
                    if (!method || !args || !kwargs) return false;
                    text = PyHandle(PyObject_Call(method.get(), args.get(), kwargs.get()));
                }
                if (!text || !copy_bytes(text.get(), out)) return false;
            }
            out.resize(field.reference & 0xffff);
            return true;
        }
        case 0x50: {
            if (field.element_kind >= 0 && (field.reference & 0xffff) == 0) return true;
            const int truth = PyObject_IsTrue(value);
            if (truth < 0) return false;
            if (truth && field.element_kind >= 0) {
                // The remaining inline ARRAYINFO kinds retain their raw-byte fallback contract.
                PyHandle items(PySequence_List(value));
                if (!items) return false;
            }
            if (truth && !copy_bytes(value, out)) return false;
            out.resize(field.reference & 0xffff);
            return true;
        }
        case 0x44: {
            const int truth = PyObject_IsTrue(value);
            if (truth < 0) return false;
            if (!truth) { out.assign(16, 0); return true; }
            PyHandle text(PyObject_Str(value));
            if (!text) return false;
            PyHandle raw(PyUnicode_AsEncodedString(text.get(), "ascii", "ignore"));
            if (!raw || !copy_bytes(raw.get(), out)) return false;
            const auto count = out.size();
            if (count > 0xffff) throw std::overflow_error("META string count exceeds uint16 range");
            out.push_back(0);
            const auto pointer = add(0x10, std::move(out), 1);
            reference(out, pointer, count);
            return true;
        }
        case 0x59: {
            const int truth = PyObject_IsTrue(value);
            if (truth < 0) return false;
            if (truth && !copy_bytes(value, out)) return false;
            if (out.empty()) { out.assign(8, 0); return true; }
            const auto name = field.reference != 0 && field.reference != 2 ? field.reference : 0x11;
            const auto pointer = add(name, std::move(out), 1, false);
            reference(out, pointer);
            return true;
        }
        case 0x07: {
            if (value == Py_None) { out.assign(8, 0); return true; }
            unsigned int name;
            if (!target_hash(value, field.reference, name) || !structure(name, value, out)) return false;
            const auto pointer = add(name, std::move(out));
            reference(out, pointer);
            return true;
        }
        case 0x05: {
            unsigned int name = field.reference;
            if (!name && !target_hash(value, 0, name)) return false;
            used.insert(name);
            if (value != Py_None) return structure(name, value, out);
            PyHandle size(PyObject_CallFunction(inline_size, "I", name));
            if (!size) return false;
            const auto length = PyLong_AsSsize_t(size.get());
            if (PyErr_Occurred()) return false;
            if (length < 0) throw std::invalid_argument("Negative META structure size");
            out.assign(length, 0);
            return true;
        }
        case 0x52: return array(field, value, out);
        default:
            PyErr_Format(PyExc_NotImplementedError, "Unsupported META field type %d", field.kind);
            return false;
        }
    }
};
}

PyObject* mod_meta_graph_new(PyObject*, PyObject* args) {
    PyObject *scalar, *fields;
    if (!PyArg_ParseTuple(args, "OO", &scalar, &fields)) return nullptr;
    if (!PyCapsule_IsValid(scalar, "fivefury.MetaScalars")) {
        PyErr_SetString(PyExc_TypeError, "Expected a META scalar schema");
        return nullptr;
    }
    auto plan = std::make_unique<Plan>();
    Py_INCREF(scalar);
    plan->scalar = PyHandle(scalar);
    PyHandle sequence(PySequence_Tuple(fields));
    if (!sequence) return nullptr;
    for (Py_ssize_t i = 0; i < PyTuple_Size(sequence.get()); ++i) {
        PyObject *name, *alias;
        Py_ssize_t offset;
        int kind, element_kind;
        unsigned int target, element_target;
        if (!PyArg_ParseTuple(PyTuple_GetItem(sequence.get(), i), "UUniIiI",
                              &name, &alias, &offset, &kind, &target, &element_kind, &element_target)) return nullptr;
        Py_INCREF(name); Py_INCREF(alias);
        plan->fields.push_back({PyHandle(name), PyHandle(alias), offset, kind, element_kind, target, element_target});
    }
    return owned_capsule(std::move(plan), capsule_name, destroy_plan);
}

PyObject* mod_meta_graph_write(PyObject*, PyObject* args) {
    unsigned int root, xyz_hash;
    PyObject *value, *resolve, *raw_type, *mapping_type, *xyz, *inline_size, *hash;
    Py_ssize_t max_length;
    if (!PyArg_ParseTuple(args, "IOOOOOOOnI", &root, &value, &resolve, &raw_type, &mapping_type,
                          &xyz, &inline_size, &hash, &max_length, &xyz_hash)) return nullptr;
    Graph graph{resolve, raw_type, mapping_type, xyz, inline_size, hash, xyz_hash, max_length};
    graph.reserve(root, false);
    std::vector<char> payload;
    if (!graph.structure(root, value, payload)) return nullptr;
    pad(payload, 16);
    graph.blocks[0].data = std::move(payload);
    PyHandle blocks(PyList_New(graph.blocks.size()));
    PyHandle used(PySet_New(nullptr));
    if (!blocks || !used) return nullptr;
    for (std::size_t i = 0; i < graph.blocks.size(); ++i) {
        const auto& block = graph.blocks[i];
        PyHandle data(PyByteArray_FromStringAndSize(block.data.data(), block.data.size()));
        PyHandle name(PyLong_FromUnsignedLong(block.name));
        if (!data || !name || !list_take(blocks.get(), i, PyTuple_Pack(2, name.get(), data.get()))) return nullptr;
    }
    for (auto name : graph.used) {
        PyHandle item(PyLong_FromUnsignedLong(name));
        if (!item || PySet_Add(used.get(), item.get()) < 0) return nullptr;
    }
    return PyTuple_Pack(2, blocks.get(), used.get());
}
}  // namespace fivefury_py
