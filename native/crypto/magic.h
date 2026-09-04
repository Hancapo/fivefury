#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace fivefury_native {

std::string build_magic_mask(std::int32_t seed, std::size_t length, unsigned int rounds);

}  // namespace fivefury_native
