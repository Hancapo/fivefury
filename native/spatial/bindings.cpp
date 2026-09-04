#include "spatial/bindings.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <limits>
#include <vector>

namespace fivefury_py {

namespace {

constexpr std::uint64_t VIRTUAL_BASE = 0x50000000ULL;
constexpr std::size_t POLYGON_SIZE = 16U;
constexpr std::size_t BVH_RECORD_SIZE = 16U;
constexpr std::size_t YNV_LIST_PART_SIZE = 16U;
constexpr std::size_t YNV_EDGE_SIZE = 8U;

std::uint16_t read_u16(const std::uint8_t* data) {
    return static_cast<std::uint16_t>(data[0]) |
        (static_cast<std::uint16_t>(data[1]) << 8U);
}

std::int16_t read_i16(const std::uint8_t* data) {
    return static_cast<std::int16_t>(read_u16(data));
}

std::uint32_t read_u32(const std::uint8_t* data) {
    return static_cast<std::uint32_t>(data[0]) |
        (static_cast<std::uint32_t>(data[1]) << 8U) |
        (static_cast<std::uint32_t>(data[2]) << 16U) |
        (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t read_u64(const std::uint8_t* data) {
    return static_cast<std::uint64_t>(read_u32(data)) |
        (static_cast<std::uint64_t>(read_u32(data + 4U)) << 32U);
}

float read_f32(const std::uint8_t* data) {
    const auto bits = read_u32(data);
    float value = 0.0F;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

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
    PyObject* sequence = PySequence_Fast(object, message);
    if (sequence == nullptr) {
        return false;
    }
    if (PySequence_Size(sequence) < 3) {
        Py_DECREF(sequence);
        PyErr_SetString(PyExc_ValueError, message);
        return false;
    }
    for (std::size_t index = 0; index < 3U; ++index) {
        PyObject* item = PySequence_GetItem(sequence, static_cast<Py_ssize_t>(index));
        result[index] = PyFloat_AsDouble(item);
        Py_XDECREF(item);
        if (PyErr_Occurred() != nullptr) {
            Py_DECREF(sequence);
            return false;
        }
    }
    Py_DECREF(sequence);
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
    Py_buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    const auto start = static_cast<std::size_t>(start_value);
    const auto count = static_cast<std::size_t>(count_value);
    const auto size = static_cast<std::size_t>(buffer.len);
    if (!checked_span(start, count, POLYGON_SIZE, size)) {
        PyBuffer_Release(&buffer);
        PyErr_SetString(PyExc_ValueError, "polygon array is truncated");
        return nullptr;
    }

    std::vector<PolygonRecord> records(count);
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    Py_BEGIN_ALLOW_THREADS
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
                record.scalar = read_f32(decoded);
                for (std::size_t field = 0; field < 6U; ++field) {
                    record.values[field] = read_u16(decoded + 4U + (field * 2U));
                }
                break;
            case 1:
                record.values[0] = read_u16(decoded);
                record.values[1] = read_u16(decoded + 2U);
                record.scalar = read_f32(decoded + 4U);
                record.values[2] = read_u32(decoded + 8U);
                record.values[3] = read_u32(decoded + 12U);
                break;
            case 2:
            case 4:
                record.values[0] = read_u16(decoded);
                record.values[1] = read_u16(decoded + 2U);
                record.scalar = read_f32(decoded + 4U);
                record.values[2] = read_u16(decoded + 8U);
                record.values[3] = read_u16(decoded + 10U);
                record.values[4] = read_u32(decoded + 12U);
                break;
            case 3:
                record.values[0] = read_u32(decoded);
                for (std::size_t field = 0; field < 4U; ++field) {
                    record.values[field + 1U] = read_i16(decoded + 4U + (field * 2U));
                }
                record.values[5] = read_u32(decoded + 12U);
                break;
            default:
                break;
        }
    }
    Py_END_ALLOW_THREADS
    PyBuffer_Release(&buffer);

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
    Py_buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    const auto start = static_cast<std::size_t>(start_value);
    const auto count = static_cast<std::size_t>(count_value);
    const auto size = static_cast<std::size_t>(buffer.len);
    if (!checked_span(start, count, BVH_RECORD_SIZE, size)) {
        PyBuffer_Release(&buffer);
        PyErr_SetString(PyExc_ValueError, "BVH record array is truncated");
        return nullptr;
    }

    std::vector<BvhRecord> records(count);
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    Py_BEGIN_ALLOW_THREADS
    for (std::size_t index = 0; index < count; ++index) {
        const auto* source = data + start + (index * BVH_RECORD_SIZE);
        auto& record = records[index];
        for (std::size_t axis = 0; axis < 3U; ++axis) {
            record.minimum[axis] = center[axis] + (read_i16(source + (axis * 2U)) * quantum[axis]);
            record.maximum[axis] = center[axis] + (read_i16(source + 6U + (axis * 2U)) * quantum[axis]);
        }
        record.item_id = read_u16(source + 12U);
        record.item_count = read_u16(source + 14U);
    }
    Py_END_ALLOW_THREADS
    PyBuffer_Release(&buffer);

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
    PyObject* adjacent_sequence = PySequence_Fast(adjacent_object, "adjacent area IDs must be a sequence");
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
            Py_DECREF(adjacent_sequence);
            return nullptr;
        }
        adjacent_ids.push_back(static_cast<std::uint32_t>(value));
    }
    Py_DECREF(adjacent_sequence);

    Py_buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    const auto size = static_cast<std::size_t>(buffer.len);
    const auto parts_count = static_cast<std::size_t>(parts_count_value);
    std::size_t parts_offset = 0;
    if (!virtual_offset(parts_pointer, size, parts_offset) ||
        !checked_span(parts_offset, parts_count, YNV_LIST_PART_SIZE, size)) {
        PyBuffer_Release(&buffer);
        PyErr_SetString(PyExc_ValueError, "YNV edge list parts are truncated");
        return nullptr;
    }

    bool valid = true;
    std::vector<YnvEdgeRecord> records;
    Py_BEGIN_ALLOW_THREADS
    for (std::size_t part_index = 0; part_index < parts_count; ++part_index) {
        const auto* part = data + parts_offset + (part_index * YNV_LIST_PART_SIZE);
        const auto items_pointer = read_u64(part);
        const auto item_count = static_cast<std::size_t>(read_u32(part + 8U));
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
                const auto value = read_u32(edge + (half * 4U));
                const auto area_index = value & 0x1FU;
                output[half * 4U] = area_index < adjacent_ids.size() ? adjacent_ids[area_index] : 0x3FFFU;
                output[(half * 4U) + 1U] = (value >> 5U) & 0x7FFFU;
                output[(half * 4U) + 2U] = (value >> 20U) & 0x3U;
                output[(half * 4U) + 3U] = (value >> 22U) & 0x3FFU;
            }
        }
    }
    Py_END_ALLOW_THREADS
    PyBuffer_Release(&buffer);
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
