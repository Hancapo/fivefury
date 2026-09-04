#include "binary/primitives.h"
#include "spatial/bindings.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <limits>
#include <vector>

namespace fivefury_py {
namespace binary = fivefury_native::binary;

namespace {

constexpr std::uint64_t VIRTUAL_BASE = 0x50000000ULL;
constexpr std::size_t POLYGON_SIZE = 16U;
constexpr std::size_t BVH_RECORD_SIZE = 16U;
constexpr std::size_t YNV_LIST_PART_SIZE = 16U;
constexpr std::size_t YNV_EDGE_SIZE = 8U;






bool checked_span(std::size_t start, std::size_t count, std::size_t item_size, std::size_t size) {
    return start <= size && count <= (size - start) / item_size;
}

bool virtual_offset(std::uint64_t pointer, std::size_t size, std::size_t& offset) {
    if (pointer < VIRTUAL_BASE) {
        return false;
    }
    const auto raw = pointer - VIRTUAL_BASE;
    if (raw > size) {
        return false;
    }
    offset = static_cast<std::size_t>(raw);
    return true;
}

bool parse_vector3(PyObject* object, std::array<double, 3>& result, const char* message) {
    PyHandle sequence_owner(PySequence_Fast(object, message));
    PyObject* sequence = sequence_owner.get();
    if (sequence == nullptr) {
        return false;
    }
    if (PySequence_Size(sequence) < 3) {
        PyErr_SetString(PyExc_ValueError, message);
        return false;
    }
    for (std::size_t index = 0; index < 3U; ++index) {
        PyObject* item = PySequence_GetItem(sequence, static_cast<Py_ssize_t>(index));
        result[index] = PyFloat_AsDouble(item);
        Py_XDECREF(item);
        if (PyErr_Occurred() != nullptr) {
            return false;
        }
    }
    return true;
}

struct PolygonRecord {
    std::array<std::uint8_t, POLYGON_SIZE> raw{};
    std::uint8_t type = 0;
    float scalar = 0.0F;
    std::array<std::int64_t, 6> values{};
};

struct BvhRecord {
    std::array<double, 3> minimum{};
    std::array<double, 3> maximum{};
    std::uint16_t item_id = 0;
    std::uint16_t item_count = 0;
};

struct YnvEdgeRecord {
    std::array<std::uint32_t, 8> values{};
};

PyObject* build_polygon_values(const PolygonRecord& record) {
    switch (record.type) {
        case 0:
            return Py_BuildValue(
                "(diiiiii)",
                static_cast<double>(record.scalar),
                static_cast<int>(record.values[0]),
                static_cast<int>(record.values[1]),
                static_cast<int>(record.values[2]),
                static_cast<int>(record.values[3]),
                static_cast<int>(record.values[4]),
                static_cast<int>(record.values[5])
            );
        case 1:
            return Py_BuildValue(
                "(iidKK)",
                static_cast<int>(record.values[0]),
                static_cast<int>(record.values[1]),
                static_cast<double>(record.scalar),
                static_cast<unsigned long long>(record.values[2]),
                static_cast<unsigned long long>(record.values[3])
            );
        case 2:
        case 4:
            return Py_BuildValue(
                "(iidiiK)",
                static_cast<int>(record.values[0]),
                static_cast<int>(record.values[1]),
                static_cast<double>(record.scalar),
                static_cast<int>(record.values[2]),
                static_cast<int>(record.values[3]),
                static_cast<unsigned long long>(record.values[4])
            );
        case 3:
            return Py_BuildValue(
                "(KiiiiK)",
                static_cast<unsigned long long>(record.values[0]),
                static_cast<int>(record.values[1]),
                static_cast<int>(record.values[2]),
                static_cast<int>(record.values[3]),
                static_cast<int>(record.values[4]),
                static_cast<unsigned long long>(record.values[5])
            );
        default:
            return PyTuple_New(0);
    }
}

PyObject* build_vector3(const std::array<double, 3>& value) {
    return Py_BuildValue("(ddd)", value[0], value[1], value[2]);
}

}  // namespace

PyObject* mod_bounds_decode_polygons(PyObject*, PyObject* args) {
    PyObject* data_object = nullptr;
    Py_ssize_t start_value = 0;
    Py_ssize_t count_value = 0;
    if (!PyArg_ParseTuple(args, "Onn:bounds_decode_polygons", &data_object, &start_value, &count_value)) {
        return nullptr;
    }
    if (start_value < 0 || count_value < 0) {
        PyErr_SetString(PyExc_ValueError, "polygon offset and count must be non-negative");
        return nullptr;
    }
    Buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    const auto start = static_cast<std::size_t>(start_value);
    const auto count = static_cast<std::size_t>(count_value);
    const auto size = static_cast<std::size_t>(buffer.len);
    if (!checked_span(start, count, POLYGON_SIZE, size)) {
        buffer.release();
        PyErr_SetString(PyExc_ValueError, "polygon array is truncated");
        return nullptr;
    }

    std::vector<PolygonRecord> records(count);
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    {
    GilRelease gil_release;
    for (std::size_t index = 0; index < count; ++index) {
        const auto* source = data + start + (index * POLYGON_SIZE);
        auto& record = records[index];
        std::copy_n(source, POLYGON_SIZE, record.raw.begin());
        record.type = record.raw[0] & 0x07U;
        if (record.type > 4U) {
            record.type = 0;
        }
        record.raw[0] &= 0xF8U;
        const auto* decoded = record.raw.data();
        switch (record.type) {
            case 0:
                record.scalar = binary::load<float>(decoded);
                for (std::size_t field = 0; field < 6U; ++field) {
                    record.values[field] = binary::load<std::uint16_t>(decoded + 4U + (field * 2U));
                }
                break;
            case 1:
                record.values[0] = binary::load<std::uint16_t>(decoded);
                record.values[1] = binary::load<std::uint16_t>(decoded + 2U);
                record.scalar = binary::load<float>(decoded + 4U);
                record.values[2] = binary::load<std::uint32_t>(decoded + 8U);
                record.values[3] = binary::load<std::uint32_t>(decoded + 12U);
                break;
            case 2:
            case 4:
                record.values[0] = binary::load<std::uint16_t>(decoded);
                record.values[1] = binary::load<std::uint16_t>(decoded + 2U);
                record.scalar = binary::load<float>(decoded + 4U);
                record.values[2] = binary::load<std::uint16_t>(decoded + 8U);
                record.values[3] = binary::load<std::uint16_t>(decoded + 10U);
                record.values[4] = binary::load<std::uint32_t>(decoded + 12U);
                break;
            case 3:
                record.values[0] = binary::load<std::uint32_t>(decoded);
                for (std::size_t field = 0; field < 4U; ++field) {
                    record.values[field + 1U] = binary::load<std::int16_t>(decoded + 4U + (field * 2U));
                }
                record.values[5] = binary::load<std::uint32_t>(decoded + 12U);
                break;
            default:
                break;
        }
    }
    }
    buffer.release();

    PyObject* result = PyList_New(count_value);
    if (result == nullptr) {
        return nullptr;
    }
    for (std::size_t index = 0; index < count; ++index) {
        const auto& record = records[index];
        PyObject* item = PyTuple_New(3);
        PyObject* type = PyLong_FromUnsignedLong(record.type);
        PyObject* raw = PyBytes_FromStringAndSize(
            reinterpret_cast<const char*>(record.raw.data()),
            static_cast<Py_ssize_t>(record.raw.size())
        );
        PyObject* values = build_polygon_values(record);
        if (item == nullptr || type == nullptr || raw == nullptr || values == nullptr) {
            Py_XDECREF(item);
            Py_XDECREF(type);
            Py_XDECREF(raw);
            Py_XDECREF(values);
            Py_DECREF(result);
            return nullptr;
        }
        PyTuple_SetItem(item, 0, type);
        PyTuple_SetItem(item, 1, raw);
        PyTuple_SetItem(item, 2, values);
        PyList_SetItem(result, static_cast<Py_ssize_t>(index), item);
    }
    return result;
}

PyObject* mod_bounds_decode_bvh_records(PyObject*, PyObject* args) {
    PyObject* data_object = nullptr;
    PyObject* center_object = nullptr;
    PyObject* quantum_object = nullptr;
    Py_ssize_t start_value = 0;
    Py_ssize_t count_value = 0;
    if (!PyArg_ParseTuple(
            args,
            "OnnOO:bounds_decode_bvh_records",
            &data_object,
            &start_value,
            &count_value,
            &center_object,
            &quantum_object
        )) {
        return nullptr;
    }
    if (start_value < 0 || count_value < 0) {
        PyErr_SetString(PyExc_ValueError, "BVH offset and count must be non-negative");
        return nullptr;
    }
    std::array<double, 3> center{};
    std::array<double, 3> quantum{};
    if (!parse_vector3(center_object, center, "center must contain three numbers") ||
        !parse_vector3(quantum_object, quantum, "quantum must contain three numbers")) {
        return nullptr;
    }
    Buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    const auto start = static_cast<std::size_t>(start_value);
    const auto count = static_cast<std::size_t>(count_value);
    const auto size = static_cast<std::size_t>(buffer.len);
    if (!checked_span(start, count, BVH_RECORD_SIZE, size)) {
        buffer.release();
        PyErr_SetString(PyExc_ValueError, "BVH record array is truncated");
        return nullptr;
    }

    std::vector<BvhRecord> records(count);
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    {
    GilRelease gil_release;
    for (std::size_t index = 0; index < count; ++index) {
        const auto* source = data + start + (index * BVH_RECORD_SIZE);
        auto& record = records[index];
        for (std::size_t axis = 0; axis < 3U; ++axis) {
            record.minimum[axis] = center[axis] + (binary::load<std::int16_t>(source + (axis * 2U)) * quantum[axis]);
            record.maximum[axis] = center[axis] + (binary::load<std::int16_t>(source + 6U + (axis * 2U)) * quantum[axis]);
        }
        record.item_id = binary::load<std::uint16_t>(source + 12U);
        record.item_count = binary::load<std::uint16_t>(source + 14U);
    }
    }
    buffer.release();

    PyObject* result = PyList_New(count_value);
    if (result == nullptr) {
        return nullptr;
    }
    for (std::size_t index = 0; index < count; ++index) {
        const auto& record = records[index];
        PyObject* item = PyTuple_New(4);
        PyObject* minimum = build_vector3(record.minimum);
        PyObject* maximum = build_vector3(record.maximum);
        PyObject* item_id = PyLong_FromUnsignedLong(record.item_id);
        PyObject* item_count = PyLong_FromUnsignedLong(record.item_count);
        if (item == nullptr || minimum == nullptr || maximum == nullptr || item_id == nullptr || item_count == nullptr) {
            Py_XDECREF(item);
            Py_XDECREF(minimum);
            Py_XDECREF(maximum);
            Py_XDECREF(item_id);
            Py_XDECREF(item_count);
            Py_DECREF(result);
            return nullptr;
        }
        PyTuple_SetItem(item, 0, minimum);
        PyTuple_SetItem(item, 1, maximum);
        PyTuple_SetItem(item, 2, item_id);
        PyTuple_SetItem(item, 3, item_count);
        PyList_SetItem(result, static_cast<Py_ssize_t>(index), item);
    }
    return result;
}

PyObject* mod_ynv_decode_edge_list(PyObject*, PyObject* args) {
    PyObject* data_object = nullptr;
    PyObject* adjacent_object = nullptr;
    unsigned long long parts_pointer = 0;
    Py_ssize_t parts_count_value = 0;
    if (!PyArg_ParseTuple(
            args,
            "OKnO:ynv_decode_edge_list",
            &data_object,
            &parts_pointer,
            &parts_count_value,
            &adjacent_object
        )) {
        return nullptr;
    }
    if (parts_count_value < 0) {
        PyErr_SetString(PyExc_ValueError, "YNV list part count must be non-negative");
        return nullptr;
    }
    if (parts_pointer == 0 || parts_count_value == 0) {
        return PyList_New(0);
    }
    PyHandle adjacent_sequence_owner(PySequence_Fast(adjacent_object, "adjacent area IDs must be a sequence"));
    PyObject* adjacent_sequence = adjacent_sequence_owner.get();
    if (adjacent_sequence == nullptr) {
        return nullptr;
    }
    std::vector<std::uint32_t> adjacent_ids;
    const auto adjacent_count = PySequence_Size(adjacent_sequence);
    adjacent_ids.reserve(static_cast<std::size_t>(adjacent_count));
    for (Py_ssize_t index = 0; index < adjacent_count; ++index) {
        PyObject* item = PySequence_GetItem(adjacent_sequence, index);
        const auto value = PyLong_AsUnsignedLong(item);
        Py_XDECREF(item);
        if (PyErr_Occurred() != nullptr) {
            return nullptr;
        }
        adjacent_ids.push_back(static_cast<std::uint32_t>(value));
    }

    Buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    const auto size = static_cast<std::size_t>(buffer.len);
    const auto parts_count = static_cast<std::size_t>(parts_count_value);
    std::size_t parts_offset = 0;
    if (!virtual_offset(parts_pointer, size, parts_offset) ||
        !checked_span(parts_offset, parts_count, YNV_LIST_PART_SIZE, size)) {
        buffer.release();
        PyErr_SetString(PyExc_ValueError, "YNV edge list parts are truncated");
        return nullptr;
    }

    bool valid = true;
    std::vector<YnvEdgeRecord> records;
    {
    GilRelease gil_release;
    for (std::size_t part_index = 0; part_index < parts_count; ++part_index) {
        const auto* part = data + parts_offset + (part_index * YNV_LIST_PART_SIZE);
        const auto items_pointer = binary::load<std::uint64_t>(part);
        const auto item_count = static_cast<std::size_t>(binary::load<std::uint32_t>(part + 8U));
        if (items_pointer == 0 || item_count == 0) {
            continue;
        }
        std::size_t items_offset = 0;
        if (!virtual_offset(items_pointer, size, items_offset) ||
            !checked_span(items_offset, item_count, YNV_EDGE_SIZE, size)) {
            valid = false;
            break;
        }
        const auto original_size = records.size();
        records.resize(original_size + item_count);
        for (std::size_t item_index = 0; item_index < item_count; ++item_index) {
            const auto* edge = data + items_offset + (item_index * YNV_EDGE_SIZE);
            auto& output = records[original_size + item_index].values;
            for (std::size_t half = 0; half < 2U; ++half) {
                const auto value = binary::load<std::uint32_t>(edge + (half * 4U));
                const auto area_index = value & 0x1FU;
                output[half * 4U] = area_index < adjacent_ids.size() ? adjacent_ids[area_index] : 0x3FFFU;
                output[(half * 4U) + 1U] = (value >> 5U) & 0x7FFFU;
                output[(half * 4U) + 2U] = (value >> 20U) & 0x3U;
                output[(half * 4U) + 3U] = (value >> 22U) & 0x3FFU;
            }
        }
    }
    }
    buffer.release();
    if (!valid) {
        PyErr_SetString(PyExc_ValueError, "YNV edge array is truncated");
        return nullptr;
    }

    PyObject* result = PyList_New(static_cast<Py_ssize_t>(records.size()));
    if (result == nullptr) {
        return nullptr;
    }
    for (std::size_t index = 0; index < records.size(); ++index) {
        PyObject* item = PyTuple_New(8);
        if (item == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        for (std::size_t field = 0; field < 8U; ++field) {
            PyTuple_SetItem(item, field, PyLong_FromUnsignedLong(records[index].values[field]));
        }
        PyList_SetItem(result, static_cast<Py_ssize_t>(index), item);
    }
    return result;
}

}  // namespace fivefury_py
