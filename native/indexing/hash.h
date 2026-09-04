#pragma once

#include <cstdint>
#include <string_view>

namespace fivefury_native {

std::uint32_t jenk_partial_hash(std::string_view value, std::string_view lut);
std::uint32_t jenk_continue_hash(
    std::uint32_t partial_hash,
    std::string_view value,
    std::string_view lut
);
std::uint32_t jenk_finalize_hash(std::uint32_t partial_hash);
std::uint32_t jenk_hash(std::string_view value, std::string_view lut);

}  // namespace fivefury_native
