#pragma once

#include <filesystem>
#include <string>
#include <string_view>

namespace fivefury_native::filesystem {

inline std::filesystem::path from_utf8(std::string_view text) {
    return std::filesystem::path(std::u8string(text.begin(), text.end()));
}

inline std::string to_utf8(const std::filesystem::path& path) {
    const auto text = path.generic_u8string();
    return {text.begin(), text.end()};
}

}  // namespace fivefury_native::filesystem
