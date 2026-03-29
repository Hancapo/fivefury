#include "rpf_scan.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <stdexcept>
#include <string_view>
#include <utility>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#pragma comment(lib, "bcrypt.lib")
#endif

namespace fivefury_native {

namespace {

constexpr std::uint32_t RPF_MAGIC = 0x52504637;
constexpr std::uint32_t RPF_BLOCK_SIZE = 512;
constexpr std::uint32_t NONE_ENCRYPTION = 0;
constexpr std::uint32_t OPEN_ENCRYPTION = 0x4E45504F;
constexpr std::uint32_t AES_ENCRYPTION = 0x0FFFFFF9;
constexpr std::uint32_t NG_ENCRYPTION = 0x0FEFFFFF;
constexpr std::size_t NG_KEYS_SIZE = 27472;
constexpr std::size_t NG_TABLES_SIZE = 278528;
constexpr std::size_t NG_BLOB_SIZE = NG_KEYS_SIZE + NG_TABLES_SIZE;
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
    constexpr std::int32_t RPF = 100;

    const auto dot = path.find_last_of('.');
    if (dot == std::string_view::npos) {
        return UNKNOWN;
    }
    const auto ext = path.substr(dot);
    if (ext == ".ymap") return YMAP;
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
    if (ext == ".rpf") return RPF;
    return UNKNOWN;
}

void log_scan(ScanLogFn log_fn, void* log_context, std::string_view message) {
    if (log_fn == nullptr) {
        return;
    }
    log_fn(log_context, message.data(), message.size());
}

struct FileReader {
    explicit FileReader(const std::filesystem::path& path)
        : stream(path, std::ios::binary), size(std::filesystem::file_size(path)) {
        if (!stream) {
            throw std::runtime_error("failed to open archive");
        }
    }

    std::vector<std::uint8_t> read(std::uint64_t absolute_offset, std::size_t count) {
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

    std::ifstream stream;
    std::uint64_t size = 0;
};

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

struct ArchiveContext {
    std::uint64_t base_offset = 0;
    std::uint64_t archive_size = 0;
    std::string archive_name;
    std::string source_prefix;
};

#ifdef _WIN32
class AesEcbDecryptor {
public:
    explicit AesEcbDecryptor(const std::vector<std::uint8_t>& key_material) {
        check(
            BCryptOpenAlgorithmProvider(&algorithm_, BCRYPT_AES_ALGORITHM, nullptr, 0),
            "BCryptOpenAlgorithmProvider"
        );
        try {
            const wchar_t mode[] = BCRYPT_CHAIN_MODE_ECB;
            check(
                BCryptSetProperty(
                    algorithm_,
                    BCRYPT_CHAINING_MODE,
                    reinterpret_cast<PUCHAR>(const_cast<wchar_t*>(mode)),
                    static_cast<ULONG>(sizeof(mode)),
                    0
                ),
                "BCryptSetProperty"
            );

            ULONG object_length = 0;
            ULONG result_length = 0;
            check(
                BCryptGetProperty(
                    algorithm_,
                    BCRYPT_OBJECT_LENGTH,
                    reinterpret_cast<PUCHAR>(&object_length),
                    sizeof(object_length),
                    &result_length,
                    0
                ),
                "BCryptGetProperty"
            );

            key_object_.resize(object_length);
            key_bytes_ = key_material;
            check(
                BCryptGenerateSymmetricKey(
                    algorithm_,
                    &key_,
                    key_object_.data(),
                    static_cast<ULONG>(key_object_.size()),
                    const_cast<PUCHAR>(key_bytes_.data()),
                    static_cast<ULONG>(key_bytes_.size()),
                    0
                ),
                "BCryptGenerateSymmetricKey"
            );
        } catch (...) {
            close();
            throw;
        }
    }

    AesEcbDecryptor(const AesEcbDecryptor&) = delete;
    AesEcbDecryptor& operator=(const AesEcbDecryptor&) = delete;

    ~AesEcbDecryptor() {
        close();
    }

