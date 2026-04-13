#include "py_bindings.h"

#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace {

struct Vec3 {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;

    bool operator==(const Vec3& other) const noexcept {
        return x == other.x && y == other.y && z == other.z;
    }
};

struct Triangle {
    Vec3 vertex0;
    Vec3 vertex1;
    Vec3 vertex2;
};

struct TriangleChunk {
    std::vector<Vec3> vertices;
    std::vector<std::array<std::uint32_t, 3>> triangles;
};

double canonical_zero(double value) noexcept {
    return value == 0.0 ? 0.0 : value;
}

std::uint64_t hashable_double(double value) noexcept {
    value = canonical_zero(value);
    std::uint64_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

struct Vec3Hash {
    std::size_t operator()(const Vec3& value) const noexcept {
        const auto hx = static_cast<std::size_t>(hashable_double(value.x));
        const auto hy = static_cast<std::size_t>(hashable_double(value.y));
        const auto hz = static_cast<std::size_t>(hashable_double(value.z));
        return hx ^ (hy + 0x9E3779B97F4A7C15ULL + (hx << 6U) + (hx >> 2U)) ^
               (hz + 0x9E3779B97F4A7C15ULL + (hy << 6U) + (hy >> 2U));
    }
};

double triangle_area_impl(const Vec3& vertex0, const Vec3& vertex1, const Vec3& vertex2) noexcept {
    const double edge1x = vertex1.x - vertex0.x;
    const double edge1y = vertex1.y - vertex0.y;
    const double edge1z = vertex1.z - vertex0.z;
    const double edge2x = vertex2.x - vertex0.x;
    const double edge2y = vertex2.y - vertex0.y;
    const double edge2z = vertex2.z - vertex0.z;
    const double crossx = (edge1y * edge2z) - (edge1z * edge2y);
    const double crossy = (edge1z * edge2x) - (edge1x * edge2z);
    const double crossz = (edge1x * edge2y) - (edge1y * edge2x);
    return 0.5 * std::sqrt((crossx * crossx) + (crossy * crossy) + (crossz * crossz));
}

std::pair<Vec3, Vec3> bounds_from_vertices_impl(const std::vector<Vec3>& vertices) {
    if (vertices.empty()) {
        throw std::invalid_argument("At least one vertex is required");
    }
    Vec3 minimum = vertices.front();
    Vec3 maximum = vertices.front();
    for (std::size_t index = 1; index < vertices.size(); ++index) {
        const auto& vertex = vertices[index];
        minimum.x = std::min(minimum.x, vertex.x);
        minimum.y = std::min(minimum.y, vertex.y);
        minimum.z = std::min(minimum.z, vertex.z);
        maximum.x = std::max(maximum.x, vertex.x);
        maximum.y = std::max(maximum.y, vertex.y);
        maximum.z = std::max(maximum.z, vertex.z);
    }
    return {minimum, maximum};
}

double sphere_radius_from_vertices_impl(const Vec3& center, const std::vector<Vec3>& vertices) noexcept {
    double max_distance_squared = 0.0;
    for (const auto& vertex : vertices) {
        const double dx = vertex.x - center.x;
        const double dy = vertex.y - center.y;
        const double dz = vertex.z - center.z;
        const double distance_squared = (dx * dx) + (dy * dy) + (dz * dz);
        if (distance_squared > max_distance_squared) {
            max_distance_squared = distance_squared;
        }
    }
    return std::sqrt(max_distance_squared);
}

std::vector<TriangleChunk> chunk_bound_triangles_impl(
    const std::vector<Triangle>& triangles,
    std::size_t max_vertices_per_child,
    std::size_t max_triangles_per_child
) {
    std::vector<TriangleChunk> chunks;
    TriangleChunk current_chunk;
    std::unordered_map<Vec3, std::uint32_t, Vec3Hash> vertex_lookup;

    auto flush = [&]() {
        if (!current_chunk.triangles.empty()) {
            chunks.push_back(std::move(current_chunk));
            current_chunk = TriangleChunk{};
        }
        vertex_lookup.clear();
    };

    for (const auto& triangle : triangles) {
        if (!current_chunk.triangles.empty() &&
            ((current_chunk.triangles.size() + 1U) > max_triangles_per_child ||
             (current_chunk.vertices.size() + 3U) > max_vertices_per_child)) {
            flush();
        }

        std::array<std::uint32_t, 3> indices{};
        const Vec3 vertices[3] = {triangle.vertex0, triangle.vertex1, triangle.vertex2};
        for (std::size_t index = 0; index < 3U; ++index) {
            const auto lookup = vertex_lookup.find(vertices[index]);
            if (lookup != vertex_lookup.end()) {
                indices[index] = lookup->second;
                continue;
            }
            if (current_chunk.vertices.size() > std::numeric_limits<std::uint32_t>::max()) {
                throw std::overflow_error("too many bound vertices");
            }
            const auto vertex_index = static_cast<std::uint32_t>(current_chunk.vertices.size());
            current_chunk.vertices.push_back(vertices[index]);
            vertex_lookup.emplace(vertices[index], vertex_index);
            indices[index] = vertex_index;
        }
        current_chunk.triangles.push_back(indices);
    }

    flush();
    return chunks;
}

bool parse_vector3(PyObject* object, Vec3& out, const char* argument_name) {
    PyObject* sequence = PySequence_Fast(object, argument_name);
    if (sequence == nullptr) {
        return false;
    }
    if (PySequence_Size(sequence) != 3) {
        Py_DECREF(sequence);
        PyErr_Format(PyExc_ValueError, "%s must contain exactly 3 values", argument_name);
        return false;
    }
    PyObject* x_item = PySequence_GetItem(sequence, 0);
    PyObject* y_item = PySequence_GetItem(sequence, 1);
    PyObject* z_item = PySequence_GetItem(sequence, 2);
    if (x_item == nullptr || y_item == nullptr || z_item == nullptr) {
        Py_XDECREF(x_item);
        Py_XDECREF(y_item);
        Py_XDECREF(z_item);
        Py_DECREF(sequence);
        return false;
    }
    out.x = canonical_zero(PyFloat_AsDouble(x_item));
    if (PyErr_Occurred() != nullptr) {
        Py_DECREF(x_item);
        Py_DECREF(y_item);
        Py_DECREF(z_item);
        Py_DECREF(sequence);
        return false;
    }
    out.y = canonical_zero(PyFloat_AsDouble(y_item));
    if (PyErr_Occurred() != nullptr) {
        Py_DECREF(x_item);
        Py_DECREF(y_item);
        Py_DECREF(z_item);
        Py_DECREF(sequence);
        return false;
    }
    out.z = canonical_zero(PyFloat_AsDouble(z_item));
    if (PyErr_Occurred() != nullptr) {
        Py_DECREF(x_item);
        Py_DECREF(y_item);
        Py_DECREF(z_item);
        Py_DECREF(sequence);
        return false;
    }
    Py_DECREF(x_item);
    Py_DECREF(y_item);
    Py_DECREF(z_item);
    Py_DECREF(sequence);
    return true;
}

bool parse_vertices(PyObject* object, std::vector<Vec3>& out, const char* argument_name) {
    PyObject* sequence = PySequence_Fast(object, argument_name);
    if (sequence == nullptr) {
        return false;
    }
    const auto count = static_cast<std::size_t>(PySequence_Size(sequence));
    out.clear();
    out.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, static_cast<Py_ssize_t>(index));
        if (item == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        Vec3 vertex;
        const bool ok = parse_vector3(item, vertex, "vertex");
        Py_DECREF(item);
        if (!ok) {
            Py_DECREF(sequence);
            return false;
        }
        out.push_back(vertex);
    }
    Py_DECREF(sequence);
    return true;
}

