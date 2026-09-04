#include "indexing/compact_index.h"

#include <algorithm>
#include <stdexcept>
#include <unordered_set>

namespace fivefury_native {

namespace {

template <typename T>
T checked_at(const std::vector<T>& values, std::uint32_t index) {
    if (index >= values.size()) {
        throw std::out_of_range("asset id out of range");
    }
    return values[index];
}

}  // namespace

void CompactIndex::clear() {
    std::lock_guard<std::mutex> lock(mutex_);
    paths_.clear();
    kinds_.clear();
    sizes_.clear();
    uncompressed_sizes_.clear();
    flags_.clear();
    archive_encryptions_.clear();
    name_hashes_.clear();
    short_hashes_.clear();
    path_to_id_.clear();
    hash_to_ids_.clear();
    kind_to_ids_.clear();
    container_to_ids_.clear();
}

std::size_t CompactIndex::count() const noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    return paths_.size();
}

std::uint32_t CompactIndex::add(
    std::string path,
    std::int32_t kind,
    std::uint64_t size,
    std::uint64_t uncompressed_size,
    std::uint8_t flags,
    std::uint32_t archive_encryption,
    std::uint32_t name_hash,
    std::uint32_t short_hash
) {
    std::lock_guard<std::mutex> lock(mutex_);
    return add_unlocked(AssetRecordData{
        std::move(path),
        kind,
        size,
        uncompressed_size,
        flags,
        archive_encryption,
        name_hash,
        short_hash,
    });
}

std::size_t CompactIndex::add_many(std::vector<AssetRecordData> records) {
    std::lock_guard<std::mutex> lock(mutex_);
    for (auto& record : records) {
        add_unlocked(std::move(record));
    }
    return records.size();
}

std::optional<std::uint32_t> CompactIndex::find_path_id(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto it = path_to_id_.find(path);
    if (it == path_to_id_.end()) {
        return std::nullopt;
    }
    return it->second;
}

std::vector<std::uint32_t> CompactIndex::find_hash_ids(std::uint32_t hash_value) const {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto it = hash_to_ids_.find(hash_value);
    if (it == hash_to_ids_.end()) {
        return {};
    }
    return it->second;
}

std::vector<std::pair<std::uint32_t, std::vector<std::uint32_t>>> CompactIndex::find_hashes_ids(
    const std::vector<std::uint32_t>& hash_values,
    std::optional<std::int32_t> kind_value
) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::pair<std::uint32_t, std::vector<std::uint32_t>>> result;
    result.reserve(hash_values.size());
    for (const auto hash_value : hash_values) {
        std::vector<std::uint32_t> matches;
        const auto found = hash_to_ids_.find(hash_value);
        if (found != hash_to_ids_.end()) {
            matches.reserve(found->second.size());
            for (const auto asset_id : found->second) {
                if (!kind_value.has_value() || checked_at(kinds_, asset_id) == kind_value.value()) {
                    matches.push_back(asset_id);
                }
            }
        }
        result.emplace_back(hash_value, std::move(matches));
    }
    return result;
}

std::vector<std::uint32_t> CompactIndex::find_kind_ids(std::int32_t kind_value) const {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto it = kind_to_ids_.find(kind_value);
    if (it == kind_to_ids_.end()) {
        return {};
    }
    return it->second;
}

std::vector<std::uint32_t> CompactIndex::find_container_ids(
    const std::string& container,
    bool include_prefixed,
    std::optional<std::int32_t> kind_value
) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::uint32_t> result;
    std::unordered_set<std::uint32_t> seen;
    const auto append = [&](const std::vector<std::uint32_t>& ids) {
        for (const auto asset_id : ids) {
            if (kind_value.has_value() && checked_at(kinds_, asset_id) != kind_value.value()) {
                continue;
            }
            if (seen.insert(asset_id).second) {
                result.push_back(asset_id);
            }
        }
    };
    const auto exact = container_to_ids_.find(container);
    if (exact != container_to_ids_.end()) {
        append(exact->second);
    }
    if (include_prefixed) {
        const auto prefix = container + "_";
        for (const auto& [name, ids] : container_to_ids_) {
            if (name.starts_with(prefix)) {
                append(ids);
            }
        }
    }
    std::sort(result.begin(), result.end());
    return result;
}

