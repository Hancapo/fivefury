#include "drawable/bindings.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <unordered_map>
#include <vector>

namespace fivefury_py {

namespace {

constexpr int SEMANTIC_POSITION = 0;
constexpr int SEMANTIC_BLEND_WEIGHTS = 1;
constexpr int SEMANTIC_BLEND_INDICES = 2;
constexpr int SEMANTIC_NORMAL = 3;
constexpr int SEMANTIC_COLOUR0 = 4;
constexpr int SEMANTIC_COLOUR1 = 5;
constexpr int SEMANTIC_TEXCOORD0 = 6;
constexpr int SEMANTIC_TEXCOORD7 = 13;
constexpr int SEMANTIC_TANGENT = 14;

constexpr int COMPONENT_HALF2 = 1;
constexpr int COMPONENT_FLOAT = 2;
constexpr int COMPONENT_HALF4 = 3;
constexpr int COMPONENT_FLOAT2 = 5;
constexpr int COMPONENT_FLOAT3 = 6;
constexpr int COMPONENT_FLOAT4 = 7;
constexpr int COMPONENT_UBYTE4 = 8;
constexpr int COMPONENT_COLOUR = 9;
constexpr int COMPONENT_RGBA8_SNORM = 10;

struct DecodedComponent {
    std::array<double, 4> values{};
    int count = 0;
    bool integral = false;
};

struct DecodedVertices {
    std::vector<std::array<double, 3>> positions;
    std::vector<std::array<double, 3>> normals;
    std::vector<std::array<double, 4>> tangents;
    std::array<std::vector<std::array<double, 2>>, 8> texcoords;
    int max_texcoord = -1;
    std::vector<std::array<double, 4>> colours0;
    std::vector<std::array<double, 4>> colours1;
    std::vector<std::array<double, 4>> blend_weights;
    std::vector<std::array<std::uint32_t, 4>> blend_indices;
};

struct MeshChunk {
    std::vector<std::uint32_t> vertices;
    std::vector<std::uint32_t> indices;
};

int component_size(int type) {
    switch (type) {
        case COMPONENT_FLOAT:
        case COMPONENT_HALF2:
        case COMPONENT_COLOUR:
        case COMPONENT_UBYTE4:
        case COMPONENT_RGBA8_SNORM: return 4;
        case COMPONENT_FLOAT2:
        case COMPONENT_HALF4: return 8;
        case COMPONENT_FLOAT3: return 12;
        case COMPONENT_FLOAT4: return 16;
        default: return 0;
    }
}

float read_f32(const std::uint8_t* data) {
    std::uint32_t bits = static_cast<std::uint32_t>(data[0]) |
        (static_cast<std::uint32_t>(data[1]) << 8U) |
        (static_cast<std::uint32_t>(data[2]) << 16U) |
        (static_cast<std::uint32_t>(data[3]) << 24U);
    float value = 0.0F;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

float read_f16(const std::uint8_t* data) {
    const auto bits = static_cast<std::uint16_t>(data[0]) |
        static_cast<std::uint16_t>(data[1] << 8U);
    const auto sign = (bits >> 15U) & 1U;
    const auto exponent = (bits >> 10U) & 0x1FU;
    const auto mantissa = bits & 0x3FFU;
    double value = 0.0;
    if (exponent == 0) {
        value = mantissa == 0 ? 0.0 : std::ldexp(static_cast<double>(mantissa), -24);
    } else if (exponent == 0x1FU) {
        value = mantissa == 0
            ? std::numeric_limits<double>::infinity()
            : std::numeric_limits<double>::quiet_NaN();
    } else {
        value = std::ldexp(static_cast<double>(mantissa + 1024U), exponent - 25);
    }
    return static_cast<float>(sign != 0U ? -value : value);
}

DecodedComponent decode_component(const std::uint8_t* data, int type) {
    DecodedComponent result;
    switch (type) {
        case COMPONENT_FLOAT:
            result.count = 1;
            result.values[0] = read_f32(data);
            break;
        case COMPONENT_FLOAT2:
        case COMPONENT_FLOAT3:
        case COMPONENT_FLOAT4:
            result.count = type == COMPONENT_FLOAT2 ? 2 : (type == COMPONENT_FLOAT3 ? 3 : 4);
            for (int index = 0; index < result.count; ++index) {
                result.values[index] = read_f32(data + index * 4);
            }
            break;
        case COMPONENT_HALF2:
        case COMPONENT_HALF4:
            result.count = type == COMPONENT_HALF2 ? 2 : 4;
            for (int index = 0; index < result.count; ++index) {
                result.values[index] = read_f16(data + index * 2);
            }
            break;
        case COMPONENT_COLOUR:
            result.count = 4;
            for (int index = 0; index < 4; ++index) {
                result.values[index] = static_cast<double>(data[index]) / 255.0;
            }
            break;
        case COMPONENT_UBYTE4:
            result.count = 4;
            result.integral = true;
            for (int index = 0; index < 4; ++index) {
                result.values[index] = data[index];
            }
            break;
        case COMPONENT_RGBA8_SNORM:
            result.count = 4;
            for (int index = 0; index < 4; ++index) {
                const auto value = static_cast<std::int8_t>(data[index]);
                result.values[index] = std::max(-1.0, static_cast<double>(value) / 127.0);
            }
            break;
        default:
            break;
    }
    return result;
}

template <std::size_t Size>
PyObject* build_float_tuples(const std::vector<std::array<double, Size>>& values) {
    PyObject* result = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (result == nullptr) {
        return nullptr;
    }
    for (std::size_t row = 0; row < values.size(); ++row) {
        PyObject* tuple = PyTuple_New(Size);
        if (tuple == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        for (std::size_t column = 0; column < Size; ++column) {
            PyTuple_SetItem(tuple, column, PyFloat_FromDouble(values[row][column]));
        }
        PyList_SetItem(result, static_cast<Py_ssize_t>(row), tuple);
    }
    return result;
}

PyObject* build_index_tuples(const std::vector<std::array<std::uint32_t, 4>>& values) {
    PyObject* result = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (result == nullptr) {
        return nullptr;
    }
    for (std::size_t row = 0; row < values.size(); ++row) {
        PyObject* tuple = PyTuple_New(4);
        if (tuple == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        for (std::size_t column = 0; column < 4; ++column) {
            PyTuple_SetItem(tuple, column, PyLong_FromUnsignedLong(values[row][column]));
        }
        PyList_SetItem(result, static_cast<Py_ssize_t>(row), tuple);
    }
    return result;
}

bool dict_set_owned(PyObject* target, const char* name, PyObject* value) {
    if (value == nullptr) {
        return false;
    }
    const auto status = PyDict_SetItemString(target, name, value);
    Py_DECREF(value);
    return status == 0;
}

bool parse_indices(PyObject* object, std::vector<std::uint32_t>& out) {
    PyHandle sequence_owner(PySequence_Fast(object, "mesh indices must be a sequence"));
    PyObject* sequence = sequence_owner.get();
    if (sequence == nullptr) {
        return false;
    }
    const auto count = PySequence_Size(sequence);
    out.reserve(static_cast<std::size_t>(std::max<Py_ssize_t>(count, 0)));
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        const auto value = PyLong_AsUnsignedLong(item);
        Py_XDECREF(item);
        if (PyErr_Occurred() != nullptr) {
            return false;
        }
        out.push_back(static_cast<std::uint32_t>(value));
    }
    return true;
}

}  // namespace

PyObject* mod_ydr_decode_vertex_buffer(PyObject*, PyObject* args) {
    PyObject* data_object = nullptr;
    PyObject* offsets_object = nullptr;
    Py_ssize_t vertex_count = 0;
    int stride = 0;
    unsigned long long flags = 0;
    unsigned long long types = 0;
    if (!PyArg_ParseTuple(
            args,
            "OniKKO",
            &data_object,
            &vertex_count,
            &stride,
            &flags,
            &types,
            &offsets_object
        )) {
        return nullptr;
    }
    if (vertex_count < 0 || stride <= 0) {
        PyErr_SetString(PyExc_ValueError, "vertex count and stride must be positive");
        return nullptr;
    }
    std::array<int, 16> offsets{};
    if (offsets_object != Py_None) {
        PyHandle sequence_owner(PySequence_Fast(offsets_object, "component offsets must be a sequence"));
        PyObject* sequence = sequence_owner.get();
        if (sequence == nullptr) {
            return nullptr;
        }
        if (PySequence_Size(sequence) < 16) {
            PyErr_SetString(PyExc_ValueError, "component offsets must contain 16 values");
            return nullptr;
        }
        for (int index = 0; index < 16; ++index) {
            PyObject* item = PySequence_GetItem(sequence, index);
            offsets[index] = static_cast<int>(PyLong_AsLong(item));
            Py_XDECREF(item);
        }
        if (PyErr_Occurred() != nullptr) {
            return nullptr;
        }
    } else {
        int offset = 0;
        for (int index = 0; index < 16; ++index) {
            offsets[index] = offset;
            if (((flags >> index) & 1UL) != 0UL) {
                offset += component_size(static_cast<int>((types >> (index * 4)) & 0xFULL));
            }
        }
    }
    Buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    const auto available = static_cast<Py_ssize_t>(buffer.len / stride);
    const auto count = std::min(vertex_count, available);
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    const auto data_size = static_cast<std::size_t>(buffer.len);
    DecodedVertices decoded;
    {
    GilRelease gil_release;
    for (Py_ssize_t vertex = 0; vertex < count; ++vertex) {
        const auto base = static_cast<std::size_t>(vertex) * static_cast<std::size_t>(stride);
        for (int semantic = 0; semantic < 16; ++semantic) {
            if (((flags >> semantic) & 1UL) == 0UL) {
                continue;
            }
            const auto type = static_cast<int>((types >> (semantic * 4)) & 0xFULL);
            const auto size = component_size(type);
            const auto source = base + static_cast<std::size_t>(offsets[semantic]);
            if (size <= 0 || source + static_cast<std::size_t>(size) > data_size) {
                continue;
            }
            if (semantic == SEMANTIC_BLEND_INDICES && size == 4) {
                decoded.blend_indices.push_back({
                    data[source + 2], data[source + 1], data[source], data[source + 3]
                });
                continue;
            }
            if (semantic == SEMANTIC_BLEND_WEIGHTS && type == COMPONENT_COLOUR) {
                decoded.blend_weights.push_back({
                    static_cast<double>(data[source + 2]) / 255.0,
                    static_cast<double>(data[source + 1]) / 255.0,
                    static_cast<double>(data[source]) / 255.0,
                    static_cast<double>(data[source + 3]) / 255.0,
                });
                continue;
            }
            const auto value = decode_component(data + source, type);
            if (value.count == 0) {
                continue;
            }
            if (semantic == SEMANTIC_POSITION && value.count >= 3) {
                decoded.positions.push_back({value.values[0], value.values[1], value.values[2]});
            } else if (semantic == SEMANTIC_NORMAL && value.count >= 3) {
                decoded.normals.push_back({value.values[0], value.values[1], value.values[2]});
            } else if (semantic == SEMANTIC_TANGENT && value.count >= 4) {
                decoded.tangents.push_back(value.values);
            } else if (semantic == SEMANTIC_COLOUR0 && value.count >= 4) {
                decoded.colours0.push_back(value.values);
            } else if (semantic == SEMANTIC_COLOUR1 && value.count >= 4) {
                decoded.colours1.push_back(value.values);
            } else if (semantic == SEMANTIC_BLEND_INDICES && value.count >= 4) {
                decoded.blend_indices.push_back({
                    static_cast<std::uint32_t>(value.values[0]),
                    static_cast<std::uint32_t>(value.values[1]),
                    static_cast<std::uint32_t>(value.values[2]),
                    static_cast<std::uint32_t>(value.values[3]),
                });
            } else if (semantic == SEMANTIC_BLEND_WEIGHTS && value.count >= 4) {
                auto weights = value.values;
                if (value.integral) {
                    for (auto& component : weights) {
                        component /= 255.0;
                    }
                }
                decoded.blend_weights.push_back(weights);
            } else if (
                semantic >= SEMANTIC_TEXCOORD0 && semantic <= SEMANTIC_TEXCOORD7 &&
                value.count >= 2
            ) {
                const auto index = semantic - SEMANTIC_TEXCOORD0;
                decoded.max_texcoord = std::max(decoded.max_texcoord, index);
                decoded.texcoords[static_cast<std::size_t>(index)].push_back({
                    value.values[0], value.values[1]
                });
            }
        }
    }
    }
    buffer.release();

    PyObject* result = PyDict_New();
    if (result == nullptr ||
        !dict_set_owned(result, "positions", build_float_tuples(decoded.positions)) ||
        !dict_set_owned(result, "normals", build_float_tuples(decoded.normals)) ||
        !dict_set_owned(result, "tangents", build_float_tuples(decoded.tangents)) ||
        !dict_set_owned(result, "colours0", build_float_tuples(decoded.colours0)) ||
        !dict_set_owned(result, "colours1", build_float_tuples(decoded.colours1)) ||
        !dict_set_owned(result, "blend_weights", build_float_tuples(decoded.blend_weights)) ||
        !dict_set_owned(result, "blend_indices", build_index_tuples(decoded.blend_indices))) {
        Py_XDECREF(result);
        return nullptr;
    }
    PyObject* texcoords = PyList_New(std::max(decoded.max_texcoord + 1, 0));
    if (texcoords == nullptr) {
        Py_DECREF(result);
        return nullptr;
    }
    for (int index = 0; index <= decoded.max_texcoord; ++index) {
        PyList_SetItem(texcoords, index, build_float_tuples(decoded.texcoords[index]));
    }
    if (!dict_set_owned(result, "texcoords", texcoords)) {
        Py_DECREF(result);
        return nullptr;
    }
    return result;
}

PyObject* mod_ydr_split_mesh_indices(PyObject*, PyObject* args) {
    PyObject* indices_object = nullptr;
    Py_ssize_t vertex_count = 0;
    Py_ssize_t max_vertices = 0;
    if (!PyArg_ParseTuple(args, "Onn", &indices_object, &vertex_count, &max_vertices)) {
        return nullptr;
    }
    if (vertex_count < 0 || max_vertices <= 0) {
        PyErr_SetString(PyExc_ValueError, "mesh vertex limits must be positive");
        return nullptr;
    }
    std::vector<std::uint32_t> indices;
    if (!parse_indices(indices_object, indices)) {
        return nullptr;
    }
    if (indices.size() % 3U != 0U) {
        PyErr_SetString(PyExc_ValueError, "YDR writer currently requires triangle list indices");
        return nullptr;
    }
    std::vector<MeshChunk> chunks;
    bool needs_split = false;
    {
    GilRelease gil_release;
    std::unordered_map<std::uint32_t, std::uint32_t> lookup;
    MeshChunk current;
    for (std::size_t base = 0; base < indices.size(); base += 3U) {
        std::size_t new_vertices = 0;
        for (std::size_t offset = 0; offset < 3U; ++offset) {
            const auto index = indices[base + offset];
            if (index >= static_cast<std::uint32_t>(vertex_count)) {
                needs_split = true;
                continue;
            }
            if (!lookup.contains(index)) {
                ++new_vertices;
            }
        }
        if (!current.indices.empty() && current.vertices.size() + new_vertices > static_cast<std::size_t>(max_vertices)) {
            chunks.push_back(std::move(current));
            current = MeshChunk{};
            lookup.clear();
            needs_split = true;
        }
        for (std::size_t offset = 0; offset < 3U; ++offset) {
            const auto index = indices[base + offset];
            auto [iterator, inserted] = lookup.try_emplace(
                index,
                static_cast<std::uint32_t>(current.vertices.size())
            );
            if (inserted) {
                current.vertices.push_back(index);
            }
            current.indices.push_back(iterator->second);
            if (index > 0xFFFFU) {
                needs_split = true;
            }
        }
    }
    if (!current.indices.empty()) {
        chunks.push_back(std::move(current));
    }
    if (chunks.size() > 1U) {
        needs_split = true;
    }
    }
    if (std::any_of(indices.begin(), indices.end(), [vertex_count](auto value) {
            return value >= static_cast<std::uint32_t>(vertex_count);
        })) {
        PyErr_SetString(PyExc_ValueError, "Mesh indices reference a vertex outside positions");
        return nullptr;
    }
    if (!needs_split) {
        Py_RETURN_NONE;
    }
    PyObject* result = PyList_New(static_cast<Py_ssize_t>(chunks.size()));
    if (result == nullptr) {
        return nullptr;
    }
    for (std::size_t chunk_index = 0; chunk_index < chunks.size(); ++chunk_index) {
        const auto& chunk = chunks[chunk_index];
        PyObject* vertices = PyList_New(static_cast<Py_ssize_t>(chunk.vertices.size()));
        PyObject* remapped = PyList_New(static_cast<Py_ssize_t>(chunk.indices.size()));
        PyObject* pair = PyTuple_New(2);
        if (vertices == nullptr || remapped == nullptr || pair == nullptr) {
            Py_XDECREF(vertices);
            Py_XDECREF(remapped);
            Py_XDECREF(pair);
            Py_DECREF(result);
            return nullptr;
        }
        for (std::size_t index = 0; index < chunk.vertices.size(); ++index) {
            PyList_SetItem(vertices, index, PyLong_FromUnsignedLong(chunk.vertices[index]));
        }
        for (std::size_t index = 0; index < chunk.indices.size(); ++index) {
            PyList_SetItem(remapped, index, PyLong_FromUnsignedLong(chunk.indices[index]));
        }
        PyTuple_SetItem(pair, 0, vertices);
        PyTuple_SetItem(pair, 1, remapped);
        PyList_SetItem(result, static_cast<Py_ssize_t>(chunk_index), pair);
    }
    return result;
}

}  // namespace fivefury_py
