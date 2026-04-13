#include "py_bindings.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <stdexcept>
#include <unordered_map>
#include <utility>
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

struct BvhItem {
    Vec3 minimum;
    Vec3 maximum;
    std::uint32_t index = 0;
};

struct BvhNodeOutput {
    Vec3 minimum;
    Vec3 maximum;
    std::uint32_t item_id = 0;
    std::uint32_t item_count = 0;
};

struct BvhTreeOutput {
    Vec3 minimum;
    Vec3 maximum;
    std::uint32_t node_index = 0;
    std::uint32_t node_index2 = 0;
};

constexpr std::array<std::array<int, 3>, 8> OCTANT_SIGNS = {{
    {{1, 1, 1}},
    {{-1, 1, 1}},
    {{1, -1, 1}},
    {{-1, -1, 1}},
    {{1, 1, -1}},
    {{-1, 1, -1}},
    {{1, -1, -1}},
    {{-1, -1, -1}},
}};

constexpr std::size_t MAX_BVH_TREE_NODE_COUNT = 127;

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

bool octant_shadowed_impl(const Vec3& vertex1, const Vec3& vertex2, const std::array<int, 3>& signs) noexcept {
    const double dx = (vertex2.x - vertex1.x) * static_cast<double>(signs[0]);
    const double dy = (vertex2.y - vertex1.y) * static_cast<double>(signs[1]);
    const double dz = (vertex2.z - vertex1.z) * static_cast<double>(signs[2]);
    return dx >= 0.0 && dy >= 0.0 && dz >= 0.0;
}

std::array<std::vector<std::uint32_t>, 8> build_octants_impl(const std::vector<Vec3>& vertices) {
    std::array<std::vector<std::uint32_t>, 8> octants;
    for (std::size_t octant_index = 0; octant_index < OCTANT_SIGNS.size(); ++octant_index) {
        std::vector<std::uint32_t> indices;
        for (std::uint32_t vertex_index = 0; vertex_index < static_cast<std::uint32_t>(vertices.size()); ++vertex_index) {
            const auto& vertex = vertices[vertex_index];
            bool should_add = true;
            std::vector<std::uint32_t> next_indices;
            for (const auto other_index : indices) {
                const auto& other_vertex = vertices[other_index];
                if (octant_shadowed_impl(vertex, other_vertex, OCTANT_SIGNS[octant_index])) {
                    should_add = false;
                    next_indices = indices;
                    break;
                }
                if (!octant_shadowed_impl(other_vertex, vertex, OCTANT_SIGNS[octant_index])) {
                    next_indices.push_back(other_index);
                }
            }
            if (should_add) {
                next_indices.push_back(vertex_index);
            }
            indices = std::move(next_indices);
        }
        octants[octant_index] = std::move(indices);
    }
    return octants;
}

std::pair<Vec3, Vec3> merge_item_bounds(const std::vector<BvhItem>& items, const std::pair<Vec3, Vec3>& fallback) {
    if (items.empty()) {
        return fallback;
    }
    Vec3 minimum = items.front().minimum;
    Vec3 maximum = items.front().maximum;
    for (std::size_t index = 1; index < items.size(); ++index) {
        const auto& item = items[index];
        minimum.x = std::min(minimum.x, item.minimum.x);
        minimum.y = std::min(minimum.y, item.minimum.y);
        minimum.z = std::min(minimum.z, item.minimum.z);
        maximum.x = std::max(maximum.x, item.maximum.x);
        maximum.y = std::max(maximum.y, item.maximum.y);
        maximum.z = std::max(maximum.z, item.maximum.z);
    }
    return {minimum, maximum};
}

Vec3 center_from_bounds_impl(const Vec3& minimum, const Vec3& maximum) noexcept {
    return {
        (minimum.x + maximum.x) * 0.5,
        (minimum.y + maximum.y) * 0.5,
        (minimum.z + maximum.z) * 0.5,
    };
}

Vec3 choose_bvh_quantum_impl(const Vec3& minimum, const Vec3& maximum, const Vec3& center) noexcept {
    std::array<double, 3> values{};
    const std::array<double, 3> min_values = {minimum.x, minimum.y, minimum.z};
    const std::array<double, 3> max_values = {maximum.x, maximum.y, maximum.z};
    const std::array<double, 3> center_values = {center.x, center.y, center.z};
    for (std::size_t axis = 0; axis < 3; ++axis) {
        const double half_extent = std::max(
            std::abs(min_values[axis] - center_values[axis]),
            std::abs(max_values[axis] - center_values[axis])
        );
        values[axis] = half_extent > 0.0 ? (half_extent / 32767.0) : (1.0 / 32767.0);
    }
    return {values[0], values[1], values[2]};
}