    std::vector<std::uint8_t> decrypt_aligned(const std::vector<std::uint8_t>& data) const {
        if (data.empty()) {
            return {};
        }
        const auto aligned = data.size() - (data.size() % 16U);
        std::vector<std::uint8_t> out(data.begin(), data.end());
        if (aligned == 0) {
            return out;
        }
        ULONG written = 0;
        check(
            BCryptDecrypt(
                key_,
                const_cast<PUCHAR>(data.data()),
                static_cast<ULONG>(aligned),
                nullptr,
                nullptr,
                0,
                out.data(),
                static_cast<ULONG>(aligned),
                &written,
                0
            ),
            "BCryptDecrypt"
        );
        return out;
    }

private:
    static void check(NTSTATUS status, const char* message) {
        if (status < 0) {
            throw std::runtime_error(std::string(message) + " failed");
        }
    }

    void close() noexcept {
        if (key_ != nullptr) {
            BCryptDestroyKey(key_);
            key_ = nullptr;
        }
        if (algorithm_ != nullptr) {
            BCryptCloseAlgorithmProvider(algorithm_, 0);
            algorithm_ = nullptr;
        }
    }

    BCRYPT_ALG_HANDLE algorithm_ = nullptr;
    BCRYPT_KEY_HANDLE key_ = nullptr;
    std::vector<std::uint8_t> key_object_;
    std::vector<std::uint8_t> key_bytes_;
};
#endif

}  // namespace

std::uint32_t jenk_hash(std::string_view value, std::string_view lut) {
    std::uint32_t result = 0;
    for (const unsigned char byte : value) {
        const auto temp = static_cast<std::uint32_t>(1025U * (static_cast<std::uint8_t>(lut[byte]) + result));
        result = ((temp >> 6U) ^ temp) & 0xFFFFFFFFU;
    }
    const auto tail = static_cast<std::uint32_t>(9U * result);
    return static_cast<std::uint32_t>(32769U * (((tail >> 11U) ^ tail) & 0xFFFFFFFFU));
}

struct NativeCryptoContext::Impl {
    explicit Impl(std::vector<std::uint8_t> aes_key_bytes, std::vector<std::uint8_t> ng_blob_bytes)
#ifdef _WIN32
        : aes(std::make_unique<AesEcbDecryptor>(aes_key_bytes))
#endif
    {
        if (aes_key_bytes.size() != 32U) {
            throw std::invalid_argument("AES key must be 32 bytes");
        }
        if (ng_blob_bytes.size() < NG_BLOB_SIZE) {
            throw std::invalid_argument("NG blob is truncated");
        }
        aes_key = std::move(aes_key_bytes);
        ng_blob = std::move(ng_blob_bytes);
        ng_tables.resize(NG_TABLES_SIZE / sizeof(std::uint32_t));
        const auto* tables_data = ng_blob.data() + NG_KEYS_SIZE;
        for (std::size_t i = 0; i < ng_tables.size(); ++i) {
            ng_tables[i] = read_u32_le(tables_data + (i * 4U));
        }
        ng_subkeys.resize(101U * 17U * 4U);
        for (std::size_t key_index = 0; key_index < 101U; ++key_index) {
            const auto* key_base = ng_blob.data() + (key_index * 272U);
            for (std::size_t round_index = 0; round_index < 17U; ++round_index) {
                const auto* round_base = key_base + (round_index * 16U);
                const auto out_base = ((key_index * 17U) + round_index) * 4U;
                ng_subkeys[out_base + 0U] = read_u32_le(round_base + 0U);
                ng_subkeys[out_base + 1U] = read_u32_le(round_base + 4U);
                ng_subkeys[out_base + 2U] = read_u32_le(round_base + 8U);
                ng_subkeys[out_base + 3U] = read_u32_le(round_base + 12U);
            }
        }
    }

