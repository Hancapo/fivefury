#pragma once

#include <cstddef>
#include <cstdint>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace fivefury_native {

class TextureIndex {
public:
    std::uint32_t add(std::uint32_t texture_hash, std::uint32_t dictionary_id);
    std::uint32_t add_many(
        const std::vector<std::uint32_t>& texture_hashes,
        std::uint32_t dictionary_id
    );
    void clear();
    std::size_t count() const noexcept;
    std::vector<std::uint32_t> find_texture(std::uint32_t texture_hash) const;
    std::vector<std::uint32_t> find_dictionary(std::uint32_t dictionary_id) const;

private:
    mutable std::mutex mutex_;
    std::uint32_t count_ = 0;
    std::unordered_map<std::uint32_t, std::vector<std::uint32_t>> texture_to_ids_;
    std::unordered_map<std::uint32_t, std::vector<std::uint32_t>> dictionary_to_ids_;
};

}  // namespace fivefury_native
