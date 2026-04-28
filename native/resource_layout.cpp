#include "resource_layout.h"

#include <algorithm>
#include <limits>
#include <stdexcept>

namespace fivefury_native::resource {

namespace {

std::uint64_t align_value(std::uint64_t value, std::uint64_t alignment) {
    return alignment == 0 ? value : ((value + alignment - 1U) / alignment) * alignment;
}

std::uint64_t rsc7_block_pad(std::uint64_t position) {
    return (16U - (position % 16U)) % 16U;
}

std::uint32_t flags_from_page_counts(
    const std::uint32_t page_counts[5],
    std::uint32_t version,
    std::uint32_t base_shift
) {
    std::uint32_t flags = 0;
    flags |= (version & 0xFU) << 28U;
    flags |= (page_counts[0] & 0x7FU) << 17U;
    flags |= (page_counts[1] & 0x3FU) << 11U;
    flags |= (page_counts[2] & 0xFU) << 7U;
    flags |= (page_counts[3] & 0x3U) << 5U;
    flags |= (page_counts[4] & 0x1U) << 4U;
    flags |= base_shift & 0xFU;
    return flags;
}

ResourceSectionLayout assign_section_layout(
    const std::vector<ResourceBlockSpan>& blocks,
    std::uint32_t version,
    std::uint32_t max_page_count,
    bool is_system
) {
    if (blocks.empty()) {
        return ResourceSectionLayout{(version & 0xFU) << 28U, {}};
    }

    std::vector<std::uint64_t> sizes;
    sizes.reserve(blocks.size());
    for (const auto& block : blocks) {
        sizes.push_back(block.size);
    }

    const std::uint64_t max_block_size = *std::max_element(sizes.begin(), sizes.end());
    const std::uint64_t min_block_size = *std::min_element(sizes.begin(), sizes.end());
    std::uint32_t base_shift = 0;
    std::uint64_t base_size = 0x2000U;
    while (((base_size < min_block_size) || ((base_size * 16U) < max_block_size)) && base_shift < 0xFU) {
        ++base_shift;
        base_size = 0x2000ULL << base_shift;
    }
    if ((base_size * 16U) < max_block_size) {
        throw std::invalid_argument("unable to fit the largest resource block into RSC7 page flags");
    }

    std::vector<std::size_t> sorted_indices;
    sorted_indices.reserve(blocks.size());
    const bool has_root = is_system && !blocks.empty();
    for (std::size_t index = 0; index < blocks.size(); ++index) {
        if (has_root && index == 0U) {
            continue;
        }
        sorted_indices.push_back(index);
    }
    std::sort(sorted_indices.begin(), sorted_indices.end(), [&](std::size_t lhs, std::size_t rhs) {
        return sizes[lhs] > sizes[rhs];
    });
    if (has_root) {
        sorted_indices.insert(sorted_indices.begin(), 0U);
    }

    while (true) {
        std::uint32_t page_counts[5] = {0, 0, 0, 0, 0};
        std::vector<std::uint64_t> page_sizes[5];
        std::vector<std::tuple<std::uint32_t, std::uint32_t, std::uint64_t>> block_pages(blocks.size());

        std::uint32_t largest_page_size_index = 0;
        std::uint64_t largest_page_size = base_size;
        while (largest_page_size < max_block_size) {
            ++largest_page_size_index;
            largest_page_size *= 2U;
        }

        for (std::size_t sorted_position = 0; sorted_position < sorted_indices.size(); ++sorted_position) {
            const auto block_index = sorted_indices[sorted_position];
            const auto block_size = sizes[block_index];
            if (sorted_position == 0U) {
                page_sizes[largest_page_size_index].push_back(block_size);
                block_pages[block_index] = {largest_page_size_index, 0U, 0U};
                continue;
            }

            std::uint32_t page_size_index = 0;
            std::uint64_t page_size = base_size;
            while ((block_size > page_size) && (page_size_index < largest_page_size_index)) {
                ++page_size_index;
                page_size *= 2U;
            }

            bool found = false;
            std::uint32_t test_page_size_index = page_size_index;
            std::uint64_t test_page_size = page_size;
            while (!found && test_page_size_index <= largest_page_size_index) {
                auto& pages = page_sizes[test_page_size_index];
                for (std::size_t page_index = 0; page_index < pages.size(); ++page_index) {
                    const auto candidate_offset = pages[page_index] + rsc7_block_pad(pages[page_index]);
                    const auto candidate_size = candidate_offset + block_size;
                    if (candidate_size <= test_page_size) {
                        pages[page_index] = candidate_size;
                        block_pages[block_index] = {
                            test_page_size_index,
                            static_cast<std::uint32_t>(page_index),
                            candidate_offset,
                        };
                        found = true;
                        break;
                    }
                }
                ++test_page_size_index;
                test_page_size *= 2U;
            }
            if (found) {
                continue;
            }

            auto& pages = page_sizes[page_size_index];
            const auto page_index = static_cast<std::uint32_t>(pages.size());
            pages.push_back(block_size);
            block_pages[block_index] = {page_size_index, page_index, 0U};
        }

        std::uint32_t total_page_count = 0;
        for (std::size_t index = 0; index < 5U; ++index) {
            if (page_sizes[index].size() > std::numeric_limits<std::uint32_t>::max()) {
                throw std::overflow_error("too many RSC7 pages");
            }
            page_counts[index] = static_cast<std::uint32_t>(page_sizes[index].size());
            total_page_count += page_counts[index];
        }

        bool test_ok = total_page_count <= max_page_count;
        test_ok = test_ok && page_counts[0] <= 0x7FU;
        test_ok = test_ok && page_counts[1] <= 0x3FU;
        test_ok = test_ok && page_counts[2] <= 0xFU;
        test_ok = test_ok && page_counts[3] <= 0x3U;
        test_ok = test_ok && page_counts[4] <= 0x1U;
        if (!test_ok) {
            if (base_shift >= 0xFU) {
                throw std::invalid_argument("unable to pack resource blocks into RSC7 page flags");
            }
            ++base_shift;
            base_size = 0x2000ULL << base_shift;
            continue;
        }

        std::uint64_t page_offset = 0;
        std::uint64_t page_offsets[5] = {0, 0, 0, 0, 0};
        for (int index = 4; index >= 0; --index) {
            page_offsets[index] = page_offset;
            page_offset += (base_size * (1ULL << index)) * page_counts[index];
        }

        ResourceSectionLayout result;
        result.flags = flags_from_page_counts(page_counts, version, base_shift);
        result.offset_map.reserve(blocks.size());
        for (std::size_t block_index = 0; block_index < blocks.size(); ++block_index) {
            const auto [page_size_index, page_index, offset] = block_pages[block_index];
            const auto page_size = base_size * (1ULL << page_size_index);
            const auto new_offset = page_offsets[page_size_index] + (page_size * page_index) + offset;
            result.offset_map.emplace_back(blocks[block_index].offset, blocks[block_index].size, new_offset);
        }
        return result;
    }
}

std::uint64_t remap_resource_pointer(
    std::uint64_t value,
    std::uint64_t system_base,
    const std::vector<std::tuple<std::uint64_t, std::uint64_t, std::uint64_t>>& system_map,
    std::uint64_t graphics_base,
    const std::vector<std::tuple<std::uint64_t, std::uint64_t, std::uint64_t>>& graphics_map
) {
    if (value == 0U) {
        return value;
    }
    const auto remap_against = [&](std::uint64_t base, const auto& offset_map) -> std::uint64_t {
        if (value < base) {
            return value;
        }
        const auto relative = value - base;
        for (const auto& [old_offset, size, new_offset] : offset_map) {
            if (old_offset <= relative && relative < old_offset + size) {
                return base + new_offset + (relative - old_offset);
            }
        }
        return value;
    };
    const auto system_value = remap_against(system_base, system_map);
    if (system_value != value) {
        return system_value;
    }
    return remap_against(graphics_base, graphics_map);
}

std::uint64_t read_u64_le(const std::string& data, std::uint64_t offset) {
    const auto* ptr = reinterpret_cast<const unsigned char*>(data.data() + offset);
    std::uint64_t value = 0;
    for (int shift = 0; shift < 64; shift += 8) {
        value |= static_cast<std::uint64_t>(ptr[shift / 8]) << shift;
    }
    return value;
}

void write_u64_le(std::string& data, std::uint64_t offset, std::uint64_t value) {
    auto* ptr = reinterpret_cast<unsigned char*>(data.data() + offset);
    for (int shift = 0; shift < 64; shift += 8) {
        ptr[shift / 8] = static_cast<unsigned char>((value >> shift) & 0xFFU);
    }
}

std::string rewrite_resource_pointers(
    std::string data,
    const std::vector<ResourceBlockSpan>& blocks,
    std::uint64_t system_base,
    const std::vector<std::tuple<std::uint64_t, std::uint64_t, std::uint64_t>>& system_map,
    std::uint64_t graphics_base,
    const std::vector<std::tuple<std::uint64_t, std::uint64_t, std::uint64_t>>& graphics_map
) {
    for (const auto& block : blocks) {
        if (block.offset > data.size() || block.size > data.size() - block.offset) {
            throw std::invalid_argument("resource block is out of range");
        }
        if (!block.relocate_pointers) {
            continue;
        }
        const auto start = align_value(block.offset, 8U);
        const auto end = block.offset + block.size;
        if (end <= start + 7U) {
            continue;
        }
        for (std::uint64_t offset = start; offset < end - 7U; offset += 8U) {
            const auto value = read_u64_le(data, offset);
            const auto remapped = remap_resource_pointer(value, system_base, system_map, graphics_base, graphics_map);
            if (remapped != value) {
                write_u64_le(data, offset, remapped);
            }
        }
    }
    return data;
}

std::string apply_section_layout(
    const std::string& data,
    std::uint32_t flags,
    const std::vector<std::tuple<std::uint64_t, std::uint64_t, std::uint64_t>>& offset_map
) {
    const auto target_size = get_resource_size_from_flags_impl(flags);
    if (target_size > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
        throw std::overflow_error("RSC7 section is too large");
    }
    std::string output(static_cast<std::size_t>(target_size), '\0');
    for (const auto& [old_offset, size, new_offset] : offset_map) {
        if (old_offset + size > data.size() || new_offset + size > output.size()) {
            throw std::invalid_argument("resource block is out of range");
        }
        std::copy_n(data.data() + old_offset, static_cast<std::size_t>(size), output.data() + new_offset);
    }
    return output;
}

}  // namespace

std::uint64_t get_resource_size_from_flags_impl(std::uint32_t flags) {
    const std::uint64_t s0 = ((flags >> 27U) & 0x1U) << 0U;
    const std::uint64_t s1 = ((flags >> 26U) & 0x1U) << 1U;
    const std::uint64_t s2 = ((flags >> 25U) & 0x1U) << 2U;
    const std::uint64_t s3 = ((flags >> 24U) & 0x1U) << 3U;
    const std::uint64_t s4 = ((flags >> 17U) & 0x7FU) << 4U;
    const std::uint64_t s5 = ((flags >> 11U) & 0x3FU) << 5U;
    const std::uint64_t s6 = ((flags >> 7U) & 0xFU) << 6U;
    const std::uint64_t s7 = ((flags >> 5U) & 0x3U) << 7U;
    const std::uint64_t s8 = ((flags >> 4U) & 0x1U) << 8U;
    const std::uint64_t base_size = 0x200ULL << (flags & 0xFU);
    return base_size * (s0 + s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8);
}

std::uint32_t get_resource_total_page_count_impl(std::uint32_t flags) {
    return ((flags >> 17U) & 0x7FU) + ((flags >> 11U) & 0x3FU) + ((flags >> 7U) & 0xFU) +
           ((flags >> 5U) & 0x3U) + ((flags >> 4U) & 0x1U) + ((flags >> 24U) & 0x1U) +
           ((flags >> 25U) & 0x1U) + ((flags >> 26U) & 0x1U) + ((flags >> 27U) & 0x1U);
}

ResourceLayoutResult layout_resource_sections_impl(
    const std::string& system_data,
    const std::vector<ResourceBlockSpan>& system_blocks,
    const std::string& graphics_data,
    const std::vector<ResourceBlockSpan>& graphics_blocks,
    std::uint32_t version,
    std::uint32_t max_page_count,
    std::uint64_t virtual_base,
    std::uint64_t physical_base
) {
    const auto system_layout = assign_section_layout(system_blocks, (version >> 4U) & 0xFU, max_page_count, true);
    const auto system_page_count = get_resource_total_page_count_impl(system_layout.flags);
    const auto graphics_layout = assign_section_layout(
        graphics_blocks,
        version & 0xFU,
        max_page_count > system_page_count ? max_page_count - system_page_count : 0U,
        false
    );

    const auto relocated_system = rewrite_resource_pointers(
        system_data,
        system_blocks,
        virtual_base,
        system_layout.offset_map,
        physical_base,
        graphics_layout.offset_map
    );
    const auto relocated_graphics = rewrite_resource_pointers(
        graphics_data,
        graphics_blocks,
        virtual_base,
        system_layout.offset_map,
        physical_base,
        graphics_layout.offset_map
    );

    ResourceLayoutResult result;
    result.system_flags = system_layout.flags;
    result.graphics_flags = graphics_layout.flags;
    result.system_data = apply_section_layout(relocated_system, system_layout.flags, system_layout.offset_map);
    result.graphics_data = apply_section_layout(relocated_graphics, graphics_layout.flags, graphics_layout.offset_map);
    return result;
}

}  // namespace fivefury_native::resource
