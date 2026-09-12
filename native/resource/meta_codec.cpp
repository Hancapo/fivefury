#include "resource/bindings.h"
#include "python/record_factory.h"
#include <cmath>
#include <memory>
#include <vector>

namespace fivefury_py {
namespace {
namespace binary = fivefury_native::binary;
constexpr auto capsule_name = "fivefury.MetaScalars";
struct Field {
    PyHandle name, alias;
    int kind;
    Py_ssize_t offset, count;
};
struct Schema {
    Py_ssize_t size;
    std::vector<Field> fields;
};
constexpr auto model_capsule_name = "fivefury.MetaModel";
struct ModelField {
    PyHandle converter;
    std::unique_ptr<RecordFactory> vector;
    bool scalar_record = false;
};
struct ReferenceField {
    PyHandle name;
    ModelField value;
    Py_ssize_t offset;
    int kind, element_kind;
};
struct Model {
    PyHandle schema_owner, type_owner;
    Schema* schema;
    RecordFactory factory;
    std::vector<ModelField> fields;
    std::vector<ReferenceField> references;
    bool opaque_fields = false;
    Model(PyHandle schema_ref, Schema* schema_value, PyHandle type_ref, PyObject* names)
        : schema_owner(std::move(schema_ref)), type_owner(std::move(type_ref)),
          schema(schema_value), factory(type_owner.get(), names) {}
};
void destroy_model(PyObject* capsule) {
    delete static_cast<Model*>(PyCapsule_GetPointer(capsule, model_capsule_name));
}
std::size_t width(int kind) {
    switch (kind) {
    case 1: case 0x10: case 0x11: case 0x60: return 1;
    case 0x12: case 0x13: case 0x64: return 2;
    case 0x14: case 0x15: case 0x21: case 0x4a:
    case 0x62: case 0x63: case 0x65: return 4;
    case 0x33: return 12;
    case 0x34: return 16;
    default: throw std::invalid_argument("Unsupported META scalar type");
    }
}
void destroy_schema(PyObject* capsule) {
    delete static_cast<Schema*>(PyCapsule_GetPointer(capsule, capsule_name));
}
template<typename T> bool write_integer(char* out, PyObject* value) {
    PyHandle integer(PyNumber_Long(value));
    if (!integer) return false;
    const auto number = PyLong_AsLongLong(integer.get());
    if (PyErr_Occurred()) return false;
    if (number < static_cast<long long>(std::numeric_limits<T>::min()) ||
        number > static_cast<long long>(std::numeric_limits<T>::max())) {
        PyErr_SetString(PyExc_OverflowError, "META integer exceeds field range");
        return false;
    }
    binary::store<T>(out, static_cast<T>(number));
    return true;
}
bool write_float(char* out, PyObject* value) {
    PyHandle converted(PyNumber_Float(value));
    if (!converted) return false;
    const double number = PyFloat_AsDouble(converted.get());
    if (PyErr_Occurred()) return false;
    const auto packed = static_cast<float>(number);
    if (std::isfinite(number) && !std::isfinite(packed)) {
        PyErr_SetString(PyExc_OverflowError, "META float exceeds float32 range");
        return false;
    }
    binary::store<float>(out, packed);
    return true;
}
bool encode(char* out, int kind, PyObject* value, PyObject* hash) {
    if (value == Py_None) return true; // Payload is initialized to zero.
    if (kind != 0x4a && kind != 0x33 && kind != 0x34) {
        const int truth = PyObject_IsTrue(value);
        if (truth < 0) return false;
        if (!truth) return true;
    }
    switch (kind) {
    case 1: {
        int truth = PyObject_IsTrue(value);
        if (truth < 0) return false;
        *out = static_cast<char>(truth); return true;
    }
    case 0x10: return write_integer<std::int8_t>(out, value);
    case 0x11: case 0x60: return write_integer<std::uint8_t>(out, value);
    case 0x12: case 0x64: return write_integer<std::int16_t>(out, value);
    case 0x13: return write_integer<std::uint16_t>(out, value);
    case 0x14: case 0x62: case 0x63: case 0x65: return write_integer<std::int32_t>(out, value);
    case 0x15: return write_integer<std::uint32_t>(out, value);
    case 0x4a: {
        if (!PyUnicode_Check(value)) return write_integer<std::uint32_t>(out, value);
        PyHandle number(PyObject_CallFunctionObjArgs(hash, value, nullptr));
        return number && write_integer<std::uint32_t>(out, number.get());
    }
    case 0x21: return write_float(out, value);
    default: {
        if (PyUnicode_Check(value) || PyBytes_Check(value) || PyByteArray_Check(value)) {
            PyErr_SetString(PyExc_TypeError, "Vector values must be numeric iterables"); return false;
        }
        PyHandle components(PySequence_Tuple(value));
        if (!components) return false;
        const Py_ssize_t count = kind == 0x33 ? 3 : 4;
        if (PyTuple_Size(components.get()) != count) {
            PyErr_SetString(PyExc_ValueError, "Incorrect META vector dimension"); return false;
        }
        for (Py_ssize_t i = 0; i < count; ++i)
            if (!write_float(out + i * 4, PyTuple_GetItem(components.get(), i))) return false;
        return true;
    }
    }
}
PyObject* decode(const char* in, int kind) {
    switch (kind) {
    case 1: return PyBool_FromLong(*in != 0);
    case 0x10: return PyLong_FromLong(binary::load<std::int8_t>(in));
    case 0x11: case 0x60: return PyLong_FromLong(binary::load<std::uint8_t>(in));
    case 0x12: case 0x64: return PyLong_FromLong(binary::load<std::int16_t>(in));
    case 0x13: return PyLong_FromLong(binary::load<std::uint16_t>(in));
    case 0x14: case 0x62: case 0x63: case 0x65: return PyLong_FromLong(binary::load<std::int32_t>(in));
    case 0x15: case 0x4a: return PyLong_FromUnsignedLong(binary::load<std::uint32_t>(in));
    case 0x21: return PyFloat_FromDouble(binary::load<float>(in));
    default: {
        const Py_ssize_t count = kind == 0x33 ? 3 : 4;
        PyHandle result(PyTuple_New(count));
        if (!result) return nullptr;
        for (Py_ssize_t i = 0; i < count; ++i)
            if (!tuple_take(result.get(), i, PyFloat_FromDouble(binary::load<float>(in + i * 4)))) return nullptr;
        return result.release();
    }
    }
}
}

namespace {
PyObject* decode_field(const char* data, const Field& field) {
    const auto* in = data + field.offset;
    if (field.count < 0) return decode(in, field.kind);
    PyHandle result(PyTuple_New(field.count));
    if (!result) return nullptr;
    const auto step = width(field.kind);
    for (Py_ssize_t i = 0; i < field.count; ++i)
        if (!tuple_take(result.get(), i, decode(in + i * step, field.kind))) return nullptr;
    return result.release();
}
bool encode_array_item(char* target, int kind, PyObject* item, PyObject* hash) {
    switch (kind) {
    case 0x21: if (!write_float(target, item)) return false; break;
    case 0x11: {
        PyHandle integer(PyNumber_Long(item));
        if (!integer) return false;
        const auto number = PyLong_AsUnsignedLongLongMask(integer.get());
        if (PyErr_Occurred()) return false;
        *target = static_cast<char>(number & 0xff); break;
    }
    case 0x10: if (!write_integer<std::int8_t>(target, item)) return false; break;
    case 0x12: if (!write_integer<std::int16_t>(target, item)) return false; break;
    case 0x13: if (!write_integer<std::uint16_t>(target, item)) return false; break;
    case 0x14: if (!write_integer<std::int32_t>(target, item)) return false; break;
    case 0x15: if (!write_integer<std::uint32_t>(target, item)) return false; break;
    default: if (!encode(target, kind, item, hash)) return false; break;
    }
    return true;
}
bool encode_field(char* data, const Field& field, PyObject* value, PyObject* hash) {
    auto* out = data + field.offset;
    if (field.count < 0) return encode(out, field.kind, value, hash);
    if (field.count == 0) return true;
    const int truth = PyObject_IsTrue(value);
    if (truth < 0) return false;
    if (!truth) return true;
    PyHandle items(PySequence_Tuple(value));
    if (!items) return false;
    const auto count = std::min(field.count, PyTuple_Size(items.get()));
    const auto step = width(field.kind);
    for (Py_ssize_t i = 0; i < count; ++i) {
        auto* item = PyTuple_GetItem(items.get(), i);
        auto* target = out + i * step;
        if (!encode_array_item(target, field.kind, item, hash)) return false;
    }
    return true;
}
}

PyObject* mod_meta_scalars_new(PyObject*, PyObject* args) {
    Py_ssize_t size; PyObject* fields;
    if (!PyArg_ParseTuple(args, "nO", &size, &fields)) return nullptr;
    if (size < 0) throw std::invalid_argument("Negative META structure size");
    auto schema = std::make_unique<Schema>(); schema->size = size;
    PyHandle sequence(PySequence_Tuple(fields));
    if (!sequence) return nullptr;
    for (Py_ssize_t i = 0; i < PyTuple_Size(sequence.get()); ++i) {
        PyObject *name, *alias; int kind; Py_ssize_t offset, count = -1;
        if (!PyArg_ParseTuple(PyTuple_GetItem(sequence.get(), i), "UUni|n", &name, &alias, &offset, &kind, &count)) return nullptr;
        const auto step = width(kind);
        if (count < -1 || (count >= 0 && (step > 4 || static_cast<std::size_t>(count) > static_cast<std::size_t>(size) / step)))
            throw std::invalid_argument("Invalid META fixed array size");
        if (offset < 0 || !binary::contains(offset, step * (count < 0 ? 1 : count), size))
            throw std::invalid_argument("META field exceeds structure size");
        Py_INCREF(name); Py_INCREF(alias);
        schema->fields.push_back({PyHandle(name), PyHandle(alias), kind, offset, count});
    }
    return owned_capsule(std::move(schema), capsule_name, destroy_schema);
}
PyObject* mod_meta_scalars_read(PyObject*, PyObject* args) {
    PyObject *capsule, *raw;
    if (!PyArg_ParseTuple(args, "OO", &capsule, &raw)) return nullptr;
    auto* schema = static_cast<Schema*>(PyCapsule_GetPointer(capsule, capsule_name));
    if (!schema) return nullptr;
    Buffer data; if (!data.acquire(raw)) return nullptr;
    if (data.len < schema->size) throw std::invalid_argument("META structure is truncated");
    PyHandle result(PyDict_New()); if (!result) return nullptr;
    for (const auto& field : schema->fields) {
        PyHandle value(decode_field(static_cast<const char*>(data.buf), field));
        if (!value || PyDict_SetItem(result.get(), field.name.get(), value.get()) < 0) return nullptr;
    }
    return result.release();
}
namespace {
bool encode_scalars(const Schema& schema, PyObject* values, PyObject* hash, char* out) {
    for (const auto& field : schema.fields) {
        PyHandle value(PyObject_GetItem(values, field.name.get()));
        if (!value) {
            if (!PyErr_ExceptionMatches(PyExc_KeyError)) return false;
            PyErr_Clear();
            PyHandle alias(PyObject_GetItem(values, field.alias.get()));
            if (!alias) {
                if (!PyErr_ExceptionMatches(PyExc_KeyError)) return false;
                PyErr_Clear(); continue;
            }
            if (!encode_field(out, field, alias.get(), hash)) return false;
        } else if (!encode_field(out, field, value.get(), hash)) return false;
    }
    return true;
}
}

bool meta_scalar_write(PyObject* capsule, PyObject* values, PyObject* hash, std::vector<char>& data) {
    auto* schema = static_cast<Schema*>(PyCapsule_GetPointer(capsule, capsule_name));
    if (!schema) return false;
    data.assign(schema->size, 0);
    return encode_scalars(*schema, values, hash, data.data());
}

bool meta_primitive_write(int kind, PyObject* items, PyObject* hash, std::vector<char>& data) {
    switch (kind) {
    case 0x21: case 0x15: case 0x4a: case 0x13: case 0x11: case 0x33: break;
    default:
        PyErr_Format(PyExc_NotImplementedError, "Unsupported array element type %d", kind);
        return false;
    }
    const auto count = PyTuple_Size(items);
    const auto step = kind == 0x33 ? 16 : width(kind);
    data.assign(checked_buffer_size(count, step), 0);
    for (Py_ssize_t i = 0; i < count; ++i)
        if (!encode_array_item(data.data() + i * step, kind, PyTuple_GetItem(items, i), hash)) return false;
    return true;
}

PyObject* mod_meta_scalars_write(PyObject*, PyObject* args) {
    PyObject *capsule, *values, *hash;
    if (!PyArg_ParseTuple(args, "OOO", &capsule, &values, &hash)) return nullptr;
    auto* schema = static_cast<Schema*>(PyCapsule_GetPointer(capsule, capsule_name));
    if (!schema) return nullptr;
    PyHandle result(PyByteArray_FromStringAndSize(nullptr, schema->size));
    if (!result) return nullptr;
    auto* out = PyByteArray_AsString(result.get());
    std::memset(out, 0, schema->size);
    if (!encode_scalars(*schema, values, hash, out)) return nullptr;
    return result.release();
}

namespace {
bool model_binding(PyObject* converter, int kind, Py_ssize_t count, ModelField& binding) {
    if (PyTuple_Check(converter)) {
        PyObject *type, *components;
        if (!PyArg_ParseTuple(converter, "OO", &type, &components)) return false;
        binding.vector = std::make_unique<RecordFactory>(type, components);
        if (!*binding.vector) return false;
        binding.scalar_record = kind == 0x4a && count < 0 && binding.vector->dimensions() == 2;
        const auto dimensions = count < 0 ? (kind == 0x33 ? 3 : kind == 0x34 ? 4 : 0) : (kind == 0x21 ? count : 0);
        if (!binding.scalar_record && ((dimensions != 3 && dimensions != 4) || binding.vector->dimensions() != dimensions))
            throw std::invalid_argument("META vector binding has incompatible dimensions");
    } else if (converter != Py_None && !PyCallable_Check(converter)) {
        PyErr_SetString(PyExc_TypeError, "META model converter must be callable"); return false;
    }
    Py_INCREF(converter);
    binding.converter = PyHandle(converter);
    return true;
}
PyObject* convert_value(const ModelField& binding, PyObject* value) {
    if (binding.vector) return binding.scalar_record ? binding.vector->scalar(value) : binding.vector->numeric(value);
    if (binding.converter.get() != Py_None) return PyObject_CallFunctionObjArgs(binding.converter.get(), value, nullptr);
    Py_INCREF(value);
    return value;
}
}

PyObject* mod_meta_model_new(PyObject*, PyObject* args) {
    PyObject *capsule, *type, *bindings, *references = Py_None; int opaque = 0;
    if (!PyArg_ParseTuple(args, "OOO|Op", &capsule, &type, &bindings, &references, &opaque)) return nullptr;
    auto* schema = static_cast<Schema*>(PyCapsule_GetPointer(capsule, capsule_name));
    if (!schema) return nullptr;
    PyHandle sequence(PySequence_Tuple(bindings));
    if (!sequence) return nullptr;
    const auto count = PyTuple_Size(sequence.get());
    if (static_cast<std::size_t>(count) != schema->fields.size())
        throw std::invalid_argument("Incorrect META model binding count");
    PyHandle names(PyList_New(count));
    if (!names) return nullptr;
    std::vector<ModelField> fields;
    fields.reserve(schema->fields.size());
    for (Py_ssize_t i = 0; i < count; ++i) {
        PyObject *name, *converter;
        if (!PyArg_ParseTuple(PyTuple_GetItem(sequence.get(), i), "UO", &name, &converter)) return nullptr;
        Py_INCREF(name);
        if (!list_take(names.get(), i, name)) return nullptr;
        ModelField binding;
        if (!model_binding(converter, schema->fields[i].kind, schema->fields[i].count, binding)) return nullptr;
        fields.push_back(std::move(binding));
    }
    Py_INCREF(capsule); Py_INCREF(type);
    auto model = std::make_unique<Model>(PyHandle(capsule), schema, PyHandle(type), names.get());
    if (!model->factory) return nullptr;
    model->fields = std::move(fields);
    model->opaque_fields = opaque != 0;
    if (references != Py_None) {
        PyHandle reference_fields(PySequence_Tuple(references));
        if (!reference_fields) return nullptr;
        for (Py_ssize_t i = 0; i < PyTuple_Size(reference_fields.get()); ++i) {
            PyObject *name, *convert; Py_ssize_t offset; int kind, element_kind;
            if (!PyArg_ParseTuple(PyTuple_GetItem(reference_fields.get(), i), "UniiO", &name, &offset, &kind, &element_kind, &convert)) return nullptr;
            if (offset < 0 || !binary::contains(offset, 16, schema->size) || (kind != 0x52 && kind != 0x44))
                throw std::invalid_argument("Invalid META model reference field");
            if (element_kind != 0 && (width(element_kind) > 4 || kind != 0x52))
                throw std::invalid_argument("Invalid META model array element");
            ModelField binding;
            if (!model_binding(convert, element_kind, -1, binding)) return nullptr;
            Py_INCREF(name);
            model->references.push_back({PyHandle(name), std::move(binding), offset, kind, element_kind});
        }
    }
    return owned_capsule(std::move(model), model_capsule_name, destroy_model);
}

namespace {
struct BlockSlice { const char* data = nullptr; Py_ssize_t size = 0; };
bool resolve_pointer(PyObject* blocks, std::uint64_t pointer, BlockSlice& result) {
    const auto block_id = static_cast<Py_ssize_t>(pointer & 0xfff);
    if (blocks == Py_None || block_id == 0 || block_id > PyTuple_Size(blocks)) return true;
    char* data; Py_ssize_t size;
    if (PyBytes_AsStringAndSize(PyTuple_GetItem(blocks, block_id - 1), &data, &size) < 0) return false;
    const auto offset = static_cast<Py_ssize_t>((pointer >> 12) & 0xfffff);
    result = {data + std::min(offset, size), std::max(Py_ssize_t(0), size - offset)};
    return true;
}
PyObject* read_model(Model* model, const char* data, Py_ssize_t size, PyObject* blocks, bool& pending) {
    if (size < model->schema->size) throw std::invalid_argument("META structure is truncated");
    PyHandle result(model->factory.create());
    if (!result) return nullptr;
    for (std::size_t i = 0; i < model->fields.size(); ++i) {
        const auto& field = model->schema->fields[i];
        const auto& binding = model->fields[i];
        if (binding.vector && !binding.scalar_record) {
            std::array<double, 4> components{};
            const auto count = binding.vector->dimensions();
            for (Py_ssize_t j = 0; j < count; ++j) components[j] = binary::load<float>(data + field.offset + j * 4);
            PyHandle converted(binding.vector->numeric(std::span<const double>(components.data(), count)));
            if (!model->factory.assign(result.get(), i, converted.get())) return nullptr;
        } else {
            PyHandle value(decode_field(data, field));
            if (!value) return nullptr;
            PyHandle converted(convert_value(binding, value.get()));
            if (!model->factory.assign(result.get(), i, converted.get())) return nullptr;
        }
    }
    pending = model->opaque_fields;
    for (const auto& field : model->references) {
        const auto pointer = binary::load<std::uint64_t>(data + field.offset);
        auto count = binary::load<std::uint16_t>(data + field.offset + 8);
        if (count && (pointer & 0xfff) && field.kind == 0x52 && field.element_kind == 0) {
            pending = true; continue;
        }
        BlockSlice source;
        if (!resolve_pointer(blocks, pointer, source)) return nullptr;
        if (!source.data) count = 0;
        PyHandle value;
        if (field.kind == 0x44) {
            value = PyHandle(PyUnicode_DecodeASCII(source.data ? source.data : "", std::min<Py_ssize_t>(count, source.size), "ignore"));
        } else {
            value = PyHandle(PyList_New(count));
            if (!value) return nullptr;
            const auto step = count ? width(field.element_kind) : 0;
            if (!binary::contains(0, count * step, source.size)) throw std::invalid_argument("META array is truncated");
            for (Py_ssize_t i = 0; i < count; ++i) {
                PyHandle item(decode(source.data + i * step, field.element_kind));
                if (!item) return nullptr;
                if (!list_take(value.get(), i, convert_value(field.value, item.get()))) return nullptr;
            }
        }
        if (!value || PyObject_GenericSetAttr(result.get(), field.name.get(), value.get()) < 0) return nullptr;
    }
    return result.release();
}
}

PyObject* mod_meta_model_read(PyObject*, PyObject* args) {
    PyObject *capsule, *raw, *blocks = Py_None;
    if (!PyArg_ParseTuple(args, "OO|O", &capsule, &raw, &blocks)) return nullptr;
    auto* model = static_cast<Model*>(PyCapsule_GetPointer(capsule, model_capsule_name));
    if (!model) return nullptr;
    PyHandle owned_blocks(blocks == Py_None ? PyTuple_New(0) : PySequence_Tuple(blocks));
    if (!owned_blocks) return nullptr;
    Buffer data;
    if (!data.acquire(raw)) return nullptr;
    bool pending;
    return read_model(model, static_cast<const char*>(data.buf), data.len, owned_blocks.get(), pending);
}

PyObject* mod_meta_struct_values(PyObject*, PyObject* args) {
    PyObject *record, *fields, *prefix, *serialize; int custom;
    if (!PyArg_ParseTuple(args, "OOOOp", &record, &fields, &prefix, &serialize, &custom)) return nullptr;
    PyHandle names(PySequence_Tuple(fields)), result(PyDict_Copy(prefix));
    if (!names || !result) return nullptr;
    for (Py_ssize_t i = 0; i < PyTuple_Size(names.get()); ++i) {
        PyObject *attribute, *name;
        if (!PyArg_ParseTuple(PyTuple_GetItem(names.get(), i), "UU", &attribute, &name)) return nullptr;
        PyHandle value(PyObject_GetAttr(record, attribute));
        if (!value) return nullptr;
        auto* object = value.get();
        const bool atomic = object == Py_None || PyBool_Check(object) || PyLong_CheckExact(object) ||
            PyFloat_CheckExact(object) || PyUnicode_CheckExact(object) || PyBytes_CheckExact(object) || PyTuple_CheckExact(object);
        if (custom || !atomic) {
            PyHandle converted(PyObject_CallFunctionObjArgs(serialize, attribute, object, nullptr));
            if (!converted) return nullptr;
            value = std::move(converted);
        }
        if (PyDict_SetItem(result.get(), name, value.get()) < 0) return nullptr;
    }
    return result.release();
}

namespace {
PyObject* read_bound_model(PyObject* binding, const BlockSlice& source, PyObject* buffers, PyObject* context) {
    PyObject *capsule, *complete, *info;
    if (!PyArg_ParseTuple(binding, "OOO", &capsule, &complete, &info)) return nullptr;
    auto* model = static_cast<Model*>(PyCapsule_GetPointer(capsule, model_capsule_name));
    if (!model) return nullptr;
    bool pending;
    PyHandle value(read_model(model, source.data, source.size, buffers, pending));
    if (!value) return nullptr;
    if (pending) {
        PyHandle raw(PyBytes_FromStringAndSize(source.data, model->schema->size));
        if (!raw) return nullptr;
        PyHandle completed(PyObject_CallFunctionObjArgs(complete, context, info, value.get(), raw.get(), nullptr));
        if (!completed) return nullptr;
    }
    return value.release();
}
}

PyObject* mod_meta_model_array_read(PyObject*, PyObject* args) {
    PyObject *binding, *blocks, *context; unsigned long long pointer; Py_ssize_t stride, count;
    if (!PyArg_ParseTuple(args, "OOKnnO", &binding, &blocks, &pointer, &stride, &count, &context)) return nullptr;
    PyHandle buffers(PySequence_Tuple(blocks));
    if (!buffers) return nullptr;
    BlockSlice source;
    if (!resolve_pointer(buffers.get(), pointer, source)) return nullptr;
    if (stride <= 0 || count < 0 || count > source.size / stride)
        throw std::invalid_argument("META structure array is truncated");
    PyHandle result(PyList_New(count));
    if (!result) return nullptr;
    for (Py_ssize_t i = 0; i < count; ++i) {
        BlockSlice row{source.data + i * stride, stride};
        if (!list_take(result.get(), i, read_bound_model(binding, row, buffers.get(), context))) return nullptr;
    }
    return result.release();
}

PyObject* mod_meta_models_read(PyObject*, PyObject* args) {
    PyObject *bindings, *blocks, *pointers, *context;
    if (!PyArg_ParseTuple(args, "OOOO", &bindings, &blocks, &pointers, &context)) return nullptr;
    PyHandle plans(PySequence_Tuple(bindings)), buffers(PySequence_Tuple(blocks)), refs(PySequence_Tuple(pointers));
    if (!plans || !buffers || !refs) return nullptr;
    if (PyTuple_Size(plans.get()) != PyTuple_Size(buffers.get())) throw std::invalid_argument("META block binding count differs");
    PyHandle result(PyList_New(PyTuple_Size(refs.get())));
    if (!result) return nullptr;
    for (Py_ssize_t i = 0; i < PyTuple_Size(refs.get()); ++i) {
        auto* pointer_value = PyTuple_GetItem(refs.get(), i);
        const auto pointer = PyLong_AsUnsignedLongLong(pointer_value);
        if (PyErr_Occurred()) return nullptr;
        const auto block_id = static_cast<Py_ssize_t>(pointer & 0xfff);
        PyObject* binding = block_id && block_id <= PyTuple_Size(plans.get()) ? PyTuple_GetItem(plans.get(), block_id - 1) : Py_None;
        PyHandle value;
        if (binding == Py_None) {
            value = PyHandle(PyObject_CallMethod(context, "_resolve_pointer_value", "O", pointer_value));
        } else {
            BlockSlice source;
            if (!resolve_pointer(buffers.get(), pointer, source)) return nullptr;
            value = PyHandle(read_bound_model(binding, source, buffers.get(), context));
        }
        if (!value || !list_take(result.get(), i, value.release())) return nullptr;
    }
    return result.release();
}
} // namespace fivefury_py
