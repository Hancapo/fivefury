#include "bounds_python.h"

#include <array>
#include <cstddef>
#include <vector>

namespace fivefury_py {

bool parse_vector3(PyObject* object, fivefury_native::bounds::Vec3& out, const char* argument_name) {
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
    out.x = fivefury_native::bounds::canonical_zero(PyFloat_AsDouble(x_item));
    if (PyErr_Occurred() != nullptr) {
        Py_DECREF(x_item); Py_DECREF(y_item); Py_DECREF(z_item); Py_DECREF(sequence);
        return false;
    }
    out.y = fivefury_native::bounds::canonical_zero(PyFloat_AsDouble(y_item));
    if (PyErr_Occurred() != nullptr) {
        Py_DECREF(x_item); Py_DECREF(y_item); Py_DECREF(z_item); Py_DECREF(sequence);
        return false;
    }
    out.z = fivefury_native::bounds::canonical_zero(PyFloat_AsDouble(z_item));
    if (PyErr_Occurred() != nullptr) {
        Py_DECREF(x_item); Py_DECREF(y_item); Py_DECREF(z_item); Py_DECREF(sequence);
        return false;
    }
    Py_DECREF(x_item); Py_DECREF(y_item); Py_DECREF(z_item); Py_DECREF(sequence);
    return true;
}

bool parse_vertices(PyObject* object, std::vector<fivefury_native::bounds::Vec3>& out, const char* argument_name) {
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
        fivefury_native::bounds::Vec3 vertex;
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

bool parse_triangles(PyObject* object, std::vector<fivefury_native::bounds::Triangle>& out) {
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
            Py_XDECREF(vertex0); Py_XDECREF(vertex1); Py_XDECREF(vertex2);
            Py_DECREF(triangle_sequence); Py_DECREF(sequence);
            return false;
        }
        fivefury_native::bounds::Triangle triangle;
        const bool ok = parse_vector3(vertex0, triangle.vertex0, "triangle vertex 0")
            && parse_vector3(vertex1, triangle.vertex1, "triangle vertex 1")
            && parse_vector3(vertex2, triangle.vertex2, "triangle vertex 2");
        Py_DECREF(vertex0); Py_DECREF(vertex1); Py_DECREF(vertex2); Py_DECREF(triangle_sequence);
        if (!ok) {
            Py_DECREF(sequence);
            return false;
        }
        out.push_back(triangle);
    }
    Py_DECREF(sequence);
    return true;
}

