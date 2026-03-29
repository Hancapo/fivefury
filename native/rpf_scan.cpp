#include "rpf_archive.h"

#include <algorithm>
#include <filesystem>
#include <functional>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace fivefury_native {

std::uint32_t jenk_hash(std::string_view value, std::string_view lut) {
    std::uint32_t result = 0;
    for (const unsigned char byte : value) {
        const auto temp = static_cast<std::uint32_t>(1025U * (static_cast<std::uint8_t>(lut[byte]) + result));
        result = ((temp >> 6U) ^ temp) & 0xFFFFFFFFU;
    }
    const auto tail = static_cast<std::uint32_t>(9U * result);
    return static_cast<std::uint32_t>(32769U * (((tail >> 11U) ^ tail) & 0xFFFFFFFFU));
}

namespace {

void collect_records(
    rpf_internal::FileReader& reader,
    const rpf_internal::ArchiveContext& archive,
    const std::string_view hash_lut,
    const NativeCryptoContext* crypto,
    std::vector<AssetRecordData>& out_records,
    const std::uint32_t skip_mask,
    ScanLogFn log_fn,
    void* log_context
) {
    const auto parsed = rpf_internal::parse_entries(reader, archive, crypto, std::string(hash_lut));
    const auto encryption = parsed.encryption;
    const auto& entries = parsed.entries;

    std::function<void(std::uint32_t, std::string_view)> walk_dir;
    walk_dir = [&](std::uint32_t dir_index, std::string_view prefix) {
        const auto& dir = entries.at(dir_index);
        const auto start = dir.entries_index;
        const auto end = std::min<std::uint32_t>(start + dir.entries_count, static_cast<std::uint32_t>(entries.size()));
        for (std::uint32_t i = start; i < end; ++i) {
            const auto& child = entries[i];
            const auto archive_path = rpf_internal::join_path(prefix, child.name_lower);
            const auto logical_path = rpf_internal::normalize_path(rpf_internal::join_path(archive.source_prefix, archive_path));
            const auto category_mask = rpf_internal::asset_category_mask(logical_path);
            if (child.type == rpf_internal::EntryType::Directory) {
                if ((category_mask & skip_mask) != 0U) {
                    rpf_internal::log_scan(log_fn, log_context, std::string("[GameFileCache] skip dir ") + logical_path);
                    continue;
                }
                walk_dir(i, archive_path);
                continue;
            }

            if ((category_mask & skip_mask) != 0U) {
                if (child.type == rpf_internal::EntryType::Binary && rpf_internal::ends_with(child.name_lower, ".rpf")) {
                    rpf_internal::log_scan(log_fn, log_context, std::string("[GameFileCache] skip archive subtree ") + logical_path);
                } else {
                    rpf_internal::log_scan(log_fn, log_context, std::string("[GameFileCache] skip asset ") + logical_path);
                }
                continue;
            }

            std::uint64_t size = 0;
            std::uint64_t uncompressed_size = 0;
            std::uint8_t flags = 0;
            if (child.type == rpf_internal::EntryType::Resource) {
                size = rpf_internal::resolve_resource_size(reader, archive, child);
                uncompressed_size = size;
                flags |= rpf_internal::FLAG_RESOURCE;
            } else {
                size = child.binary_size();
                uncompressed_size = child.file_uncompressed_size == 0U ? size : child.file_uncompressed_size;
            }
            if (child.is_encrypted) {
                flags |= rpf_internal::FLAG_ENCRYPTED;
            }
            const auto lower_name = rpf_internal::ascii_lower(rpf_internal::path_name(logical_path));
            const auto stem = rpf_internal::ascii_lower(rpf_internal::path_stem(lower_name));
            rpf_internal::log_scan(log_fn, log_context, std::string("[GameFileCache] scan asset ") + logical_path);
            out_records.push_back(AssetRecordData{
                logical_path,
                rpf_internal::guess_kind(logical_path),
                size,
                uncompressed_size,
                flags,
                encryption,
                jenk_hash(lower_name, hash_lut),
                jenk_hash(stem, hash_lut),
            });

            if (child.type == rpf_internal::EntryType::Binary && rpf_internal::ends_with(child.name_lower, ".rpf")) {
                try {
                    const rpf_internal::ArchiveContext nested{
                        archive.base_offset + (static_cast<std::uint64_t>(child.file_offset) * rpf_internal::RPF_BLOCK_SIZE),
                        child.binary_size(),
                        child.name,
                        logical_path,
                    };
                    collect_records(reader, nested, hash_lut, crypto, out_records, skip_mask, log_fn, log_context);
                } catch (...) {
                }
            }
        }
    };

    walk_dir(0U, {});
}

}  // namespace

std::size_t scan_rpf_into_index(
    CompactIndex& index,
    const std::string& path,
    const std::string& source_prefix,
    const std::string& hash_lut,
    const NativeCryptoContext* crypto,
    const std::uint32_t skip_mask,
    ScanLogFn log_fn,
    void* log_context
) {
    if (hash_lut.size() != 256U) {
        throw std::invalid_argument("hash LUT must contain 256 bytes");
    }
    const auto fs_path = std::filesystem::path(path);
    rpf_internal::FileReader reader(fs_path);
    const rpf_internal::ArchiveContext archive{
        0U,
        reader.size,
        fs_path.filename().string(),
        rpf_internal::normalize_path(source_prefix),
    };
    std::vector<AssetRecordData> records;
    records.reserve(4096U);
    collect_records(reader, archive, hash_lut, crypto, records, skip_mask, log_fn, log_context);
    return index.add_many(std::move(records));
}

}  // namespace fivefury_native
