#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <tuple>
#include <vector>

namespace fivefury_native::resource {

struct ResourceBlockSpan {
    std::uint64_t offset = 0;
    std::uint64_t size = 0;
    bool relocate_pointers = true;
};

struct ResourceSectionLayout {
    std::uint32_t flags = 0;
    std::vector<std::tuple<std::uint64_t, std::uint64_t, std::uint64_t>> offset_map;
};

struct ResourceLayoutResult {
    std::string system_data;
    std::string graphics_data;
    std::uint32_t system_flags = 0;
    std::uint32_t graphics_flags = 0;
};

std::uint64_t get_resource_size_from_flags_impl(std::uint32_t flags);
std::uint32_t get_resource_total_page_count_impl(std::uint32_t flags);
ResourceLayoutResult layout_resource_sections_impl(
    const std::string& system_data,
    const std::vector<ResourceBlockSpan>& system_blocks,
    const std::string& graphics_data,
    const std::vector<ResourceBlockSpan>& graphics_blocks,
    std::uint32_t version,
    std::uint32_t max_page_count,
    std::uint64_t virtual_base,
    std::uint64_t physical_base
);

}  // namespace fivefury_native::resource