bool parse_triangles(PyObject* object, std::vector<Triangle>& out) {
    PyObject* sequence = PySequence_Fast(object, "triangles must be a sequence");
    if (sequence == nullptr) {
        return false;
    }
    const auto count = static_cast<std::size_t>(PySequence_Size(sequence));
    out.clear();
    out.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        PyObject* triangle_object = PySequence_GetItem(sequence, static_cast<Py_ssize_t>(index));
        if (triangle_object == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        PyObject* triangle_sequence = PySequence_Fast(triangle_object, "triangle must be a sequence of 3 vertices");
        Py_DECREF(triangle_object);
        if (triangle_sequence == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        if (PySequence_Size(triangle_sequence) != 3) {
            Py_DECREF(triangle_sequence);
            Py_DECREF(sequence);
            PyErr_SetString(PyExc_ValueError, "triangle must contain exactly 3 vertices");
            return false;
        }
        PyObject* vertex0 = PySequence_GetItem(triangle_sequence, 0);
        PyObject* vertex1 = PySequence_GetItem(triangle_sequence, 1);
        PyObject* vertex2 = PySequence_GetItem(triangle_sequence, 2);
        if (vertex0 == nullptr || vertex1 == nullptr || vertex2 == nullptr) {
            Py_XDECREF(vertex0);
            Py_XDECREF(vertex1);
            Py_XDECREF(vertex2);
            Py_DECREF(triangle_sequence);
            Py_DECREF(sequence);
            return false;
        }
        Triangle triangle;
        const bool ok = parse_vector3(vertex0, triangle.vertex0, "triangle vertex 0")
            && parse_vector3(vertex1, triangle.vertex1, "triangle vertex 1")
            && parse_vector3(vertex2, triangle.vertex2, "triangle vertex 2");
        Py_DECREF(vertex0);
        Py_DECREF(vertex1);
        Py_DECREF(vertex2);
        Py_DECREF(triangle_sequence);
        if (!ok) {
            Py_DECREF(sequence);
            return false;
        }
        out.push_back(triangle);
    }
    Py_DECREF(sequence);
    return true;
}

PyObject* build_vector3(const Vec3& value) {
    PyObject* tuple = PyTuple_New(3);
    if (tuple == nullptr) {
        return nullptr;
    }
    PyObject* x = PyFloat_FromDouble(value.x);
    PyObject* y = PyFloat_FromDouble(value.y);
    PyObject* z = PyFloat_FromDouble(value.z);
    if (x == nullptr || y == nullptr || z == nullptr) {
        Py_XDECREF(x);
        Py_XDECREF(y);
        Py_XDECREF(z);
        Py_DECREF(tuple);
        return nullptr;
    }
    if (PyTuple_SetItem(tuple, 0, x) < 0) {
        Py_DECREF(x);
        Py_DECREF(y);
        Py_DECREF(z);
        Py_DECREF(tuple);
        return nullptr;
    }
    x = nullptr;
    if (PyTuple_SetItem(tuple, 1, y) < 0) {
        Py_DECREF(y);
        Py_DECREF(z);
        Py_DECREF(tuple);
        return nullptr;
    }
    y = nullptr;
    if (PyTuple_SetItem(tuple, 2, z) < 0) {
        Py_DECREF(z);
        Py_DECREF(tuple);
        return nullptr;
    }
    return tuple;
}

PyObject* build_triangle_indices(const std::array<std::uint32_t, 3>& value) {
    PyObject* tuple = PyTuple_New(3);
    if (tuple == nullptr) {
        return nullptr;
    }
    PyObject* a = PyLong_FromUnsignedLong(value[0]);
    PyObject* b = PyLong_FromUnsignedLong(value[1]);
    PyObject* c = PyLong_FromUnsignedLong(value[2]);
    if (a == nullptr || b == nullptr || c == nullptr) {
        Py_XDECREF(a);
        Py_XDECREF(b);
        Py_XDECREF(c);
        Py_DECREF(tuple);
        return nullptr;
    }
    if (PyTuple_SetItem(tuple, 0, a) < 0) {
        Py_DECREF(a);
        Py_DECREF(b);
        Py_DECREF(c);
        Py_DECREF(tuple);
        return nullptr;
    }
    a = nullptr;
    if (PyTuple_SetItem(tuple, 1, b) < 0) {
        Py_DECREF(b);
        Py_DECREF(c);
        Py_DECREF(tuple);
        return nullptr;
    }
    b = nullptr;
    if (PyTuple_SetItem(tuple, 2, c) < 0) {
        Py_DECREF(c);
        Py_DECREF(tuple);
        return nullptr;
    }
    return tuple;
}

PyObject* build_chunk_list(const std::vector<TriangleChunk>& chunks) {
    PyObject* result = PyList_New(static_cast<Py_ssize_t>(chunks.size()));
    if (result == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t chunk_index = 0; chunk_index < static_cast<Py_ssize_t>(chunks.size()); ++chunk_index) {
        const auto& chunk = chunks[static_cast<std::size_t>(chunk_index)];
        PyObject* vertices = PyList_New(static_cast<Py_ssize_t>(chunk.vertices.size()));
        PyObject* triangles = PyList_New(static_cast<Py_ssize_t>(chunk.triangles.size()));
        PyObject* pair = PyTuple_New(2);
        if (vertices == nullptr || triangles == nullptr || pair == nullptr) {
            Py_XDECREF(vertices);
            Py_XDECREF(triangles);
            Py_XDECREF(pair);
            Py_DECREF(result);
            return nullptr;
        }
        for (Py_ssize_t vertex_index = 0; vertex_index < static_cast<Py_ssize_t>(chunk.vertices.size()); ++vertex_index) {
            PyObject* vertex = build_vector3(chunk.vertices[static_cast<std::size_t>(vertex_index)]);
            if (vertex == nullptr || PyList_SetItem(vertices, vertex_index, vertex) < 0) {
                Py_XDECREF(vertex);
                Py_DECREF(vertices);
                Py_DECREF(triangles);
                Py_DECREF(pair);
                Py_DECREF(result);
                return nullptr;
            }
        }
        for (Py_ssize_t triangle_index = 0; triangle_index < static_cast<Py_ssize_t>(chunk.triangles.size()); ++triangle_index) {
            PyObject* triangle = build_triangle_indices(chunk.triangles[static_cast<std::size_t>(triangle_index)]);
            if (triangle == nullptr || PyList_SetItem(triangles, triangle_index, triangle) < 0) {
                Py_XDECREF(triangle);
                Py_DECREF(vertices);
                Py_DECREF(triangles);
                Py_DECREF(pair);
                Py_DECREF(result);
                return nullptr;
            }
        }
        if (PyTuple_SetItem(pair, 0, vertices) < 0) {
            Py_DECREF(vertices);
            Py_DECREF(triangles);
            Py_DECREF(pair);
            Py_DECREF(result);
            return nullptr;
        }
        vertices = nullptr;
        if (PyTuple_SetItem(pair, 1, triangles) < 0) {
            Py_DECREF(triangles);
            Py_DECREF(pair);
            Py_DECREF(result);
            return nullptr;
        }
        if (PyList_SetItem(result, chunk_index, pair) < 0) {
            Py_DECREF(pair);
            Py_DECREF(result);
            return nullptr;
        }
    }
    return result;
}

}  // namespace

