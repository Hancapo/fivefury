#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <string_view>
#include <vector>

#include "rpf_scan.h"

namespace fivefury_native::rpf_internal {

constexpr std::uint32_t RPF_MAGIC = 0x52504637;
constexpr std::uint32_t RPF_BLOCK_SIZE = 512;
constexpr std::uint32_t NONE_ENCRYPTION = 0;
constexpr std::uint32_t OPEN_ENCRYPTION = 0x4E45504F;
constexpr std::uint32_t RSC7_MAGIC = 0x37435352U;

constexpr std::uint8_t FLAG_RESOURCE = 2;
constexpr std::uint8_t FLAG_ENCRYPTED = 4;
constexpr std::uint32_t SKIP_AUDIO = 1U << 0U;
constexpr std::uint32_t SKIP_VEHICLES = 1U << 1U;
constexpr std::uint32_t SKIP_PEDS = 1U << 2U;

enum class EntryType : std::uint8_t {
    Directory = 0,
    Binary = 1,
    Resource = 2,
};

struct EntryDescriptor {
    EntryType type = EntryType::Binary;
    std::string name;
    std::string name_lower;
    std::uint32_t name_offset = 0;
    std::uint32_t entries_index = 0;
    std::uint32_t entries_count = 0;
    std::uint32_t file_offset = 0;
    std::uint32_t file_size = 0;
    std::uint32_t file_uncompressed_size = 0;
    std::uint32_t encryption_type = 0;
    std::uint32_t system_flags = 0;
    std::uint32_t graphics_flags = 0;
    bool is_encrypted = false;

    std::uint32_t binary_size() const noexcept {
        return file_size == 0 ? file_uncompressed_size : file_size;
    }
};

struct FileReader {
    explicit FileReader(const std::filesystem::path& path);
    std::vector<std::uint8_t> read(std::uint64_t absolute_offset, std::size_t count);

    std::ifstream stream;
    std::uint64_t size = 0;
};

struct ArchiveContext {
    std::uint64_t base_offset = 0;
    std::uint64_t archive_size = 0;
    std::string archive_name;
    std::string source_prefix;
};

struct ParsedArchive {
    std::vector<EntryDescriptor> entries;
    std::uint32_t encryption = OPEN_ENCRYPTION;
};

struct ResolvedEntry {
    ArchiveContext archive;
    std::uint32_t archive_encryption = OPEN_ENCRYPTION;
    EntryDescriptor entry;
};

std::string ascii_lower(std::string text);
std::string normalize_path(std::string value);
std::string join_path(std::string_view lhs, std::string_view rhs);
bool ends_with(std::string_view value, std::string_view suffix) noexcept;
bool starts_with(std::string_view value, std::string_view prefix) noexcept;
std::string path_name(std::string_view path);
std::string path_stem(std::string_view path);
std::uint32_t resource_version_from_flags(std::uint32_t system_flags, std::uint32_t graphics_flags) noexcept;
std::uint32_t asset_category_mask(std::string_view normalized_path);
std::uint32_t read_u32_le(const std::uint8_t* data) noexcept;
std::uint64_t read_u64_le(const std::uint8_t* data) noexcept;
void write_u32_le(std::uint32_t value, std::uint8_t* out) noexcept;
std::uint32_t get_resource_size_from_flags(std::uint32_t flags) noexcept;
std::int32_t guess_kind(std::string_view path) noexcept;
void log_scan(ScanLogFn log_fn, void* log_context, std::string_view message);
std::string read_name(const std::vector<std::uint8_t>& names_data, std::uint32_t offset);
bool is_rsc7(const std::vector<std::uint8_t>& data) noexcept;
std::vector<std::string> split_path(std::string_view value);
const EntryDescriptor* find_child_entry(
    const std::vector<EntryDescriptor>& entries,
    std::uint32_t dir_index,
    const std::string& name_lower,
    std::uint32_t& child_index_out
);
ParsedArchive parse_entries(
    FileReader& reader,
    const ArchiveContext& archive,
    const NativeCryptoContext* crypto,
    const std::string& hash_lut
);
ResolvedEntry resolve_entry(
    FileReader& reader,
    const ArchiveContext& root_archive,
    const std::string& entry_path,
    const NativeCryptoContext* crypto,
    const std::string& hash_lut
);
std::uint32_t resolve_resource_size(
    FileReader& reader,
    const ArchiveContext& archive,
    const EntryDescriptor& entry
);
std::vector<std::uint8_t> read_resolved_entry_raw(FileReader& reader, const ResolvedEntry& resolved);
std::vector<std::uint8_t> build_resolved_entry_standalone(
    std::vector<std::uint8_t> raw,
    const ResolvedEntry& resolved,
    const NativeCryptoContext* crypto,
    const std::string& hash_lut
);
std::vector<std::uint8_t> read_resolved_entry_standalone(
    FileReader& reader,
    const ResolvedEntry& resolved,
    const NativeCryptoContext* crypto,
    const std::string& hash_lut
);

}  // namespace fivefury_native::rpf_internal