    std::vector<std::uint8_t> decrypt_archive_table(
        const std::vector<std::uint8_t>& data,
        const std::uint32_t encryption,
        const std::string& archive_name,
        const std::uint32_t archive_size,
        const std::string& hash_lut
    ) const {
        if (encryption == NONE_ENCRYPTION || encryption == OPEN_ENCRYPTION) {
            return data;
        }
        if (encryption == AES_ENCRYPTION) {
#ifdef _WIN32
            return aes->decrypt_aligned(data);
#else
            throw std::runtime_error("AES decryption is unavailable");
#endif
        }
        if (encryption != NG_ENCRYPTION) {
            throw std::runtime_error("unsupported RPF encryption");
        }
        return decrypt_ng(data, archive_name, archive_size, hash_lut);
    }

    std::vector<std::uint8_t> decrypt_ng(
        const std::vector<std::uint8_t>& data,
        const std::string& archive_name,
        const std::uint32_t archive_size,
        const std::string& hash_lut
    ) const {
        if (data.empty()) {
            return {};
        }
        std::string seed_name = archive_name;
        const auto key_seed = (jenk_hash(seed_name, hash_lut) + archive_size + 61U) & 0xFFFFFFFFU;
        const auto key_index = static_cast<std::size_t>(key_seed % 0x65U);
        std::vector<std::uint8_t> out(data.begin(), data.end());
        const auto aligned = out.size() - (out.size() % 16U);
        if (aligned == 0) {
            return out;
        }
        const auto subkey_base = key_index * 17U * 4U;
        for (std::size_t offset = 0; offset < aligned; offset += 16U) {
            decrypt_ng_block(
                out.data() + offset,
                &data[offset],
                subkey_base
            );
        }
        return out;
    }

    void decrypt_ng_block(std::uint8_t* out, const std::uint8_t* in, const std::size_t subkey_base) const {
        std::array<std::uint8_t, 16> buffer{};
        std::memcpy(buffer.data(), in, 16U);
        round_a(buffer.data(), subkey_base + 0U * 4U, 0U);
        round_a(buffer.data(), subkey_base + 1U * 4U, 1U);
        for (std::size_t round_index = 2U; round_index < 16U; ++round_index) {
            round_b(buffer.data(), subkey_base + round_index * 4U, round_index);
        }
        round_a(buffer.data(), subkey_base + 16U * 4U, 16U);
        std::memcpy(out, buffer.data(), 16U);
    }

    void round_a(std::uint8_t* block, const std::size_t subkey_offset, const std::size_t round_index) const {
        const auto* subkeys = &ng_subkeys[subkey_offset];
        const auto tbase = round_index * 16U * 256U;
        const auto x1 = table(tbase + 0U * 256U, block[0]) ^ table(tbase + 1U * 256U, block[1]) ^
                        table(tbase + 2U * 256U, block[2]) ^ table(tbase + 3U * 256U, block[3]) ^ subkeys[0];
        const auto x2 = table(tbase + 4U * 256U, block[4]) ^ table(tbase + 5U * 256U, block[5]) ^
                        table(tbase + 6U * 256U, block[6]) ^ table(tbase + 7U * 256U, block[7]) ^ subkeys[1];
        const auto x3 = table(tbase + 8U * 256U, block[8]) ^ table(tbase + 9U * 256U, block[9]) ^
                        table(tbase + 10U * 256U, block[10]) ^ table(tbase + 11U * 256U, block[11]) ^ subkeys[2];
        const auto x4 = table(tbase + 12U * 256U, block[12]) ^ table(tbase + 13U * 256U, block[13]) ^
                        table(tbase + 14U * 256U, block[14]) ^ table(tbase + 15U * 256U, block[15]) ^ subkeys[3];
        write_u32_le(x1, block + 0U);
        write_u32_le(x2, block + 4U);
        write_u32_le(x3, block + 8U);
        write_u32_le(x4, block + 12U);
    }