namespace fivefury_py {

PyObject* mod_bounds_triangle_area(PyObject*, PyObject* args) {
    PyObject* vertex0_object = nullptr;
    PyObject* vertex1_object = nullptr;
    PyObject* vertex2_object = nullptr;
    if (!PyArg_ParseTuple(args, "OOO:bounds_triangle_area", &vertex0_object, &vertex1_object, &vertex2_object)) {
        return nullptr;
    }
    Vec3 vertex0;
    Vec3 vertex1;
    Vec3 vertex2;
    if (!parse_vector3(vertex0_object, vertex0, "vertex0") ||
        !parse_vector3(vertex1_object, vertex1, "vertex1") ||
        !parse_vector3(vertex2_object, vertex2, "vertex2")) {
        return nullptr;
    }
    return PyFloat_FromDouble(triangle_area_impl(vertex0, vertex1, vertex2));
}

PyObject* mod_bounds_from_vertices(PyObject*, PyObject* args) {
    PyObject* vertices_object = nullptr;
    if (!PyArg_ParseTuple(args, "O:bounds_from_vertices", &vertices_object)) {
        return nullptr;
    }
    std::vector<Vec3> vertices;
    if (!parse_vertices(vertices_object, vertices, "vertices must be a sequence")) {
        return nullptr;
    }
    try {
        const auto [minimum, maximum] = bounds_from_vertices_impl(vertices);
        PyObject* result = PyTuple_New(2);
        if (result == nullptr) {
            return nullptr;
        }
        PyObject* minimum_object = build_vector3(minimum);
        PyObject* maximum_object = build_vector3(maximum);
        if (minimum_object == nullptr || maximum_object == nullptr) {
            Py_XDECREF(minimum_object);
            Py_XDECREF(maximum_object);
            Py_DECREF(result);
            return nullptr;
        }
        if (PyTuple_SetItem(result, 0, minimum_object) < 0) {
            Py_DECREF(minimum_object);
            Py_DECREF(maximum_object);
            Py_DECREF(result);
            return nullptr;
        }
        minimum_object = nullptr;
        if (PyTuple_SetItem(result, 1, maximum_object) < 0) {
            Py_DECREF(maximum_object);
            Py_DECREF(result);
            return nullptr;
        }
        return result;
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_bounds_sphere_radius_from_vertices(PyObject*, PyObject* args) {
    PyObject* center_object = nullptr;
    PyObject* vertices_object = nullptr;
    if (!PyArg_ParseTuple(args, "OO:bounds_sphere_radius_from_vertices", &center_object, &vertices_object)) {
        return nullptr;
    }
    Vec3 center;
    if (!parse_vector3(center_object, center, "center")) {
        return nullptr;
    }
    std::vector<Vec3> vertices;
    if (!parse_vertices(vertices_object, vertices, "vertices must be a sequence")) {
        return nullptr;
    }
    return PyFloat_FromDouble(sphere_radius_from_vertices_impl(center, vertices));
}

PyObject* mod_bounds_chunk_triangles(PyObject*, PyObject* args) {
    PyObject* triangles_object = nullptr;
    unsigned long max_vertices_per_child = 30000;
    unsigned long max_triangles_per_child = 32000;
    if (!PyArg_ParseTuple(
            args,
            "O|kk:bounds_chunk_triangles",
            &triangles_object,
            &max_vertices_per_child,
            &max_triangles_per_child
        )) {
        return nullptr;
    }
    if (max_vertices_per_child == 0 || max_triangles_per_child == 0) {
        PyErr_SetString(PyExc_ValueError, "chunk limits must be positive");
        return nullptr;
    }
    std::vector<Triangle> triangles;
    if (!parse_triangles(triangles_object, triangles)) {
        return nullptr;
    }
    try {
        const auto chunks = chunk_bound_triangles_impl(
            triangles,
            static_cast<std::size_t>(max_vertices_per_child),
            static_cast<std::size_t>(max_triangles_per_child)
        );
        return build_chunk_list(chunks);
    } catch (...) {
        return translate_cpp_exception();
    }
}

}  // namespace fivefury_py
