#pragma once

#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace fivefury_native {

struct AssetRecordData {
    std::string path;
    std::int32_t kind = 0;
    std::uint64_t size = 0;
    std::uint64_t uncompressed_size = 0;
    std::uint8_t flags = 0;
    std::uint32_t archive_encryption = 0;
    std::uint32_t name_hash = 0;
    std::uint32_t short_hash = 0;
};

class CompactIndex {
public:
    CompactIndex() = default;

    void clear();
    std::size_t count() const noexcept;

    std::uint32_t add(
        std::string path,
        std::int32_t kind,
        std::uint64_t size,
        std::uint64_t uncompressed_size,
        std::uint8_t flags,
        std::uint32_t archive_encryption,
        std::uint32_t name_hash,
        std::uint32_t short_hash
    );

    std::size_t add_many(std::vector<AssetRecordData> records);

    std::optional<std::uint32_t> find_path_id(const std::string& path) const;
    std::vector<std::uint32_t> find_hash_ids(std::uint32_t hash_value) const;
    std::vector<std::uint32_t> find_kind_ids(std::int32_t kind_value) const;

    std::string get_path(std::uint32_t asset_id) const;
    std::int32_t get_kind(std::uint32_t asset_id) const;
    std::uint64_t get_size(std::uint32_t asset_id) const;
    std::uint64_t get_uncompressed_size(std::uint32_t asset_id) const;
    std::uint8_t get_flags(std::uint32_t asset_id) const;
    std::uint32_t get_archive_encryption(std::uint32_t asset_id) const;
    std::uint32_t get_name_hash(std::uint32_t asset_id) const;
    std::uint32_t get_short_hash(std::uint32_t asset_id) const;
    AssetRecordData get_record(std::uint32_t asset_id) const;

    std::vector<std::string> export_paths() const;
    std::vector<std::int32_t> export_kinds() const;
    std::vector<std::uint64_t> export_sizes() const;
    std::vector<std::uint64_t> export_uncompressed_sizes() const;
    std::vector<std::uint8_t> export_flags() const;
    std::vector<std::uint32_t> export_archive_encryptions() const;
    std::vector<std::uint32_t> export_name_hashes() const;
    std::vector<std::uint32_t> export_short_hashes() const;

    void import_columns(
        std::vector<std::string> paths,
        std::vector<std::int32_t> kinds,
        std::vector<std::uint64_t> sizes,
        std::vector<std::uint64_t> uncompressed_sizes,
        std::vector<std::uint8_t> flags,
        std::vector<std::uint32_t> archive_encryptions,
        std::vector<std::uint32_t> name_hashes,
        std::vector<std::uint32_t> short_hashes
    );

private:
    std::uint32_t add_unlocked(AssetRecordData&& record);
    void rebuild_indices_unlocked();

    mutable std::mutex mutex_;
    std::vector<std::string> paths_;
    std::vector<std::int32_t> kinds_;
    std::vector<std::uint64_t> sizes_;
    std::vector<std::uint64_t> uncompressed_sizes_;
    std::vector<std::uint8_t> flags_;
    std::vector<std::uint32_t> archive_encryptions_;
    std::vector<std::uint32_t> name_hashes_;
    std::vector<std::uint32_t> short_hashes_;
    std::unordered_map<std::string, std::uint32_t> path_to_id_;
    std::unordered_map<std::uint32_t, std::vector<std::uint32_t>> hash_to_ids_;
    std::unordered_map<std::int32_t, std::vector<std::uint32_t>> kind_to_ids_;
};

}  // namespace fivefury_native