    void round_b(std::uint8_t* block, const std::size_t subkey_offset, const std::size_t round_index) const {
        const auto* subkeys = &ng_subkeys[subkey_offset];
        const auto tbase = round_index * 16U * 256U;
        const auto x1 = table(tbase + 0U * 256U, block[0]) ^ table(tbase + 7U * 256U, block[7]) ^
                        table(tbase + 10U * 256U, block[10]) ^ table(tbase + 13U * 256U, block[13]) ^ subkeys[0];
        const auto x2 = table(tbase + 1U * 256U, block[1]) ^ table(tbase + 4U * 256U, block[4]) ^
                        table(tbase + 11U * 256U, block[11]) ^ table(tbase + 14U * 256U, block[14]) ^ subkeys[1];
        const auto x3 = table(tbase + 2U * 256U, block[2]) ^ table(tbase + 5U * 256U, block[5]) ^
                        table(tbase + 8U * 256U, block[8]) ^ table(tbase + 15U * 256U, block[15]) ^ subkeys[2];
        const auto x4 = table(tbase + 3U * 256U, block[3]) ^ table(tbase + 6U * 256U, block[6]) ^
                        table(tbase + 9U * 256U, block[9]) ^ table(tbase + 12U * 256U, block[12]) ^ subkeys[3];
        write_u32_le(x1, block + 0U);
        write_u32_le(x2, block + 4U);
        write_u32_le(x3, block + 8U);
        write_u32_le(x4, block + 12U);
    }

    std::uint32_t table(const std::size_t base, const std::uint8_t index) const noexcept {
        return ng_tables[base + index];
    }

