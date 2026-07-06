#pragma once

#include <array>
#include <cstddef>
#include <utility>
#include <vector>

#include "bounds_types.h"

namespace fivefury_native::bounds {

double triangle_area_impl(const Vec3& vertex0, const Vec3& vertex1, const Vec3& vertex2) noexcept;
std::vector<std::int16_t> quantize_vertices_impl(
    const std::vector<Vec3>& vertices,
    const Vec3& center,
    const Vec3& quantum
);
std::pair<Vec3, Vec3> bounds_from_vertices_impl(const std::vector<Vec3>& vertices);
double sphere_radius_from_vertices_impl(const Vec3& center, const std::vector<Vec3>& vertices) noexcept;
std::array<std::vector<std::uint32_t>, 8> build_octants_impl(const std::vector<Vec3>& vertices);
std::vector<double> indexed_triangle_areas_impl(
    const std::vector<Vec3>& vertices,
    const std::vector<std::array<std::uint32_t, 3>>& triangles
);
std::vector<Triangle> collect_triangles_impl(
    const std::vector<Vec3>& positions,
    const std::vector<std::int64_t>& indices,
    double min_area
);
std::vector<TriangleChunk> chunk_bound_triangles_impl(
    const std::vector<Triangle>& triangles,
    std::size_t max_vertices_per_child,
    std::size_t max_triangles_per_child
);
BvhBuildResult build_bvh_impl(
    std::vector<BvhItem> items,
    const Vec3& fallback_minimum,
    const Vec3& fallback_maximum,
    std::size_t item_threshold,
    std::size_t max_tree_node_count
);

}  // namespace fivefury_native::bounds
