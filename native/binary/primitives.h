#pragma once

#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <type_traits>

namespace fivefury_native::binary {

template <typename T, std::endian Order = std::endian::little>
T load(const void* source) noexcept {
    static_assert(std::is_arithmetic_v<T>);
    std::array<std::byte, sizeof(T)> bytes;
    std::memcpy(bytes.data(), source, sizeof(T));
    if constexpr (Order != std::endian::native) std::reverse(bytes.begin(), bytes.end());
    return std::bit_cast<T>(bytes);
}

template <typename T, std::endian Order = std::endian::little>
void store(void* destination, T value) noexcept {
    auto bytes = std::bit_cast<std::array<std::byte, sizeof(T)>>(value);
    if constexpr (Order != std::endian::native) std::reverse(bytes.begin(), bytes.end());
    std::memcpy(destination, bytes.data(), sizeof(T));
}

inline std::size_t checked_product(std::size_t count, std::size_t width) {
    if (width != 0 && count > std::numeric_limits<std::size_t>::max() / width) {
        throw std::overflow_error("binary dimensions overflow address space");
    }
    return count * width;
}

inline bool contains(std::size_t offset, std::size_t length, std::size_t total) noexcept {
    return offset <= total && length <= total - offset;
}

}  // namespace fivefury_native::binary