bool parse_bvh_items(PyObject* object, std::vector<fivefury_native::bounds::BvhItem>& out) {
    PyObject* sequence = PySequence_Fast(object, "items must be a sequence");
    if (sequence == nullptr) {
        return false;
    }
    const auto count = static_cast<std::size_t>(PySequence_Size(sequence));
    out.clear();
    out.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        PyObject* item_object = PySequence_GetItem(sequence, static_cast<Py_ssize_t>(index));
        if (item_object == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        PyObject* item_sequence = PySequence_Fast(item_object, "item must be a sequence of (minimum, maximum, index)");
        Py_DECREF(item_object);
        if (item_sequence == nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        if (PySequence_Size(item_sequence) != 3) {
            Py_DECREF(item_sequence); Py_DECREF(sequence);
            PyErr_SetString(PyExc_ValueError, "item must contain minimum, maximum and index");
            return false;
        }
        PyObject* minimum_object = PySequence_GetItem(item_sequence, 0);
        PyObject* maximum_object = PySequence_GetItem(item_sequence, 1);
        PyObject* index_object = PySequence_GetItem(item_sequence, 2);
        if (minimum_object == nullptr || maximum_object == nullptr || index_object == nullptr) {
            Py_XDECREF(minimum_object); Py_XDECREF(maximum_object); Py_XDECREF(index_object);
            Py_DECREF(item_sequence); Py_DECREF(sequence);
            return false;
        }
        fivefury_native::bounds::BvhItem item;
        const bool ok = parse_vector3(minimum_object, item.minimum, "item minimum")
            && parse_vector3(maximum_object, item.maximum, "item maximum");
        Py_DECREF(minimum_object); Py_DECREF(maximum_object);
        if (!ok) {
            Py_DECREF(index_object); Py_DECREF(item_sequence); Py_DECREF(sequence);
            return false;
        }
        const auto parsed_index = PyLong_AsUnsignedLong(index_object);
        Py_DECREF(index_object); Py_DECREF(item_sequence);
        if (PyErr_Occurred() != nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        item.index = static_cast<std::uint32_t>(parsed_index);
        out.push_back(item);
    }
    Py_DECREF(sequence);
    return true;
}

PyObject* build_vector3(const fivefury_native::bounds::Vec3& value) {
    PyObject* tuple = PyTuple_New(3);
    if (tuple == nullptr) {
        return nullptr;
    }
    PyObject* x = PyFloat_FromDouble(value.x);
    PyObject* y = PyFloat_FromDouble(value.y);
    PyObject* z = PyFloat_FromDouble(value.z);
    if (x == nullptr || y == nullptr || z == nullptr) {
        Py_XDECREF(x); Py_XDECREF(y); Py_XDECREF(z); Py_DECREF(tuple);
        return nullptr;
    }
    if (PyTuple_SetItem(tuple, 0, x) < 0 || PyTuple_SetItem(tuple, 1, y) < 0 || PyTuple_SetItem(tuple, 2, z) < 0) {
        Py_DECREF(tuple);
        return nullptr;
    }
    return tuple;
}

PyObject* build_u32_list(const std::vector<std::uint32_t>& values) {
    PyObject* list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(values.size()); ++index) {
        PyObject* value = PyLong_FromUnsignedLong(values[static_cast<std::size_t>(index)]);
        if (value == nullptr || PyList_SetItem(list, index, value) < 0) {
            Py_XDECREF(value); Py_DECREF(list);
            return nullptr;
        }
    }
    return list;
}

PyObject* build_octant_list(const std::array<std::vector<std::uint32_t>, 8>& octants) {
    PyObject* list = PyList_New(8);
    if (list == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < 8; ++index) {
        PyObject* item = build_u32_list(octants[static_cast<std::size_t>(index)]);
        if (item == nullptr || PyList_SetItem(list, index, item) < 0) {
            Py_XDECREF(item); Py_DECREF(list);
            return nullptr;
        }
    }
    return list;
}

PyObject* build_bvh_nodes(const std::vector<fivefury_native::bounds::BvhNodeOutput>& nodes) {
    PyObject* list = PyList_New(static_cast<Py_ssize_t>(nodes.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(nodes.size()); ++index) {
        const auto& node = nodes[static_cast<std::size_t>(index)];
        PyObject* tuple = PyTuple_New(4);
        PyObject* minimum = build_vector3(node.minimum);
        PyObject* maximum = build_vector3(node.maximum);
        PyObject* item_id = PyLong_FromUnsignedLong(node.item_id);
        PyObject* item_count = PyLong_FromUnsignedLong(node.item_count);
        if (tuple == nullptr || minimum == nullptr || maximum == nullptr || item_id == nullptr || item_count == nullptr) {
            Py_XDECREF(tuple); Py_XDECREF(minimum); Py_XDECREF(maximum); Py_XDECREF(item_id); Py_XDECREF(item_count); Py_DECREF(list);
            return nullptr;
        }
        if (PyTuple_SetItem(tuple, 0, minimum) < 0 || PyTuple_SetItem(tuple, 1, maximum) < 0 ||
            PyTuple_SetItem(tuple, 2, item_id) < 0 || PyTuple_SetItem(tuple, 3, item_count) < 0 ||
            PyList_SetItem(list, index, tuple) < 0) {
            Py_DECREF(tuple); Py_DECREF(list);
            return nullptr;
        }
    }
    return list;
}

PyObject* build_bvh_trees(const std::vector<fivefury_native::bounds::BvhTreeOutput>& trees) {
    PyObject* list = PyList_New(static_cast<Py_ssize_t>(trees.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(trees.size()); ++index) {
        const auto& tree = trees[static_cast<std::size_t>(index)];
        PyObject* tuple = PyTuple_New(4);
        PyObject* minimum = build_vector3(tree.minimum);
        PyObject* maximum = build_vector3(tree.maximum);
        PyObject* node_index = PyLong_FromUnsignedLong(tree.node_index);
        PyObject* node_index2 = PyLong_FromUnsignedLong(tree.node_index2);
        if (tuple == nullptr || minimum == nullptr || maximum == nullptr || node_index == nullptr || node_index2 == nullptr) {
            Py_XDECREF(tuple); Py_XDECREF(minimum); Py_XDECREF(maximum); Py_XDECREF(node_index); Py_XDECREF(node_index2); Py_DECREF(list);
            return nullptr;
        }
        if (PyTuple_SetItem(tuple, 0, minimum) < 0 || PyTuple_SetItem(tuple, 1, maximum) < 0 ||
            PyTuple_SetItem(tuple, 2, node_index) < 0 || PyTuple_SetItem(tuple, 3, node_index2) < 0 ||
            PyList_SetItem(list, index, tuple) < 0) {
            Py_DECREF(tuple); Py_DECREF(list);
            return nullptr;
        }
    }
    return list;
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
        Py_XDECREF(a); Py_XDECREF(b); Py_XDECREF(c); Py_DECREF(tuple);
        return nullptr;
    }
    if (PyTuple_SetItem(tuple, 0, a) < 0 || PyTuple_SetItem(tuple, 1, b) < 0 || PyTuple_SetItem(tuple, 2, c) < 0) {
        Py_DECREF(tuple);
        return nullptr;
    }
    return tuple;
}

PyObject* build_chunk_list(const std::vector<fivefury_native::bounds::TriangleChunk>& chunks) {
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
            Py_XDECREF(vertices); Py_XDECREF(triangles); Py_XDECREF(pair); Py_DECREF(result);
            return nullptr;
        }
        for (Py_ssize_t vertex_index = 0; vertex_index < static_cast<Py_ssize_t>(chunk.vertices.size()); ++vertex_index) {
            PyObject* vertex = build_vector3(chunk.vertices[static_cast<std::size_t>(vertex_index)]);
            if (vertex == nullptr || PyList_SetItem(vertices, vertex_index, vertex) < 0) {
                Py_XDECREF(vertex); Py_DECREF(vertices); Py_DECREF(triangles); Py_DECREF(pair); Py_DECREF(result);
                return nullptr;
            }
        }
        for (Py_ssize_t triangle_index = 0; triangle_index < static_cast<Py_ssize_t>(chunk.triangles.size()); ++triangle_index) {
            PyObject* triangle = build_triangle_indices(chunk.triangles[static_cast<std::size_t>(triangle_index)]);
            if (triangle == nullptr || PyList_SetItem(triangles, triangle_index, triangle) < 0) {
                Py_XDECREF(triangle); Py_DECREF(vertices); Py_DECREF(triangles); Py_DECREF(pair); Py_DECREF(result);
                return nullptr;
            }
        }
        if (PyTuple_SetItem(pair, 0, vertices) < 0 || PyTuple_SetItem(pair, 1, triangles) < 0 || PyList_SetItem(result, chunk_index, pair) < 0) {
            Py_DECREF(pair); Py_DECREF(result);
            return nullptr;
        }
    }
    return result;
}

}  // namespace fivefury_py
