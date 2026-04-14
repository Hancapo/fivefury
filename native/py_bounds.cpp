#include "py_bindings.h"

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
            items,
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
