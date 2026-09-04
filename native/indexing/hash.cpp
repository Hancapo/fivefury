#include "indexing/hash.h"

#include <cstddef>

namespace fivefury_native {

namespace {

std::uint32_t jenk_accumulate(
    std::uint32_t result,
    std::string_view value,
    std::string_view lut,
    std::size_t index,
    bool stop_at_quote
) {
    for (; index < value.size(); ++index) {
        const auto byte = static_cast<unsigned char>(value[index]);
        if (byte == 0U || (stop_at_quote && byte == 34U)) {
            break;
        }
        const auto temp = static_cast<std::uint32_t>(
            1025U * (static_cast<std::uint8_t>(lut[byte]) + result)
        );
        result = ((temp >> 6U) ^ temp) & 0xFFFFFFFFU;
    }
    return result;
}

}  // namespace

std::uint32_t jenk_partial_hash(std::string_view value, std::string_view lut) {
    const bool quoted = !value.empty() && static_cast<unsigned char>(value[0]) == 34U;
    return jenk_accumulate(0, value, lut, quoted ? 1U : 0U, quoted);
}

std::uint32_t jenk_continue_hash(
    std::uint32_t partial_hash,
    std::string_view value,
    std::string_view lut
) {
    return jenk_accumulate(partial_hash, value, lut, 0, false);
}

std::uint32_t jenk_finalize_hash(std::uint32_t partial_hash) {
    const auto tail = static_cast<std::uint32_t>(9U * partial_hash);
    return static_cast<std::uint32_t>(
        32769U * (((tail >> 11U) ^ tail) & 0xFFFFFFFFU)
    );
}

std::uint32_t jenk_hash(std::string_view value, std::string_view lut) {
    return jenk_finalize_hash(jenk_partial_hash(value, lut));
}

}  // namespace fivefury_native