std::vector<std::uint32_t> CompactIndex::find_stem_prefix_ids(
    const std::string& prefix,
    std::int32_t kind_value
) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::uint32_t> result;
    const auto found = kind_to_ids_.find(kind_value);
    if (found == kind_to_ids_.end()) {
        return result;
    }
    for (const auto asset_id : found->second) {
        const auto& path = checked_at(paths_, asset_id);
        const auto slash = path.rfind('/');
        const auto name_start = slash == std::string::npos ? 0U : slash + 1U;
        const auto dot = path.rfind('.');
        const auto name_end = dot == std::string::npos || dot < name_start ? path.size() : dot;
        const auto stem = path.substr(name_start, name_end - name_start);
        if (stem.starts_with(prefix)) {
            result.push_back(asset_id);
        }
    }
    return result;
}

std::vector<std::pair<std::uint32_t, std::uint32_t>> CompactIndex::kind_short_hash_pairs(std::int32_t kind_value) const {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto it = kind_to_ids_.find(kind_value);
    if (it == kind_to_ids_.end()) {
        return {};
    }
    std::vector<std::pair<std::uint32_t, std::uint32_t>> pairs;
    pairs.reserve(it->second.size());
    for (const auto asset_id : it->second) {
        pairs.emplace_back(checked_at(short_hashes_, asset_id), asset_id);
    }
    return pairs;
}

std::vector<std::pair<std::int32_t, std::uint32_t>> CompactIndex::kind_counts() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::pair<std::int32_t, std::uint32_t>> counts;
    counts.reserve(kind_to_ids_.size());
    for (const auto& [kind, ids] : kind_to_ids_) {
        counts.emplace_back(kind, static_cast<std::uint32_t>(ids.size()));
    }
    return counts;
}

std::string CompactIndex::get_path(std::uint32_t asset_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return checked_at(paths_, asset_id);
}

std::int32_t CompactIndex::get_kind(std::uint32_t asset_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return checked_at(kinds_, asset_id);
}

std::uint64_t CompactIndex::get_size(std::uint32_t asset_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return checked_at(sizes_, asset_id);
}

std::uint64_t CompactIndex::get_uncompressed_size(std::uint32_t asset_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return checked_at(uncompressed_sizes_, asset_id);
}

std::uint8_t CompactIndex::get_flags(std::uint32_t asset_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return checked_at(flags_, asset_id);
}

std::uint32_t CompactIndex::get_archive_encryption(std::uint32_t asset_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return checked_at(archive_encryptions_, asset_id);
}

std::uint32_t CompactIndex::get_name_hash(std::uint32_t asset_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return checked_at(name_hashes_, asset_id);
}

std::uint32_t CompactIndex::get_short_hash(std::uint32_t asset_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return checked_at(short_hashes_, asset_id);
}

AssetRecordData CompactIndex::get_record(std::uint32_t asset_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return AssetRecordData{
        checked_at(paths_, asset_id),
        checked_at(kinds_, asset_id),
        checked_at(sizes_, asset_id),
        checked_at(uncompressed_sizes_, asset_id),
        checked_at(flags_, asset_id),
        checked_at(archive_encryptions_, asset_id),
        checked_at(name_hashes_, asset_id),
        checked_at(short_hashes_, asset_id),
    };
}

std::vector<std::string> CompactIndex::export_paths() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return paths_;
}

std::vector<std::int32_t> CompactIndex::export_kinds() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return kinds_;
}

std::vector<std::uint64_t> CompactIndex::export_sizes() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return sizes_;
}

std::vector<std::uint64_t> CompactIndex::export_uncompressed_sizes() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return uncompressed_sizes_;
}

