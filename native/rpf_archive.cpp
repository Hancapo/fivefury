#include "rpf_archive.h"

#include <algorithm>
#include <cctype>
#include <cstring>
#include <stdexcept>
#include <utility>

namespace fivefury_native::rpf_internal {

std::string ascii_lower(std::string text) {
    for (char& ch : text) {
        ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    }
    return text;
}

std::string normalize_path(std::string value) {
    std::replace(value.begin(), value.end(), '\\', '/');
    while (value.find("//") != std::string::npos) {
        value.replace(value.find("//"), 2, "/");
    }
    while (!value.empty() && value.front() == '/') {
        value.erase(value.begin());
    }
    while (!value.empty() && value.back() == '/') {
        value.pop_back();
    }
    return ascii_lower(std::move(value));
}

std::string join_path(std::string_view lhs, std::string_view rhs) {
    if (lhs.empty()) {
        return std::string(rhs);
    }
    if (rhs.empty()) {
        return std::string(lhs);
    }
    std::string out;
    out.reserve(lhs.size() + rhs.size() + 1);
    out.append(lhs);
    out.push_back('/');
    out.append(rhs);
    return out;
}

bool ends_with(std::string_view value, std::string_view suffix) noexcept {
    return value.size() >= suffix.size() && value.substr(value.size() - suffix.size()) == suffix;
}

bool starts_with(std::string_view value, std::string_view prefix) noexcept {
    return value.size() >= prefix.size() && value.substr(0, prefix.size()) == prefix;
}

std::string path_name(std::string_view path) {
    const auto slash = path.find_last_of('/');
    return slash == std::string_view::npos ? std::string(path) : std::string(path.substr(slash + 1));
}

std::string path_stem(std::string_view path) {
    const auto name = path_name(path);
    const auto dot = name.find_last_of('.');
    return dot == std::string::npos ? name : name.substr(0, dot);
}

std::uint32_t resource_version_from_flags(const std::uint32_t system_flags, const std::uint32_t graphics_flags) noexcept {
    return (((system_flags >> 28U) & 0xFU) << 4U) | ((graphics_flags >> 28U) & 0xFU);
}

std::uint32_t asset_category_mask(std::string_view normalized_path) {
    const auto name = path_name(normalized_path);
    std::uint32_t mask = 0;

    if (
        ends_with(name, ".awc") ||
        ends_with(name, ".rel") ||
        ends_with(name, ".nametable") ||
        normalized_path.find("/audio/") != std::string_view::npos ||
        normalized_path.find("/audioconfig/") != std::string_view::npos ||
        starts_with(name, "audioconfig") ||
        name == "audio_rel.rpf"
    ) {
        mask |= SKIP_AUDIO;
    }

    if (
        name == "vehicles.rpf" ||
        normalized_path.find("/vehicles.rpf/") != std::string_view::npos ||
        normalized_path.find("/vehicles/") != std::string_view::npos ||
        normalized_path.find("/vehiclemods/") != std::string_view::npos ||
        normalized_path.find("/streamedvehicles/") != std::string_view::npos ||
        starts_with(name, "streamedvehicles") ||
        starts_with(name, "vehiclemods") ||
        name == "vehicles.meta" ||
        starts_with(name, "vehiclelayouts") ||
        starts_with(name, "carvariations") ||
        starts_with(name, "carcols") ||
        name == "handling.meta" ||
        name == "vfxvehicleinfo.ymt"
    ) {
        mask |= SKIP_VEHICLES;
    }

    if (
        name == "peds.rpf" ||
        name == "pedprops.rpf" ||
        normalized_path.find("/peds.rpf/") != std::string_view::npos ||
        normalized_path.find("/streamedpeds_") != std::string_view::npos ||
        normalized_path.find("/componentpeds_") != std::string_view::npos ||
        normalized_path.find("/pedprops/") != std::string_view::npos ||
        normalized_path.find("/peds/") != std::string_view::npos ||
        starts_with(name, "streamedpeds_") ||
        starts_with(name, "componentpeds_") ||
        name == "peds.meta" ||
        name == "peds.ymt"
    ) {
        mask |= SKIP_PEDS;
    }

    return mask;
}

std::uint32_t read_u32_le(const std::uint8_t* data) noexcept {
    return static_cast<std::uint32_t>(data[0]) |
           (static_cast<std::uint32_t>(data[1]) << 8U) |
           (static_cast<std::uint32_t>(data[2]) << 16U) |
           (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t read_u64_le(const std::uint8_t* data) noexcept {
    return static_cast<std::uint64_t>(read_u32_le(data)) |
           (static_cast<std::uint64_t>(read_u32_le(data + 4U)) << 32U);
}

void write_u32_le(std::uint32_t value, std::uint8_t* out) noexcept {
    out[0] = static_cast<std::uint8_t>(value & 0xFFU);
    out[1] = static_cast<std::uint8_t>((value >> 8U) & 0xFFU);
    out[2] = static_cast<std::uint8_t>((value >> 16U) & 0xFFU);
    out[3] = static_cast<std::uint8_t>((value >> 24U) & 0xFFU);
}

std::uint32_t get_resource_size_from_flags(std::uint32_t flags) noexcept {
    const std::uint32_t s0 = ((flags >> 27U) & 0x1U) << 0U;
    const std::uint32_t s1 = ((flags >> 26U) & 0x1U) << 1U;
    const std::uint32_t s2 = ((flags >> 25U) & 0x1U) << 2U;
    const std::uint32_t s3 = ((flags >> 24U) & 0x1U) << 3U;
    const std::uint32_t s4 = ((flags >> 17U) & 0x7FU) << 4U;
    const std::uint32_t s5 = ((flags >> 11U) & 0x3FU) << 5U;
    const std::uint32_t s6 = ((flags >> 7U) & 0xFU) << 6U;
    const std::uint32_t s7 = ((flags >> 5U) & 0x3U) << 7U;
    const std::uint32_t s8 = ((flags >> 4U) & 0x1U) << 8U;
    const std::uint32_t base_shift = flags & 0xFU;
    const std::uint32_t base_size = 0x200U << base_shift;
    return base_size * (s0 + s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8);
}

std::int32_t guess_kind(std::string_view path) noexcept {
    constexpr std::int32_t UNKNOWN = -1;
    constexpr std::int32_t YDD = 0;
    constexpr std::int32_t YDR = 1;
    constexpr std::int32_t YFT = 2;
    constexpr std::int32_t YMAP = 3;
    constexpr std::int32_t YMF = 4;
    constexpr std::int32_t YMT = 5;
    constexpr std::int32_t YTD = 6;
    constexpr std::int32_t YTYP = 7;
    constexpr std::int32_t YBN = 8;
    constexpr std::int32_t YCD = 9;
    constexpr std::int32_t YPT = 10;
    constexpr std::int32_t YND = 11;
    constexpr std::int32_t YNV = 12;
    constexpr std::int32_t REL = 13;
    constexpr std::int32_t YWR = 14;
    constexpr std::int32_t YVR = 15;
    constexpr std::int32_t GTXD = 16;
    constexpr std::int32_t AWC = 17;
    constexpr std::int32_t YED = 25;
    constexpr std::int32_t YLD = 26;
    constexpr std::int32_t YFD = 27;
    constexpr std::int32_t MRF = 30;
    constexpr std::int32_t YPDB = 32;
    constexpr std::int32_t CUT = 33;
    constexpr std::int32_t RPF = 100;

    const auto dot = path.find_last_of('.');
    if (dot == std::string_view::npos) {
        return UNKNOWN;
    }
    const auto ext = path.substr(dot);
    if (ext == ".ymap") return YMAP;
    if (ext == ".ymf") return YMF;
    if (ext == ".ymt") return YMT;
    if (ext == ".ytyp") return YTYP;
    if (ext == ".ytd") return YTD;
    if (ext == ".ydr") return YDR;
    if (ext == ".ydd") return YDD;
    if (ext == ".yft") return YFT;
    if (ext == ".ybn") return YBN;
    if (ext == ".ycd") return YCD;
    if (ext == ".ypt") return YPT;
    if (ext == ".ynd") return YND;
    if (ext == ".ynv") return YNV;
    if (ext == ".rel") return REL;
    if (ext == ".ywr") return YWR;
    if (ext == ".yvr") return YVR;
    if (ext == ".gxt2") return GTXD;
    if (ext == ".awc") return AWC;
    if (ext == ".yed") return YED;
    if (ext == ".yld") return YLD;
    if (ext == ".yfd") return YFD;
    if (ext == ".mrf") return MRF;
    if (ext == ".ypdb") return YPDB;
    if (ext == ".cut") return CUT;
    if (ext == ".rpf") return RPF;
    return UNKNOWN;
}

void log_scan(ScanLogFn log_fn, void* log_context, std::string_view message) {
    if (log_fn == nullptr) {
        return;
    }
    log_fn(log_context, message.data(), message.size());
}

FileReader::FileReader(const std::filesystem::path& path)
    : stream(path, std::ios::binary), size(std::filesystem::file_size(path)) {
    if (!stream) {
        throw std::runtime_error("failed to open archive");
    }
}

std::vector<std::uint8_t> FileReader::read(std::uint64_t absolute_offset, std::size_t count) {
    std::vector<std::uint8_t> buffer(count);
    if (count == 0) {
        return buffer;
    }
    stream.seekg(static_cast<std::streamoff>(absolute_offset), std::ios::beg);
    if (!stream) {
        throw std::runtime_error("failed to seek archive");
    }
    stream.read(reinterpret_cast<char*>(buffer.data()), static_cast<std::streamsize>(count));
    if (static_cast<std::size_t>(stream.gcount()) != count) {
        throw std::runtime_error("truncated archive");
    }
    return buffer;
}

std::string read_name(const std::vector<std::uint8_t>& names_data, std::uint32_t offset) {
    if (offset >= names_data.size()) {
        return {};
    }
    const auto begin = reinterpret_cast<const char*>(names_data.data() + offset);
    const auto available = names_data.size() - offset;
    const auto end = static_cast<const char*>(std::memchr(begin, 0, available));
    if (end == nullptr) {
        return std::string(begin, available);
    }
    return std::string(begin, static_cast<std::size_t>(end - begin));
}

ParsedArchive parse_entries(
    FileReader& reader,
    const ArchiveContext& archive,
    const NativeCryptoContext* crypto,
    const std::string& hash_lut
) {
    const auto header = reader.read(archive.base_offset, 16U);
    const auto version = read_u32_le(header.data());
    const auto entry_count = read_u32_le(header.data() + 4U);
    const auto names_length = read_u32_le(header.data() + 8U);
    const auto encryption = read_u32_le(header.data() + 12U);
    if (version != RPF_MAGIC) {
        throw std::runtime_error("invalid RPF7 magic");
    }

    const auto entries_size = static_cast<std::size_t>(entry_count) * 16U;
    auto entries_data = reader.read(archive.base_offset + 16U, entries_size);
    auto names_data = reader.read(archive.base_offset + 16U + entries_size, names_length);
    if (encryption != NONE_ENCRYPTION && encryption != OPEN_ENCRYPTION) {
        if (crypto == nullptr) {
            throw std::runtime_error("encrypted archive requires crypto");
        }
        entries_data = crypto->decrypt_archive_table(
            entries_data,
            encryption,
            archive.archive_name,
            static_cast<std::uint32_t>(archive.archive_size),
            hash_lut
        );
        names_data = crypto->decrypt_archive_table(
            names_data,
            encryption,
            archive.archive_name,
            static_cast<std::uint32_t>(archive.archive_size),
            hash_lut
        );
    }

    std::vector<EntryDescriptor> entries(entry_count);
    for (std::uint32_t i = 0; i < entry_count; ++i) {
        const auto* blob = entries_data.data() + (static_cast<std::size_t>(i) * 16U);
        const auto first = read_u32_le(blob);
        const auto second = read_u32_le(blob + 4U);
        auto& entry = entries[i];
        if (second == 0x7FFFFF00U) {
            entry.type = EntryType::Directory;
            entry.name_offset = first & 0xFFFFU;
            entry.entries_index = read_u32_le(blob + 8U);
            entry.entries_count = read_u32_le(blob + 12U);
        } else if ((second & 0x80000000U) == 0U) {
            const auto low = read_u64_le(blob);
            entry.type = EntryType::Binary;
            entry.name_offset = static_cast<std::uint32_t>(low & 0xFFFFU);
            entry.file_size = static_cast<std::uint32_t>((low >> 16U) & 0xFFFFFFU);
            entry.file_offset = static_cast<std::uint32_t>((low >> 40U) & 0xFFFFFFU);
            entry.file_uncompressed_size = read_u32_le(blob + 8U);
            entry.encryption_type = read_u32_le(blob + 12U);
        } else {
            entry.type = EntryType::Resource;
            entry.name_offset = static_cast<std::uint32_t>(blob[0] | (blob[1] << 8U));
            entry.file_size = static_cast<std::uint32_t>(blob[2] | (blob[3] << 8U) | (blob[4] << 16U));
            entry.file_offset = static_cast<std::uint32_t>(blob[5] | (blob[6] << 8U) | (blob[7] << 16U)) & 0x7FFFFFU;
            entry.system_flags = read_u32_le(blob + 8U);
            entry.graphics_flags = read_u32_le(blob + 12U);
        }
        entry.name = read_name(names_data, entry.name_offset);
        entry.name_lower = ascii_lower(entry.name);
        entry.is_encrypted = entry.encryption_type == 1U || ends_with(entry.name_lower, ".ysc");
    }
    if (entries.empty() || entries.front().type != EntryType::Directory) {
        throw std::runtime_error("root RPF entry must be a directory");
    }
    entries.front().name.clear();
    entries.front().name_lower.clear();
    return ParsedArchive{std::move(entries), encryption};
}

bool is_rsc7(const std::vector<std::uint8_t>& data) noexcept {
    return data.size() >= 4U && read_u32_le(data.data()) == RSC7_MAGIC;
}

std::vector<std::string> split_path(std::string_view value) {
    std::vector<std::string> parts;
    std::size_t start = 0;
    while (start < value.size()) {
        const auto end = value.find('/', start);
        if (end == std::string_view::npos) {
            if (start < value.size()) {
                parts.emplace_back(value.substr(start));
            }
            break;
        }
        if (end > start) {
            parts.emplace_back(value.substr(start, end - start));
        }
        start = end + 1U;
    }
    return parts;
}

const EntryDescriptor* find_child_entry(
    const std::vector<EntryDescriptor>& entries,
    const std::uint32_t dir_index,
    const std::string& name_lower,
    std::uint32_t& child_index_out
) {
    const auto& dir = entries.at(dir_index);
    const auto start = dir.entries_index;
    const auto end = std::min<std::uint32_t>(start + dir.entries_count, static_cast<std::uint32_t>(entries.size()));
    for (std::uint32_t i = start; i < end; ++i) {
        if (entries[i].name_lower == name_lower) {
            child_index_out = i;
            return &entries[i];
        }
    }
    return nullptr;
}

ResolvedEntry resolve_entry(
    FileReader& reader,
    const ArchiveContext& root_archive,
    const std::string& entry_path,
    const NativeCryptoContext* crypto,
    const std::string& hash_lut
) {
    const auto normalized = normalize_path(entry_path);
    if (normalized.empty()) {
        throw std::invalid_argument("entry path must not be empty");
    }
    const auto segments = split_path(normalized);
    ArchiveContext current_archive = root_archive;
    std::size_t segment_index = 0;

    while (true) {
        const auto parsed = parse_entries(reader, current_archive, crypto, hash_lut);
        const auto& entries = parsed.entries;
        std::uint32_t dir_index = 0U;

        while (segment_index < segments.size()) {
            std::uint32_t child_index = 0U;
            const auto* child = find_child_entry(entries, dir_index, segments[segment_index], child_index);
            if (child == nullptr) {
                throw std::runtime_error("entry not found");
            }
            if (child->type == EntryType::Directory) {
                dir_index = child_index;
                ++segment_index;
                continue;
            }
            if ((segment_index + 1U) == segments.size()) {
                return ResolvedEntry{current_archive, parsed.encryption, *child};
            }
            if (child->type != EntryType::Binary || !ends_with(child->name_lower, ".rpf")) {
                throw std::runtime_error("entry path descends into a non-archive file");
            }
            current_archive = ArchiveContext{
                current_archive.base_offset + (static_cast<std::uint64_t>(child->file_offset) * RPF_BLOCK_SIZE),
                child->binary_size(),
                child->name,
                join_path(current_archive.source_prefix, child->name_lower),
            };
            ++segment_index;
            break;
        }
        if (segment_index >= segments.size()) {
            throw std::runtime_error("entry path points to a directory");
        }
    }
}

std::uint32_t resolve_resource_size(
    FileReader& reader,
    const ArchiveContext& archive,
    const EntryDescriptor& entry
) {
    if (entry.file_size == 0U) {
        return get_resource_size_from_flags(entry.system_flags) + get_resource_size_from_flags(entry.graphics_flags);
    }
    if (entry.file_size != 0xFFFFFFU) {
        return entry.file_size;
    }
    const auto header = reader.read(archive.base_offset + (static_cast<std::uint64_t>(entry.file_offset) * RPF_BLOCK_SIZE), 16U);
    return static_cast<std::uint32_t>(header[7]) |
           (static_cast<std::uint32_t>(header[14]) << 8U) |
           (static_cast<std::uint32_t>(header[5]) << 16U) |
           (static_cast<std::uint32_t>(header[2]) << 24U);
}

std::vector<std::uint8_t> read_resolved_entry_raw(FileReader& reader, const ResolvedEntry& resolved) {
    const auto& entry = resolved.entry;
    const auto size = entry.type == EntryType::Resource
        ? resolve_resource_size(reader, resolved.archive, entry)
        : entry.binary_size();
    if (size == 0U) {
        return {};
    }
    return reader.read(
        resolved.archive.base_offset + (static_cast<std::uint64_t>(entry.file_offset) * RPF_BLOCK_SIZE),
        static_cast<std::size_t>(size)
    );
}

std::vector<std::uint8_t> build_resolved_entry_standalone(
    std::vector<std::uint8_t> raw,
    const ResolvedEntry& resolved,
    const NativeCryptoContext* crypto,
    const std::string& hash_lut
) {
    const auto& entry = resolved.entry;
    if (entry.type == EntryType::Resource) {
        if (is_rsc7(raw)) {
            return raw;
        }
        std::vector<std::uint8_t> payload;
        if (raw.size() > 16U) {
            payload.assign(raw.begin() + 16, raw.end());
        }
        if (entry.is_encrypted) {
            if (crypto == nullptr) {
                throw std::runtime_error("encrypted resource requires crypto");
            }
            payload = crypto->decrypt_data(
                payload,
                resolved.archive_encryption,
                entry.name,
                entry.file_size,
                hash_lut
            );
        }
        std::vector<std::uint8_t> out(16U + payload.size());
        write_u32_le(RSC7_MAGIC, out.data());
        write_u32_le(resource_version_from_flags(entry.system_flags, entry.graphics_flags), out.data() + 4U);
        write_u32_le(entry.system_flags, out.data() + 8U);
        write_u32_le(entry.graphics_flags, out.data() + 12U);
        std::copy(payload.begin(), payload.end(), out.begin() + 16U);
        return out;
    }
    if (entry.is_encrypted) {
        if (crypto == nullptr) {
            throw std::runtime_error("encrypted entry requires crypto");
        }
        return crypto->decrypt_data(raw, resolved.archive_encryption, entry.name, entry.file_uncompressed_size, hash_lut);
    }
    return raw;
}

std::vector<std::uint8_t> read_resolved_entry_standalone(
    FileReader& reader,
    const ResolvedEntry& resolved,
    const NativeCryptoContext* crypto,
    const std::string& hash_lut
) {
    return build_resolved_entry_standalone(read_resolved_entry_raw(reader, resolved), resolved, crypto, hash_lut);
}

}  // namespace fivefury_native::rpf_internal
