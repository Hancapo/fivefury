#include "py_bindings.h"

#include <array>
#include <utility>
#include <vector>

#include "bounds_algorithms.h"
#include "bounds_python.h"

namespace fivefury_py {

using namespace fivefury_native::bounds;

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

PyObject* mod_bounds_quantize_vertices(PyObject*, PyObject* args) {
    PyObject* vertices_object = nullptr;
    PyObject* center_object = nullptr;
    PyObject* quantum_object = nullptr;
    if (!PyArg_ParseTuple(args, "OOO:bounds_quantize_vertices", &vertices_object, &center_object, &quantum_object)) {
        return nullptr;
    }
    Vec3 center;
    Vec3 quantum;
    if (!parse_vector3(center_object, center, "center") || !parse_vector3(quantum_object, quantum, "quantum")) {
        return nullptr;
    }
    std::vector<Vec3> vertices;
    if (!parse_vertices(vertices_object, vertices, "vertices must be a sequence")) {
        return nullptr;
    }
    try {
        const auto packed = quantize_vertices_impl(vertices, center, quantum);
        std::vector<char> data(packed.size() * 2U);
        for (std::size_t index = 0; index < packed.size(); ++index) {
            const auto value = static_cast<std::uint16_t>(packed[index]);
            data[index * 2U] = static_cast<char>(value & 0xFFU);
            data[(index * 2U) + 1U] = static_cast<char>((value >> 8U) & 0xFFU);
        }
        return PyBytes_FromStringAndSize(data.data(), static_cast<Py_ssize_t>(data.size()));
    } catch (...) {
        return translate_cpp_exception();
    }
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
        PyObject* minimum_object = build_vector3(minimum);
        PyObject* maximum_object = build_vector3(maximum);
        if (result == nullptr || minimum_object == nullptr || maximum_object == nullptr) {
            Py_XDECREF(result); Py_XDECREF(minimum_object); Py_XDECREF(maximum_object);
            return nullptr;
        }
        if (PyTuple_SetItem(result, 0, minimum_object) < 0 || PyTuple_SetItem(result, 1, maximum_object) < 0) {
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

namespace {

bool parse_index_triples(PyObject* object, std::vector<std::array<std::uint32_t, 3>>& out) {
    PyObject* sequence = PySequence_Fast(object, "triangles must be a sequence");
    if (sequence == nullptr) {
        return false;
    }
    const auto count = PySequence_Size(sequence);
    if (count < 0) {
        Py_DECREF(sequence);
        return false;
    }
    out.clear();
    out.reserve(static_cast<std::size_t>(count));
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        if (item == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        PyObject* triple = PySequence_Fast(item, "triangle must be a sequence of 3 indices");
        Py_DECREF(item);
        if (triple == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        if (PySequence_Size(triple) != 3) {
            Py_DECREF(triple);
            Py_DECREF(sequence);
            PyErr_SetString(PyExc_ValueError, "triangle must contain exactly 3 indices");
            return false;
        }
        std::array<std::uint32_t, 3> values{};
        for (Py_ssize_t component = 0; component < 3; ++component) {
            PyObject* value = PySequence_GetItem(triple, component);
            if (value == nullptr) {
                Py_DECREF(triple);
                Py_DECREF(sequence);
                return false;
            }
            const auto parsed = PyLong_AsUnsignedLong(value);
            Py_DECREF(value);
            if (PyErr_Occurred() != nullptr) {
                Py_DECREF(triple);
                Py_DECREF(sequence);
                return false;
            }
            values[static_cast<std::size_t>(component)] = static_cast<std::uint32_t>(parsed);
        }
        Py_DECREF(triple);
        out.push_back(values);
    }
    Py_DECREF(sequence);
    return true;
}

bool parse_int64_list(PyObject* object, std::vector<std::int64_t>& out) {
    PyObject* sequence = PySequence_Fast(object, "indices must be a sequence");
    if (sequence == nullptr) {
        return false;
    }
    const auto count = PySequence_Size(sequence);
    if (count < 0) {
        Py_DECREF(sequence);
        return false;
    }
    out.clear();
    out.reserve(static_cast<std::size_t>(count));
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        if (item == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        const auto value = PyLong_AsLongLong(item);
        Py_DECREF(item);
        if (value == -1 && PyErr_Occurred() != nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        out.push_back(static_cast<std::int64_t>(value));
    }
    Py_DECREF(sequence);
    return true;
}

}  // namespace

PyObject* mod_bounds_indexed_triangle_areas(PyObject*, PyObject* args) {
    PyObject* vertices_object = nullptr;
    PyObject* triangles_object = nullptr;
    if (!PyArg_ParseTuple(args, "OO:bounds_indexed_triangle_areas", &vertices_object, &triangles_object)) {
        return nullptr;
    }
    std::vector<Vec3> vertices;
    if (!parse_vertices(vertices_object, vertices, "vertices must be a sequence")) {
        return nullptr;
    }
    std::vector<std::array<std::uint32_t, 3>> triangles;
    if (!parse_index_triples(triangles_object, triangles)) {
        return nullptr;
    }
    try {
        const auto areas = indexed_triangle_areas_impl(vertices, triangles);
        PyObject* list = PyList_New(static_cast<Py_ssize_t>(areas.size()));
        if (list == nullptr) {
            return nullptr;
        }
        for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(areas.size()); ++index) {
            PyObject* value = PyFloat_FromDouble(areas[static_cast<std::size_t>(index)]);
            if (value == nullptr || PyList_SetItem(list, index, value) < 0) {
                Py_XDECREF(value);
                Py_DECREF(list);
                return nullptr;
            }
        }
        return list;
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_bounds_collect_triangles(PyObject*, PyObject* args) {
    PyObject* positions_object = nullptr;
    PyObject* indices_object = nullptr;
    double min_area = 1e-10;
    if (!PyArg_ParseTuple(args, "OO|d:bounds_collect_triangles", &positions_object, &indices_object, &min_area)) {
        return nullptr;
    }
    std::vector<Vec3> positions;
    if (!parse_vertices(positions_object, positions, "positions must be a sequence")) {
        return nullptr;
    }
    std::vector<std::int64_t> indices;
    if (!parse_int64_list(indices_object, indices)) {
        return nullptr;
    }
    try {
        const auto triangles = collect_triangles_impl(positions, indices, min_area);
        PyObject* list = PyList_New(static_cast<Py_ssize_t>(triangles.size()));
        if (list == nullptr) {
            return nullptr;
        }
        for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(triangles.size()); ++index) {
            const auto& triangle = triangles[static_cast<std::size_t>(index)];
            PyObject* tuple = PyTuple_New(3);
            PyObject* vertex0 = build_vector3(triangle.vertex0);
            PyObject* vertex1 = build_vector3(triangle.vertex1);
            PyObject* vertex2 = build_vector3(triangle.vertex2);
            if (tuple == nullptr || vertex0 == nullptr || vertex1 == nullptr || vertex2 == nullptr) {
                Py_XDECREF(tuple); Py_XDECREF(vertex0); Py_XDECREF(vertex1); Py_XDECREF(vertex2); Py_DECREF(list);
                return nullptr;
            }
            if (PyTuple_SetItem(tuple, 0, vertex0) < 0 || PyTuple_SetItem(tuple, 1, vertex1) < 0 ||
                PyTuple_SetItem(tuple, 2, vertex2) < 0 || PyList_SetItem(list, index, tuple) < 0) {
                Py_DECREF(tuple); Py_DECREF(list);
                return nullptr;
            }
        }
        return list;
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_bounds_chunk_triangles(PyObject*, PyObject* args) {
    PyObject* triangles_object = nullptr;
    unsigned long max_vertices_per_child = 30000;
    unsigned long max_triangles_per_child = 32000;
    if (!PyArg_ParseTuple(args, "O|kk:bounds_chunk_triangles", &triangles_object, &max_vertices_per_child, &max_triangles_per_child)) {
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
        return build_chunk_list(chunk_bound_triangles_impl(
            triangles,
            static_cast<std::size_t>(max_vertices_per_child),
            static_cast<std::size_t>(max_triangles_per_child)
        ));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_bounds_build_octants(PyObject*, PyObject* args) {
    PyObject* vertices_object = nullptr;
    if (!PyArg_ParseTuple(args, "O:bounds_build_octants", &vertices_object)) {
        return nullptr;
    }
    std::vector<Vec3> vertices;
    if (!parse_vertices(vertices_object, vertices, "vertices must be a sequence")) {
        return nullptr;
    }
    try {
        return build_octant_list(build_octants_impl(vertices));
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_bounds_build_bvh(PyObject*, PyObject* args) {
    PyObject* items_object = nullptr;
    PyObject* fallback_minimum_object = nullptr;
    PyObject* fallback_maximum_object = nullptr;
    unsigned long item_threshold = 4;
    unsigned long max_tree_node_count = MAX_BVH_TREE_NODE_COUNT;
    if (!PyArg_ParseTuple(
            args,
            "OOO|kk:bounds_build_bvh",
            &items_object,
            &fallback_minimum_object,
            &fallback_maximum_object,
            &item_threshold,
            &max_tree_node_count
        )) {
        return nullptr;
    }
    Vec3 fallback_minimum;
    Vec3 fallback_maximum;
    if (!parse_vector3(fallback_minimum_object, fallback_minimum, "fallback_minimum") ||
        !parse_vector3(fallback_maximum_object, fallback_maximum, "fallback_maximum")) {
        return nullptr;
    }
    std::vector<BvhItem> items;
    if (!parse_bvh_items(items_object, items)) {
        return nullptr;
    }
    try {
        const auto result = build_bvh_impl(
            std::move(items),
            fallback_minimum,
            fallback_maximum,
            static_cast<std::size_t>(item_threshold),
            static_cast<std::size_t>(max_tree_node_count)
        );
        PyObject* payload = PyTuple_New(8);
        PyObject* order = build_u32_list(result.order);
        PyObject* overall_minimum = build_vector3(result.overall_minimum);
        PyObject* overall_maximum = build_vector3(result.overall_maximum);
        PyObject* center = build_vector3(result.center);
        PyObject* quantum_inverse = build_vector3(result.quantum_inverse);
        PyObject* quantum = build_vector3(result.quantum);
        PyObject* nodes = build_bvh_nodes(result.nodes);
        PyObject* trees = build_bvh_trees(result.trees);
        if (payload == nullptr || order == nullptr || overall_minimum == nullptr || overall_maximum == nullptr ||
            center == nullptr || quantum_inverse == nullptr || quantum == nullptr || nodes == nullptr || trees == nullptr) {
            Py_XDECREF(payload); Py_XDECREF(order); Py_XDECREF(overall_minimum); Py_XDECREF(overall_maximum);
            Py_XDECREF(center); Py_XDECREF(quantum_inverse); Py_XDECREF(quantum); Py_XDECREF(nodes); Py_XDECREF(trees);
            return nullptr;
        }
        if (PyTuple_SetItem(payload, 0, order) < 0 || PyTuple_SetItem(payload, 1, overall_minimum) < 0 ||
            PyTuple_SetItem(payload, 2, overall_maximum) < 0 || PyTuple_SetItem(payload, 3, center) < 0 ||
            PyTuple_SetItem(payload, 4, quantum_inverse) < 0 || PyTuple_SetItem(payload, 5, quantum) < 0 ||
            PyTuple_SetItem(payload, 6, nodes) < 0 || PyTuple_SetItem(payload, 7, trees) < 0) {
            Py_DECREF(payload);
            return nullptr;
        }
        return payload;
    } catch (...) {
        return translate_cpp_exception();
    }
}

}  // namespace fivefury_py
