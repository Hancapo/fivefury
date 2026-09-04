#include "rpf/archive.h"
#include "filesystem/path.h"

#include <filesystem>
#include <stdexcept>

namespace fivefury_native {

std::unique_lock<std::mutex> rpf_internal::ReadCache::prepare(
    const std::filesystem::path& path, std::uint64_t current_size
) {
    std::unique_lock<std::mutex> lock(mutex);
    const auto current_modified = std::filesystem::last_write_time(path);
    if (size != current_size || modified != current_modified) {
        tables.clear();
        size = current_size;
        modified = current_modified;
    }
    return lock;
}

std::vector<std::uint8_t> read_rpf_entry(
    const std::string& path,
    const std::string& entry_path,
    const std::string& hash_lut,
    const NativeCryptoContext* crypto,
    const RpfReadMode mode,
    rpf_internal::ReadCache* cache
) {
    if (hash_lut.size() != 256U) {
        throw std::invalid_argument("hash LUT must contain 256 bytes");
    }
    const auto fs_path = filesystem::from_utf8(path);
    rpf_internal::FileReader reader(fs_path);
    auto lock = cache == nullptr ? std::unique_lock<std::mutex>() : cache->prepare(fs_path, reader.size);
    const rpf_internal::ArchiveContext archive{
        0U,
        reader.size,
        filesystem::to_utf8(fs_path.filename()),
        {},
    };
    const auto resolved = rpf_internal::resolve_entry(reader, archive, entry_path, crypto, hash_lut, cache);
    const auto raw = rpf_internal::read_resolved_entry_raw(reader, resolved);
    if (mode == RpfReadMode::Stored) {
        return raw;
    }
    return rpf_internal::build_resolved_entry_standalone(raw, resolved, crypto, hash_lut);
}

RpfReadVariants read_rpf_entry_variants(
    const std::string& path,
    const std::string& entry_path,
    const std::string& hash_lut,
    const NativeCryptoContext* crypto,
    rpf_internal::ReadCache* cache
) {
    if (hash_lut.size() != 256U) {
        throw std::invalid_argument("hash LUT must contain 256 bytes");
    }
    const auto fs_path = filesystem::from_utf8(path);
    rpf_internal::FileReader reader(fs_path);
    auto lock = cache == nullptr ? std::unique_lock<std::mutex>() : cache->prepare(fs_path, reader.size);
    const rpf_internal::ArchiveContext archive{
        0U,
        reader.size,
        filesystem::to_utf8(fs_path.filename()),
        {},
    };
    const auto resolved = rpf_internal::resolve_entry(reader, archive, entry_path, crypto, hash_lut, cache);
    auto raw = rpf_internal::read_resolved_entry_raw(reader, resolved);
    auto standalone = rpf_internal::build_resolved_entry_standalone(raw, resolved, crypto, hash_lut);
    return RpfReadVariants{std::move(raw), std::move(standalone)};
}

}  // namespace fivefury_native