std::vector<std::uint8_t> CompactIndex::export_flags() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return flags_;
}

std::vector<std::uint32_t> CompactIndex::export_archive_encryptions() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return archive_encryptions_;
}

std::vector<std::uint32_t> CompactIndex::export_name_hashes() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return name_hashes_;
}

std::vector<std::uint32_t> CompactIndex::export_short_hashes() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return short_hashes_;
}

void CompactIndex::import_columns(
    std::vector<std::string> paths,
    std::vector<std::int32_t> kinds,
    std::vector<std::uint64_t> sizes,
    std::vector<std::uint64_t> uncompressed_sizes,
    std::vector<std::uint8_t> flags,
    std::vector<std::uint32_t> archive_encryptions,
    std::vector<std::uint32_t> name_hashes,
    std::vector<std::uint32_t> short_hashes
) {
    const auto count = paths.size();
    if (kinds.size() != count || sizes.size() != count || uncompressed_sizes.size() != count ||
        flags.size() != count || archive_encryptions.size() != count ||
        name_hashes.size() != count || short_hashes.size() != count) {
        throw std::invalid_argument("column sizes must match");
    }

    std::lock_guard<std::mutex> lock(mutex_);
    paths_ = std::move(paths);
    kinds_ = std::move(kinds);
    sizes_ = std::move(sizes);
    uncompressed_sizes_ = std::move(uncompressed_sizes);
    flags_ = std::move(flags);
    archive_encryptions_ = std::move(archive_encryptions);
    name_hashes_ = std::move(name_hashes);
    short_hashes_ = std::move(short_hashes);
    rebuild_indices_unlocked();
}

std::uint32_t CompactIndex::add_unlocked(AssetRecordData&& record) {
    const auto asset_id = static_cast<std::uint32_t>(paths_.size());
    paths_.push_back(std::move(record.path));
    kinds_.push_back(record.kind);
    sizes_.push_back(record.size);
    uncompressed_sizes_.push_back(record.uncompressed_size);
    flags_.push_back(record.flags);
    archive_encryptions_.push_back(record.archive_encryption);
    name_hashes_.push_back(record.name_hash);
    short_hashes_.push_back(record.short_hash);

    path_to_id_[paths_.back()] = asset_id;
    hash_to_ids_[record.name_hash].push_back(asset_id);
    if (record.short_hash != record.name_hash) {
        hash_to_ids_[record.short_hash].push_back(asset_id);
    }
    kind_to_ids_[record.kind].push_back(asset_id);
    index_containers_unlocked(paths_.back(), asset_id);
    return asset_id;
}

void CompactIndex::index_containers_unlocked(const std::string& path, std::uint32_t asset_id) {
    const auto final_slash = path.rfind('/');
    if (final_slash == std::string::npos) {
        return;
    }
    std::size_t start = 0;
    while (start < final_slash) {
        const auto slash = path.find('/', start);
        const auto end = slash == std::string::npos || slash > final_slash ? final_slash : slash;
        if (end > start) {
            container_to_ids_[path.substr(start, end - start)].push_back(asset_id);
        }
        start = end + 1U;
    }
}

void CompactIndex::rebuild_indices_unlocked() {
    path_to_id_.clear();
    hash_to_ids_.clear();
    kind_to_ids_.clear();
    container_to_ids_.clear();

    for (std::uint32_t asset_id = 0; asset_id < paths_.size(); ++asset_id) {
        path_to_id_[paths_[asset_id]] = asset_id;
        const auto name_hash = name_hashes_[asset_id];
        const auto short_hash = short_hashes_[asset_id];
        hash_to_ids_[name_hash].push_back(asset_id);
        if (short_hash != name_hash) {
            hash_to_ids_[short_hash].push_back(asset_id);
        }
        kind_to_ids_[kinds_[asset_id]].push_back(asset_id);
        index_containers_unlocked(paths_[asset_id], asset_id);
    }
}

}  // namespace fivefury_native