    std::vector<std::uint8_t> aes_key;
    std::vector<std::uint8_t> ng_blob;
    std::vector<std::uint32_t> ng_tables;
    std::vector<std::uint32_t> ng_subkeys;
#ifdef _WIN32
    std::unique_ptr<AesEcbDecryptor> aes;
#endif
};

NativeCryptoContext::NativeCryptoContext(std::vector<std::uint8_t> aes_key, std::vector<std::uint8_t> ng_blob)
    : impl_(std::make_unique<Impl>(std::move(aes_key), std::move(ng_blob))) {
}

NativeCryptoContext::NativeCryptoContext(NativeCryptoContext&& other) noexcept = default;
NativeCryptoContext& NativeCryptoContext::operator=(NativeCryptoContext&& other) noexcept = default;
NativeCryptoContext::~NativeCryptoContext() = default;

bool NativeCryptoContext::can_decrypt() const noexcept {
    return impl_ != nullptr;
}

std::vector<std::uint8_t> NativeCryptoContext::decrypt_archive_table(
    const std::vector<std::uint8_t>& data,
    const std::uint32_t encryption,
    const std::string& archive_name,
    const std::uint32_t archive_size,
    const std::string& hash_lut
) const {
    if (impl_ == nullptr) {
        throw std::runtime_error("crypto context is not initialized");
    }
    return impl_->decrypt_archive_table(data, encryption, archive_name, archive_size, hash_lut);
}

std::vector<std::uint8_t> NativeCryptoContext::decrypt_data(
    const std::vector<std::uint8_t>& data,
    const std::uint32_t encryption,
    const std::string& entry_name,
    const std::uint32_t entry_length,
    const std::string& hash_lut
) const {
    if (impl_ == nullptr) {
        throw std::runtime_error("crypto context is not initialized");
    }
    if (data.empty()) {
        return {};
    }
    if (encryption == AES_ENCRYPTION) {
#ifdef _WIN32
        return impl_->aes->decrypt_aligned(data);
#else
        throw std::runtime_error("AES decryption is unavailable");
#endif
    }
    if (encryption == NG_ENCRYPTION) {
        return impl_->decrypt_ng(data, entry_name, entry_length, hash_lut);
    }
    return data;
}

namespace {

struct ParsedArchive {
    std::vector<EntryDescriptor> entries;
    std::uint32_t encryption = OPEN_ENCRYPTION;
};

struct ResolvedEntry {
    ArchiveContext archive;
    std::uint32_t archive_encryption = OPEN_ENCRYPTION;
    EntryDescriptor entry;
};

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

std::vector<std::uint8_t> read_resolved_entry_standalone(
    FileReader& reader,
    const ResolvedEntry& resolved,
    const NativeCryptoContext* crypto,
    const std::string& hash_lut
) {
    auto raw = read_resolved_entry_raw(reader, resolved);
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

void collect_records(
    FileReader& reader,
    const ArchiveContext& archive,
    const std::string_view hash_lut,
    const NativeCryptoContext* crypto,
    std::vector<AssetRecordData>& out_records,
    const std::uint32_t skip_mask,
    ScanLogFn log_fn,
    void* log_context
) {
    const auto parsed = parse_entries(reader, archive, crypto, std::string(hash_lut));
    const auto encryption = parsed.encryption;
    const auto& entries = parsed.entries;

    std::function<void(std::uint32_t, std::string_view)> walk_dir;
    walk_dir = [&](std::uint32_t dir_index, std::string_view prefix) {
        const auto& dir = entries.at(dir_index);
        const auto start = dir.entries_index;
        const auto end = std::min<std::uint32_t>(start + dir.entries_count, static_cast<std::uint32_t>(entries.size()));
        for (std::uint32_t i = start; i < end; ++i) {
            const auto& child = entries[i];
            const auto archive_path = join_path(prefix, child.name_lower);
            const auto logical_path = normalize_path(join_path(archive.source_prefix, archive_path));
            const auto category_mask = asset_category_mask(logical_path);
            if (child.type == EntryType::Directory) {
                if ((category_mask & skip_mask) != 0U) {
                    log_scan(log_fn, log_context, std::string("[GameFileCache] skip dir ") + logical_path);
                    continue;
                }
                walk_dir(i, archive_path);
                continue;
            }

            if ((category_mask & skip_mask) != 0U) {
                if (child.type == EntryType::Binary && ends_with(child.name_lower, ".rpf")) {
                    log_scan(log_fn, log_context, std::string("[GameFileCache] skip archive subtree ") + logical_path);
                } else {
                    log_scan(log_fn, log_context, std::string("[GameFileCache] skip asset ") + logical_path);
                }
                continue;
            }

            std::uint64_t size = 0;
            std::uint64_t uncompressed_size = 0;
            std::uint8_t flags = 0;
            if (child.type == EntryType::Resource) {
                size = resolve_resource_size(reader, archive, child);
                uncompressed_size = size;
                flags |= FLAG_RESOURCE;
            } else {
                size = child.binary_size();
                uncompressed_size = child.file_uncompressed_size == 0U ? size : child.file_uncompressed_size;
            }
            if (child.is_encrypted) {
                flags |= FLAG_ENCRYPTED;
            }
            const auto lower_name = ascii_lower(path_name(logical_path));
            const auto stem = ascii_lower(path_stem(lower_name));
            log_scan(log_fn, log_context, std::string("[GameFileCache] scan asset ") + logical_path);
            out_records.push_back(AssetRecordData{
                logical_path,
                guess_kind(logical_path),
                size,
                uncompressed_size,
                flags,
                encryption,
                jenk_hash(lower_name, hash_lut),
                jenk_hash(stem, hash_lut),
            });

            if (child.type == EntryType::Binary && ends_with(child.name_lower, ".rpf")) {
                try {
                    const ArchiveContext nested{
                        archive.base_offset + (static_cast<std::uint64_t>(child.file_offset) * RPF_BLOCK_SIZE),
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
    FileReader reader(fs_path);
    const ArchiveContext archive{
        0U,
        reader.size,
        fs_path.filename().string(),
        normalize_path(source_prefix),
    };
    std::vector<AssetRecordData> records;
    records.reserve(4096U);
    collect_records(reader, archive, hash_lut, crypto, records, skip_mask, log_fn, log_context);
    return index.add_many(std::move(records));
}

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
    FileReader reader(fs_path);
    const ArchiveContext archive{
        0U,
        reader.size,
        fs_path.filename().string(),
        {},
    };
    const auto resolved = resolve_entry(reader, archive, entry_path, crypto, hash_lut);
    if (mode == RpfReadMode::Stored) {
        return read_resolved_entry_raw(reader, resolved);
    }
    return read_resolved_entry_standalone(reader, resolved, crypto, hash_lut);
}

}  // namespace fivefury_native