Vec3 invert_vec3(const Vec3& value) noexcept {
    return {
        value.x != 0.0 ? (1.0 / value.x) : 0.0,
        value.y != 0.0 ? (1.0 / value.y) : 0.0,
        value.z != 0.0 ? (1.0 / value.z) : 0.0,
    };
}

struct BvhNodeBuild {
    std::vector<BvhItem> items;
    std::vector<BvhNodeBuild> children;
    Vec3 minimum{};
    Vec3 maximum{};
    std::uint32_t index = 0;

    std::size_t total_nodes() const noexcept {
        std::size_t count = 1;
        for (const auto& child : children) {
            count += child.total_nodes();
        }
        return count;
    }

    std::size_t total_items() const noexcept {
        std::size_t count = items.size();
        for (const auto& child : children) {
            count += child.total_items();
        }
        return count;
    }

    void update_bounds() {
        if (!items.empty()) {
            const auto [min_value, max_value] = merge_item_bounds(items, {{0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}});
            minimum = min_value;
            maximum = max_value;
            return;
        }
        if (children.empty()) {
            minimum = {0.0, 0.0, 0.0};
            maximum = {0.0, 0.0, 0.0};
            return;
        }
        minimum = children.front().minimum;
        maximum = children.front().maximum;
        for (std::size_t i = 1; i < children.size(); ++i) {
            minimum.x = std::min(minimum.x, children[i].minimum.x);
            minimum.y = std::min(minimum.y, children[i].minimum.y);
            minimum.z = std::min(minimum.z, children[i].minimum.z);
            maximum.x = std::max(maximum.x, children[i].maximum.x);
            maximum.y = std::max(maximum.y, children[i].maximum.y);
            maximum.z = std::max(maximum.z, children[i].maximum.z);
        }
    }

    void build(std::size_t item_threshold) {
        update_bounds();
        if (items.empty() || items.size() <= item_threshold) {
            return;
        }

        std::array<double, 3> average = {0.0, 0.0, 0.0};
        for (const auto& item : items) {
            average[0] += item.minimum.x + item.maximum.x;
            average[1] += item.minimum.y + item.maximum.y;
            average[2] += item.minimum.z + item.maximum.z;
        }
        const double scale = 0.5 / static_cast<double>(items.size());
        average[0] *= scale;
        average[1] *= scale;
        average[2] *= scale;

        std::array<std::size_t, 3> counts = {0U, 0U, 0U};
        for (const auto& item : items) {
            const double center_x = (item.minimum.x + item.maximum.x) * 0.5;
            const double center_y = (item.minimum.y + item.maximum.y) * 0.5;
            const double center_z = (item.minimum.z + item.maximum.z) * 0.5;
            if (center_x < average[0]) {
                counts[0] += 1U;
            }
            if (center_y < average[1]) {
                counts[1] += 1U;
            }
            if (center_z < average[2]) {
                counts[2] += 1U;
            }
        }

        const double target = static_cast<double>(items.size()) / 2.0;
        const std::array<double, 3> deltas = {
            std::abs(target - static_cast<double>(counts[0])),
            std::abs(target - static_cast<double>(counts[1])),
            std::abs(target - static_cast<double>(counts[2])),
        };
        const std::size_t axis = std::min_element(deltas.begin(), deltas.end()) - deltas.begin();

        std::vector<BvhItem> upper;
        std::vector<BvhItem> lower;
        upper.reserve(items.size());
        lower.reserve(items.size());
        for (const auto& item : items) {
            const std::array<double, 3> center = {
                (item.minimum.x + item.maximum.x) * 0.5,
                (item.minimum.y + item.maximum.y) * 0.5,
                (item.minimum.z + item.maximum.z) * 0.5,
            };
            if (center[axis] > average[axis]) {
                upper.push_back(item);
            } else {
                lower.push_back(item);
            }
        }

        if (upper.empty() || lower.empty()) {
            std::vector<BvhItem> all_items = items;
            std::sort(all_items.begin(), all_items.end(), [](const BvhItem& left, const BvhItem& right) {
                if (left.minimum.x != right.minimum.x) return left.minimum.x < right.minimum.x;
                if (left.minimum.y != right.minimum.y) return left.minimum.y < right.minimum.y;
                if (left.minimum.z != right.minimum.z) return left.minimum.z < right.minimum.z;
                if (left.maximum.x != right.maximum.x) return left.maximum.x < right.maximum.x;
                if (left.maximum.y != right.maximum.y) return left.maximum.y < right.maximum.y;
                if (left.maximum.z != right.maximum.z) return left.maximum.z < right.maximum.z;
                return left.index < right.index;
            });
            const auto midpoint = all_items.size() / 2U;
            upper.assign(all_items.begin(), all_items.begin() + static_cast<std::ptrdiff_t>(midpoint));
            lower.assign(all_items.begin() + static_cast<std::ptrdiff_t>(midpoint), all_items.end());
            if (upper.empty() || lower.empty()) {
                return;
            }
        }

        items.clear();
        children.clear();
        children.reserve(2);
        children.push_back(BvhNodeBuild{std::move(upper)});
        children.push_back(BvhNodeBuild{std::move(lower)});
        for (auto& child : children) {
            child.build(item_threshold);
        }
        std::sort(children.begin(), children.end(), [](const BvhNodeBuild& left, const BvhNodeBuild& right) {
            return left.total_items() > right.total_items();
        });
        update_bounds();
    }

