#include "texture_index.h"

#include <limits>
#include <stdexcept>

namespace fivefury_native {

std::uint32_t TextureIndex::add(
    const std::uint32_t texture_hash,
    const std::uint32_t dictionary_id
) {
    std::lock_guard lock(mutex_);
    if (count_ == std::numeric_limits<std::uint32_t>::max()) {
        throw std::overflow_error("texture index exceeds uint32 capacity");
    }
    const auto id = count_++;
    texture_to_ids_[texture_hash].push_back(id);
    dictionary_to_ids_[dictionary_id].push_back(id);
    return id;
}

void TextureIndex::clear() {
    std::lock_guard lock(mutex_);
    count_ = 0;
    texture_to_ids_.clear();
    dictionary_to_ids_.clear();
}

std::size_t TextureIndex::count() const noexcept {
    std::lock_guard lock(mutex_);
    return count_;
}

std::vector<std::uint32_t> TextureIndex::find_texture(const std::uint32_t texture_hash) const {
    std::lock_guard lock(mutex_);
    const auto match = texture_to_ids_.find(texture_hash);
    return match == texture_to_ids_.end() ? std::vector<std::uint32_t>{} : match->second;
}

std::vector<std::uint32_t> TextureIndex::find_dictionary(const std::uint32_t dictionary_id) const {
    std::lock_guard lock(mutex_);
    const auto match = dictionary_to_ids_.find(dictionary_id);
    return match == dictionary_to_ids_.end() ? std::vector<std::uint32_t>{} : match->second;
}

}  // namespace fivefury_native
