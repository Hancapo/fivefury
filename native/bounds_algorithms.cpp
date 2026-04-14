#include "bounds_algorithms.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

namespace fivefury_native::bounds {

namespace {

bool octant_shadowed_impl(const Vec3& vertex1, const Vec3& vertex2, const std::array<int, 3>& signs) noexcept {
    const double dx = (vertex2.x - vertex1.x) * static_cast<double>(signs[0]);
    const double dy = (vertex2.y - vertex1.y) * static_cast<double>(signs[1]);
    const double dz = (vertex2.z - vertex1.z) * static_cast<double>(signs[2]);
    return dx >= 0.0 && dy >= 0.0 && dz >= 0.0;
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

Vec3 center_from_bounds_impl_internal(const Vec3& minimum, const Vec3& maximum) noexcept {
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
            if (center_x < average[0]) counts[0] += 1U;
            if (center_y < average[1]) counts[1] += 1U;
            if (center_z < average[2]) counts[2] += 1U;
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

}  // namespace

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
        result.center = center_from_bounds_impl_internal(fallback_minimum, fallback_maximum);
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
    result.center = center_from_bounds_impl_internal(root.minimum, root.maximum);
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

}  // namespace fivefury_native::bounds