    void gather_nodes(std::vector<const BvhNodeBuild*>& nodes) {
        index = static_cast<std::uint32_t>(nodes.size());
        nodes.push_back(this);
        for (auto& child : children) {
            child.gather_nodes(nodes);
        }
    }

    void gather_trees(std::vector<const BvhNodeBuild*>& trees, std::size_t max_tree_node_count) const {
        if (total_nodes() > max_tree_node_count && !children.empty()) {
            for (const auto& child : children) {
                child.gather_trees(trees, max_tree_node_count);
            }
            return;
        }
        trees.push_back(this);
    }
};

struct BvhBuildResult {
    Vec3 overall_minimum{};
    Vec3 overall_maximum{};
    Vec3 center{};
    Vec3 quantum_inverse{};
    Vec3 quantum{};
    std::vector<std::uint32_t> order;
    std::vector<BvhNodeOutput> nodes;
    std::vector<BvhTreeOutput> trees;
};

BvhBuildResult build_bvh_impl(
    const std::vector<BvhItem>& items,
    const Vec3& fallback_minimum,
    const Vec3& fallback_maximum,
    std::size_t item_threshold,
    std::size_t max_tree_node_count
) {
    BvhBuildResult result;
    if (items.empty()) {
        result.overall_minimum = fallback_minimum;
        result.overall_maximum = fallback_maximum;
        result.center = center_from_bounds_impl(fallback_minimum, fallback_maximum);
        result.quantum = choose_bvh_quantum_impl(fallback_minimum, fallback_maximum, result.center);
        result.quantum_inverse = invert_vec3(result.quantum);
        return result;
    }

    BvhNodeBuild root{items};
    root.build(item_threshold);

    std::vector<const BvhNodeBuild*> nodes;
    nodes.reserve(root.total_nodes());
    root.gather_nodes(nodes);

    std::vector<const BvhNodeBuild*> trees;
    root.gather_trees(trees, max_tree_node_count);

    result.overall_minimum = root.minimum;
    result.overall_maximum = root.maximum;
    result.center = center_from_bounds_impl(root.minimum, root.maximum);
    result.quantum = choose_bvh_quantum_impl(root.minimum, root.maximum, result.center);
    result.quantum_inverse = invert_vec3(result.quantum);

    result.order.reserve(items.size());
    std::unordered_map<std::uint32_t, std::uint32_t> reordered_index_lookup;
    reordered_index_lookup.reserve(items.size());
    for (const auto* node : nodes) {
        if (!node->items.empty()) {
            for (const auto& item : node->items) {
                const auto reordered_index = static_cast<std::uint32_t>(result.order.size());
                result.order.push_back(item.index);
                reordered_index_lookup.emplace(item.index, reordered_index);
            }
        }
    }

    result.nodes.reserve(nodes.size());
    for (const auto* node : nodes) {
        BvhNodeOutput out;
        out.minimum = node->minimum;
        out.maximum = node->maximum;
        if (!node->items.empty()) {
            const auto lookup = reordered_index_lookup.find(node->items.front().index);
            out.item_id = lookup == reordered_index_lookup.end() ? 0U : lookup->second;
            out.item_count = static_cast<std::uint32_t>(node->total_items());
        } else {
            out.item_id = static_cast<std::uint32_t>(node->total_nodes());
            out.item_count = 0U;
        }
        result.nodes.push_back(out);
    }

    result.trees.reserve(trees.size());
    for (const auto* tree : trees) {
        result.trees.push_back(BvhTreeOutput{
            tree->minimum,
            tree->maximum,
            tree->index,
            static_cast<std::uint32_t>(tree->index + tree->total_nodes()),
        });
    }

    return result;
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

bool parse_bvh_items(PyObject* object, std::vector<BvhItem>& out) {
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
            Py_DECREF(item_sequence);
            Py_DECREF(sequence);
            PyErr_SetString(PyExc_ValueError, "item must contain minimum, maximum and index");
            return false;
        }
        PyObject* minimum_object = PySequence_GetItem(item_sequence, 0);
        PyObject* maximum_object = PySequence_GetItem(item_sequence, 1);
        PyObject* index_object = PySequence_GetItem(item_sequence, 2);
        if (minimum_object == nullptr || maximum_object == nullptr || index_object == nullptr) {
            Py_XDECREF(minimum_object);
            Py_XDECREF(maximum_object);
            Py_XDECREF(index_object);
            Py_DECREF(item_sequence);
            Py_DECREF(sequence);
            return false;
        }
        BvhItem item;
        const bool ok = parse_vector3(minimum_object, item.minimum, "item minimum")
            && parse_vector3(maximum_object, item.maximum, "item maximum");
        Py_DECREF(minimum_object);
        Py_DECREF(maximum_object);
        if (!ok) {
            Py_DECREF(index_object);
            Py_DECREF(item_sequence);
            Py_DECREF(sequence);
            return false;
        }
        const auto parsed_index = PyLong_AsUnsignedLong(index_object);
        Py_DECREF(index_object);
        Py_DECREF(item_sequence);
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

PyObject* build_u32_list(const std::vector<std::uint32_t>& values) {
    PyObject* list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(values.size()); ++index) {
        PyObject* value = PyLong_FromUnsignedLong(values[static_cast<std::size_t>(index)]);
        if (value == nullptr || PyList_SetItem(list, index, value) < 0) {
            Py_XDECREF(value);
            Py_DECREF(list);
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
            Py_XDECREF(item);
            Py_DECREF(list);
            return nullptr;
        }
    }
    return list;
}

