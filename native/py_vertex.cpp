#include "py_bindings.h"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace fivefury_py {

namespace {

// Mirrors fivefury.ydr.defs.VertexSemantic.
constexpr int SEMANTIC_POSITION = 0;
constexpr int SEMANTIC_BLEND_WEIGHTS = 1;
constexpr int SEMANTIC_BLEND_INDICES = 2;
constexpr int SEMANTIC_NORMAL = 3;
constexpr int SEMANTIC_COLOUR0 = 4;
constexpr int SEMANTIC_COLOUR1 = 5;
constexpr int SEMANTIC_TEXCOORD0 = 6;
constexpr int SEMANTIC_TEXCOORD7 = 13;
constexpr int SEMANTIC_TANGENT = 14;

// Mirrors fivefury.ydr.defs.VertexComponentType.
constexpr int COMPONENT_NOTHING = 0;
constexpr int COMPONENT_HALF2 = 1;
constexpr int COMPONENT_FLOAT = 2;
constexpr int COMPONENT_HALF4 = 3;
constexpr int COMPONENT_FLOAT2 = 5;
constexpr int COMPONENT_FLOAT3 = 6;
constexpr int COMPONENT_FLOAT4 = 7;
constexpr int COMPONENT_UBYTE4 = 8;
constexpr int COMPONENT_COLOUR = 9;
constexpr int COMPONENT_RGBA8_SNORM = 10;

enum class Encoding {
    Nothing,
    Float1,
    Float2,
    Float3,
    Float4,
    Half2,
    Half4,
    Colour,
    Ubyte4,
    Snorm4,
    SkinWeightsColour,  // BLEND_WEIGHTS as COLOUR: clamp-bytes in (2, 1, 0, 3) order
    SkinIndices,        // BLEND_INDICES as COLOUR/UBYTE4/SNORM: raw bytes in (2, 1, 0, 3) order
};

struct SemanticSpec {
    int semantic = 0;
    Encoding encoding = Encoding::Nothing;
    std::size_t arity = 0;
    std::size_t byte_size = 0;
    std::vector<double> values;
};

// Port of CPython's PyFloat_Pack2 so half floats stay byte-identical to struct.pack("<e", ...).
std::uint16_t pack_half(double x) {
    int sign;
    int e;
    double f;
    std::uint16_t bits;

    if (x == 0.0) {
        sign = std::signbit(x) ? 1 : 0;
        e = 0;
        bits = 0;
    } else if (std::isinf(x)) {
        sign = x < 0.0 ? 1 : 0;
        e = 0x1F;
        bits = 0;
    } else if (std::isnan(x)) {
        sign = 0;
        e = 0x1F;
        bits = 512;
    } else {
        sign = x < 0.0 ? 1 : 0;
        if (sign) {
            x = -x;
        }
        f = std::frexp(x, &e);
        f *= 2.0;
        e -= 1;
        if (e >= 16) {
            throw std::overflow_error("float too large to pack with e format");
        }
        if (e < -25) {
            f = 0.0;
            e = 0;
        } else if (e < -14) {
            f = std::ldexp(f, 14 + e);
            e = 0;
        } else {
            e += 15;
            f -= 1.0;
        }
        f *= 1024.0;
        bits = static_cast<std::uint16_t>(f);
        if ((f - bits > 0.5) || ((f - bits == 0.5) && (bits % 2 == 1))) {
            ++bits;
            if (bits == 1024) {
                bits = 0;
                ++e;
                if (e == 31) {
                    throw std::overflow_error("float too large to pack with e format");
                }
            }
        }
    }
    return static_cast<std::uint16_t>((sign << 15) | (e << 10) | bits);
}

void append_u16(std::string& out, std::uint16_t value) {
    out.push_back(static_cast<char>(value & 0xFFU));
    out.push_back(static_cast<char>((value >> 8U) & 0xFFU));
}

void append_f32(std::string& out, double value) {
    const auto narrowed = static_cast<float>(value);
    if (std::isinf(narrowed) && std::isfinite(value)) {
        throw std::overflow_error("float too large to pack with f format");
    }
    std::uint32_t bits;
    std::memcpy(&bits, &narrowed, sizeof(bits));
    out.push_back(static_cast<char>(bits & 0xFFU));
    out.push_back(static_cast<char>((bits >> 8U) & 0xFFU));
    out.push_back(static_cast<char>((bits >> 16U) & 0xFFU));
    out.push_back(static_cast<char>((bits >> 24U) & 0xFFU));
}

// max(0, min(255, int(round(value * 255.0)))) with banker's rounding, like the Python encoder.
unsigned char clamp_unsigned_byte(double value) {
    const double scaled = std::nearbyint(value * 255.0);
    if (!(scaled > 0.0)) {
        return 0;
    }
    if (scaled >= 255.0) {
        return 255;
    }
    return static_cast<unsigned char>(scaled);
}

// max(-127, min(127, int(round(value * 127.0)))).
signed char clamp_signed_byte(double value) {
    const double scaled = std::nearbyint(value * 127.0);
    if (!(scaled > -127.0)) {
        return -127;
    }
    if (scaled >= 127.0) {
        return 127;
    }
    return static_cast<signed char>(scaled);
}

// int(value) & 0xFF: truncation toward zero, then masked.
unsigned char truncated_byte(double value) {
    if (!std::isfinite(value)) {
        return 0;
    }
    return static_cast<unsigned char>(static_cast<std::int64_t>(std::trunc(value)) & 0xFF);
}

Encoding resolve_encoding(int semantic, int component_type) {
    if (semantic == SEMANTIC_BLEND_WEIGHTS && component_type == COMPONENT_COLOUR) {
        return Encoding::SkinWeightsColour;
    }
    if (semantic == SEMANTIC_BLEND_INDICES &&
        (component_type == COMPONENT_COLOUR || component_type == COMPONENT_UBYTE4 || component_type == COMPONENT_RGBA8_SNORM)) {
        return Encoding::SkinIndices;
    }
    switch (component_type) {
        case COMPONENT_NOTHING: return Encoding::Nothing;
        case COMPONENT_FLOAT: return Encoding::Float1;
        case COMPONENT_FLOAT2: return Encoding::Float2;
        case COMPONENT_FLOAT3: return Encoding::Float3;
        case COMPONENT_FLOAT4: return Encoding::Float4;
        case COMPONENT_HALF2: return Encoding::Half2;
        case COMPONENT_HALF4: return Encoding::Half4;
        case COMPONENT_COLOUR: return Encoding::Colour;
        case COMPONENT_UBYTE4: return Encoding::Ubyte4;
        case COMPONENT_RGBA8_SNORM: return Encoding::Snorm4;
        default:
            throw std::invalid_argument("Unsupported vertex component type");
    }
}

std::size_t encoding_arity(Encoding encoding) {
    switch (encoding) {
        case Encoding::Nothing: return 0;
        case Encoding::Float1: return 1;
        case Encoding::Float2:
        case Encoding::Half2: return 2;
        case Encoding::Float3: return 3;
        default: return 4;
    }
}

std::size_t encoding_byte_size(Encoding encoding) {
    switch (encoding) {
        case Encoding::Nothing: return 0;
        case Encoding::Float1:
        case Encoding::Half2:
        case Encoding::Colour:
        case Encoding::Ubyte4:
        case Encoding::Snorm4:
        case Encoding::SkinWeightsColour:
        case Encoding::SkinIndices: return 4;
        case Encoding::Float2:
        case Encoding::Half4: return 8;
        case Encoding::Float3: return 12;
        case Encoding::Float4: return 16;
    }
    return 0;
}

bool flatten_channel(
    PyObject* channel,
    std::size_t vertex_count,
    std::size_t arity,
    const char* channel_name,
    std::vector<double>& out
) {
    if (arity == 0) {
        return true;
    }
    PyObject* sequence = PySequence_Fast(channel, "vertex channel must be a sequence");
    if (sequence == nullptr) {
        return false;
    }
    if (static_cast<std::size_t>(PySequence_Size(sequence)) < vertex_count) {
        Py_DECREF(sequence);
        PyErr_Format(PyExc_ValueError, "vertex channel '%s' is shorter than the vertex count", channel_name);
        return false;
    }
    out.resize(vertex_count * arity);
    for (std::size_t vertex_index = 0; vertex_index < vertex_count; ++vertex_index) {
        PyObject* item = PySequence_GetItem(sequence, static_cast<Py_ssize_t>(vertex_index));
        if (item == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        PyObject* value = PySequence_Fast(item, "vertex value must be a sequence");
        Py_DECREF(item);
        if (value == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        if (static_cast<std::size_t>(PySequence_Size(value)) < arity) {
            Py_DECREF(value);
            Py_DECREF(sequence);
            PyErr_Format(PyExc_ValueError, "vertex value in channel '%s' has too few components", channel_name);
            return false;
        }
        for (std::size_t component = 0; component < arity; ++component) {
            PyObject* component_object = PySequence_GetItem(value, static_cast<Py_ssize_t>(component));
            if (component_object == nullptr) {
                Py_DECREF(value);
                Py_DECREF(sequence);
                return false;
            }
            const double component_value = PyFloat_AsDouble(component_object);
            Py_DECREF(component_object);
            if (component_value == -1.0 && PyErr_Occurred() != nullptr) {
                Py_DECREF(value);
                Py_DECREF(sequence);
                return false;
            }
            out[(vertex_index * arity) + component] = component_value;
        }
        Py_DECREF(value);
    }
    Py_DECREF(sequence);
    return true;
}

std::string pack_buffer(const std::vector<SemanticSpec>& specs, std::size_t vertex_count) {
    std::size_t stride = 0;
    for (const auto& spec : specs) {
        stride += spec.byte_size;
    }
    std::string out;
    out.reserve(stride * vertex_count);

    for (std::size_t vertex_index = 0; vertex_index < vertex_count; ++vertex_index) {
        for (const auto& spec : specs) {
            const double* values = spec.values.data() + (vertex_index * spec.arity);
            switch (spec.encoding) {
                case Encoding::Nothing:
                    break;
                case Encoding::Float1:
                    append_f32(out, values[0]);
                    break;
                case Encoding::Float2:
                    append_f32(out, values[0]);
                    append_f32(out, values[1]);
                    break;
                case Encoding::Float3:
                    append_f32(out, values[0]);
                    append_f32(out, values[1]);
                    append_f32(out, values[2]);
                    break;
                case Encoding::Float4:
                    append_f32(out, values[0]);
                    append_f32(out, values[1]);
                    append_f32(out, values[2]);
                    append_f32(out, values[3]);
                    break;
                case Encoding::Half2:
                    append_u16(out, pack_half(values[0]));
                    append_u16(out, pack_half(values[1]));
                    break;
                case Encoding::Half4:
                    append_u16(out, pack_half(values[0]));
                    append_u16(out, pack_half(values[1]));
                    append_u16(out, pack_half(values[2]));
                    append_u16(out, pack_half(values[3]));
                    break;
                case Encoding::Colour:
                    out.push_back(static_cast<char>(clamp_unsigned_byte(values[0])));
                    out.push_back(static_cast<char>(clamp_unsigned_byte(values[1])));
                    out.push_back(static_cast<char>(clamp_unsigned_byte(values[2])));
                    out.push_back(static_cast<char>(clamp_unsigned_byte(values[3])));
                    break;
                case Encoding::Ubyte4:
                    out.push_back(static_cast<char>(truncated_byte(values[0])));
                    out.push_back(static_cast<char>(truncated_byte(values[1])));
                    out.push_back(static_cast<char>(truncated_byte(values[2])));
                    out.push_back(static_cast<char>(truncated_byte(values[3])));
                    break;
                case Encoding::Snorm4:
                    out.push_back(static_cast<char>(clamp_signed_byte(values[0])));
                    out.push_back(static_cast<char>(clamp_signed_byte(values[1])));
                    out.push_back(static_cast<char>(clamp_signed_byte(values[2])));
                    out.push_back(static_cast<char>(clamp_signed_byte(values[3])));
                    break;
                case Encoding::SkinWeightsColour:
                    out.push_back(static_cast<char>(clamp_unsigned_byte(values[2])));
                    out.push_back(static_cast<char>(clamp_unsigned_byte(values[1])));
                    out.push_back(static_cast<char>(clamp_unsigned_byte(values[0])));
                    out.push_back(static_cast<char>(clamp_unsigned_byte(values[3])));
                    break;
                case Encoding::SkinIndices:
                    out.push_back(static_cast<char>(truncated_byte(values[2])));
                    out.push_back(static_cast<char>(truncated_byte(values[1])));
                    out.push_back(static_cast<char>(truncated_byte(values[0])));
                    out.push_back(static_cast<char>(truncated_byte(values[3])));
                    break;
            }
        }
    }
    return out;
}

}  // namespace

PyObject* mod_ydr_pack_vertex_buffer(PyObject*, PyObject* args) {
    PyObject* semantics_object = nullptr;
    PyObject* positions_object = nullptr;
    PyObject* normals_object = nullptr;
    PyObject* texcoords_object = nullptr;
    PyObject* tangents_object = nullptr;
    PyObject* colours0_object = nullptr;
    PyObject* colours1_object = nullptr;
    PyObject* blend_weights_object = Py_None;
    PyObject* blend_indices_object = Py_None;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOOO|OO:ydr_pack_vertex_buffer",
            &semantics_object,
            &positions_object,
            &normals_object,
            &texcoords_object,
            &tangents_object,
            &colours0_object,
            &colours1_object,
            &blend_weights_object,
            &blend_indices_object
        )) {
        return nullptr;
    }

