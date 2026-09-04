#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

namespace fivefury_native::bounds {

struct Vec3 {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;

    bool operator==(const Vec3& other) const noexcept {
        return x == other.x && y == other.y && z == other.z;
    }
};

inline constexpr std::array<std::array<int, 3>, 8> OCTANT_SIGNS = {{
    {{1, 1, 1}},
    {{-1, 1, 1}},
    {{1, -1, 1}},
    {{-1, -1, 1}},
    {{1, 1, -1}},
    {{-1, 1, -1}},
    {{1, -1, -1}},
    {{-1, -1, -1}},
}};

inline constexpr std::size_t MAX_BVH_TREE_NODE_COUNT = 127;

inline double canonical_zero(double value) noexcept {
    return value == 0.0 ? 0.0 : value;
}

inline std::uint64_t hashable_double(double value) noexcept {
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

}  // namespace fivefury_native::bounds