PyObject* build_bvh_nodes(const std::vector<BvhNodeOutput>& nodes) {
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
            Py_XDECREF(tuple);
            Py_XDECREF(minimum);
            Py_XDECREF(maximum);
            Py_XDECREF(item_id);
            Py_XDECREF(item_count);
            Py_DECREF(list);
            return nullptr;
        }
        if (PyTuple_SetItem(tuple, 0, minimum) < 0 ||
            PyTuple_SetItem(tuple, 1, maximum) < 0 ||
            PyTuple_SetItem(tuple, 2, item_id) < 0 ||
            PyTuple_SetItem(tuple, 3, item_count) < 0 ||
            PyList_SetItem(list, index, tuple) < 0) {
            Py_DECREF(tuple);
            Py_DECREF(list);
            return nullptr;
        }
    }
    return list;
}

PyObject* build_bvh_trees(const std::vector<BvhTreeOutput>& trees) {
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
            Py_XDECREF(tuple);
            Py_XDECREF(minimum);
            Py_XDECREF(maximum);
            Py_XDECREF(node_index);
            Py_XDECREF(node_index2);
            Py_DECREF(list);
            return nullptr;
        }
        if (PyTuple_SetItem(tuple, 0, minimum) < 0 ||
            PyTuple_SetItem(tuple, 1, maximum) < 0 ||
            PyTuple_SetItem(tuple, 2, node_index) < 0 ||
            PyTuple_SetItem(tuple, 3, node_index2) < 0 ||
            PyList_SetItem(list, index, tuple) < 0) {
            Py_DECREF(tuple);
            Py_DECREF(list);
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
            Py_XDECREF(payload);
            Py_XDECREF(order);
            Py_XDECREF(overall_minimum);
            Py_XDECREF(overall_maximum);
            Py_XDECREF(center);
            Py_XDECREF(quantum_inverse);
            Py_XDECREF(quantum);
            Py_XDECREF(nodes);
            Py_XDECREF(trees);
            return nullptr;
        }
        if (PyTuple_SetItem(payload, 0, order) < 0 ||
            PyTuple_SetItem(payload, 1, overall_minimum) < 0 ||
            PyTuple_SetItem(payload, 2, overall_maximum) < 0 ||
            PyTuple_SetItem(payload, 3, center) < 0 ||
            PyTuple_SetItem(payload, 4, quantum_inverse) < 0 ||
            PyTuple_SetItem(payload, 5, quantum) < 0 ||
            PyTuple_SetItem(payload, 6, nodes) < 0 ||
            PyTuple_SetItem(payload, 7, trees) < 0) {
            Py_DECREF(payload);
            return nullptr;
        }
        return payload;
    } catch (...) {
        return translate_cpp_exception();
    }
}

}  // namespace fivefury_py