    const auto vertex_count_signed = PySequence_Size(positions_object);
    if (vertex_count_signed < 0) {
        return nullptr;
    }
    const auto vertex_count = static_cast<std::size_t>(vertex_count_signed);

    PyObject* semantics_sequence = PySequence_Fast(semantics_object, "semantics must be a sequence");
    if (semantics_sequence == nullptr) {
        return nullptr;
    }
    const auto semantic_count = PySequence_Size(semantics_sequence);
    if (semantic_count < 0) {
        Py_DECREF(semantics_sequence);
        return nullptr;
    }

    std::vector<SemanticSpec> specs;
    specs.reserve(static_cast<std::size_t>(semantic_count));
    bool ok = true;
    for (Py_ssize_t index = 0; ok && index < semantic_count; ++index) {
        PyObject* pair = PySequence_GetItem(semantics_sequence, index);
        if (pair == nullptr) {
            ok = false;
            break;
        }
        PyObject* pair_sequence = PySequence_Fast(pair, "semantic entry must be a (semantic, component_type) pair");
        Py_DECREF(pair);
        if (pair_sequence == nullptr) {
            ok = false;
            break;
        }
        if (PySequence_Size(pair_sequence) != 2) {
            Py_DECREF(pair_sequence);
            PyErr_SetString(PyExc_ValueError, "semantic entry must contain exactly 2 values");
            ok = false;
            break;
        }
        PyObject* semantic_object = PySequence_GetItem(pair_sequence, 0);
        PyObject* component_object = PySequence_GetItem(pair_sequence, 1);
        Py_DECREF(pair_sequence);
        if (semantic_object == nullptr || component_object == nullptr) {
            Py_XDECREF(semantic_object);
            Py_XDECREF(component_object);
            ok = false;
            break;
        }
        const auto semantic = static_cast<int>(PyLong_AsLong(semantic_object));
        const auto component_type = static_cast<int>(PyLong_AsLong(component_object));
        Py_DECREF(semantic_object);
        Py_DECREF(component_object);
        if (PyErr_Occurred() != nullptr) {
            ok = false;
            break;
        }

        SemanticSpec spec;
        spec.semantic = semantic;
        try {
            spec.encoding = resolve_encoding(semantic, component_type);
        } catch (...) {
            Py_DECREF(semantics_sequence);
            return translate_cpp_exception();
        }
        spec.arity = encoding_arity(spec.encoding);
        spec.byte_size = encoding_byte_size(spec.encoding);

        PyObject* channel = nullptr;
        PyObject* borrowed_texcoord = nullptr;
        const char* channel_name = "unknown";
        if (semantic == SEMANTIC_POSITION) {
            channel = positions_object;
            channel_name = "positions";
        } else if (semantic == SEMANTIC_BLEND_WEIGHTS) {
            channel = blend_weights_object;
            channel_name = "blend_weights";
        } else if (semantic == SEMANTIC_BLEND_INDICES) {
            channel = blend_indices_object;
            channel_name = "blend_indices";
        } else if (semantic == SEMANTIC_NORMAL) {
            channel = normals_object;
            channel_name = "normals";
        } else if (semantic == SEMANTIC_COLOUR0) {
            channel = colours0_object;
            channel_name = "colours0";
        } else if (semantic == SEMANTIC_COLOUR1) {
            channel = colours1_object;
            channel_name = "colours1";
        } else if (semantic >= SEMANTIC_TEXCOORD0 && semantic <= SEMANTIC_TEXCOORD7) {
            borrowed_texcoord = PySequence_GetItem(texcoords_object, semantic - SEMANTIC_TEXCOORD0);
            if (borrowed_texcoord == nullptr) {
                ok = false;
                break;
            }
            channel = borrowed_texcoord;
            channel_name = "texcoords";
        } else if (semantic == SEMANTIC_TANGENT) {
            channel = tangents_object;
            channel_name = "tangents";
        } else {
            PyErr_Format(PyExc_ValueError, "Unsupported vertex semantic: %d", semantic);
            ok = false;
            break;
        }
        if (channel == Py_None) {
            Py_XDECREF(borrowed_texcoord);
            PyErr_Format(PyExc_ValueError, "vertex channel '%s' is required by the layout but missing", channel_name);
            ok = false;
            break;
        }
        ok = flatten_channel(channel, vertex_count, spec.arity, channel_name, spec.values);
        Py_XDECREF(borrowed_texcoord);
        if (!ok) {
            break;
        }
        specs.push_back(std::move(spec));
    }
    Py_DECREF(semantics_sequence);
    if (!ok) {
        return nullptr;
    }

    try {
        const auto buffer = pack_buffer(specs, vertex_count);
        return PyBytes_FromStringAndSize(buffer.data(), static_cast<Py_ssize_t>(buffer.size()));
    } catch (...) {
        return translate_cpp_exception();
    }
}

}  // namespace fivefury_py
