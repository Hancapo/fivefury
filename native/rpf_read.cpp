#include "rpf_archive.h"

#include <filesystem>
#include <stdexcept>

namespace fivefury_native {

std::vector<std::uint8_t> read_rpf_entry(
    const std::string& path,
    const std::string& entry_path,
    const std::string& hash_lut,
    const NativeCryptoContext* crypto,
    const RpfReadMode mode
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
        {},
    };
    const auto resolved = rpf_internal::resolve_entry(reader, archive, entry_path, crypto, hash_lut);
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
    const NativeCryptoContext* crypto
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
        {},
    };
    const auto resolved = rpf_internal::resolve_entry(reader, archive, entry_path, crypto, hash_lut);
    auto raw = rpf_internal::read_resolved_entry_raw(reader, resolved);
    auto standalone = rpf_internal::build_resolved_entry_standalone(raw, resolved, crypto, hash_lut);
    return RpfReadVariants{std::move(raw), std::move(standalone)};
}

}  // namespace fivefury_native
