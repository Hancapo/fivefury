#include "rpf/scan.h"

#include "indexing/hash.h"

#include <array>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <utility>
#include <vector>

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

constexpr std::uint32_t NONE_ENCRYPTION = 0;
constexpr std::uint32_t OPEN_ENCRYPTION = 0x4E45504F;
constexpr std::uint32_t AES_ENCRYPTION = 0x0FFFFFF9;
constexpr std::uint32_t PS3_AES_ENCRYPTION = 0x0FFFFFF8;
constexpr std::uint32_t NG_ENCRYPTION = 0x0FEFFFFF;
constexpr std::size_t NG_KEYS_SIZE = 27472;
constexpr std::size_t NG_TABLES_SIZE = 278528;
constexpr std::size_t NG_BLOB_SIZE = NG_KEYS_SIZE + NG_TABLES_SIZE;
constexpr std::size_t NG_ENCRYPT_TABLES_SIZE = NG_TABLES_SIZE;
constexpr std::size_t NG_LUT_SIZE = 3U * 65536U;
constexpr std::size_t NG_ENCRYPT_LUTS_SIZE = 17U * 16U * NG_LUT_SIZE;
constexpr std::size_t NG_ENCRYPT_BLOB_SIZE = NG_ENCRYPT_TABLES_SIZE + NG_ENCRYPT_LUTS_SIZE;
constexpr std::array<std::uint8_t, 32> GTA5_PS3_AES_KEY = {
    0x85, 0x13, 0x6E, 0x1E, 0x37, 0xFC, 0xBC, 0x45,
    0x94, 0xE7, 0xF7, 0xBC, 0x5F, 0x18, 0x52, 0x00,
    0xB3, 0x2A, 0x67, 0x30, 0x8C, 0xC1, 0xB8, 0x33,
    0xB3, 0x2A, 0x67, 0x30, 0x8C, 0xC1, 0xB8, 0x33,
};

std::uint32_t read_u32_le(const std::uint8_t* data) noexcept {
    return static_cast<std::uint32_t>(data[0]) |
           (static_cast<std::uint32_t>(data[1]) << 8U) |
           (static_cast<std::uint32_t>(data[2]) << 16U) |
           (static_cast<std::uint32_t>(data[3]) << 24U);
}

void write_u32_le(std::uint32_t value, std::uint8_t* out) noexcept {
    out[0] = static_cast<std::uint8_t>(value & 0xFFU);
    out[1] = static_cast<std::uint8_t>((value >> 8U) & 0xFFU);
    out[2] = static_cast<std::uint8_t>((value >> 16U) & 0xFFU);
    out[3] = static_cast<std::uint8_t>((value >> 24U) & 0xFFU);
}

#ifdef _WIN32
class AesEcbCipher {
public:
    explicit AesEcbCipher(const std::vector<std::uint8_t>& key_material) {
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

    AesEcbCipher(const AesEcbCipher&) = delete;
    AesEcbCipher& operator=(const AesEcbCipher&) = delete;

    ~AesEcbCipher() {
        close();
    }

    std::vector<std::uint8_t> decrypt_aligned(const std::vector<std::uint8_t>& data) const {
        return transform_aligned(data, false);
    }

    std::vector<std::uint8_t> encrypt_aligned(const std::vector<std::uint8_t>& data) const {
        return transform_aligned(data, true);
    }

private:
    std::vector<std::uint8_t> transform_aligned(
        const std::vector<std::uint8_t>& data,
        const bool encrypt
    ) const {
        if (data.empty()) {
            return {};
        }
        const auto aligned = data.size() - (data.size() % 16U);
        std::vector<std::uint8_t> out(data.begin(), data.end());
        if (aligned == 0) {
            return out;
        }
        ULONG written = 0;
        const auto status = encrypt
            ? BCryptEncrypt(
                key_, const_cast<PUCHAR>(data.data()), static_cast<ULONG>(aligned),
                nullptr, nullptr, 0, out.data(), static_cast<ULONG>(aligned), &written, 0
            )
            : BCryptDecrypt(
                key_, const_cast<PUCHAR>(data.data()), static_cast<ULONG>(aligned),
                nullptr, nullptr, 0, out.data(), static_cast<ULONG>(aligned), &written, 0
            );
        check(status, encrypt ? "BCryptEncrypt" : "BCryptDecrypt");
        return out;
    }

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

struct NativeCryptoContext::Impl {
    explicit Impl(std::vector<std::uint8_t> aes_key_bytes, std::vector<std::uint8_t> ng_blob_bytes) {
        if (aes_key_bytes.size() != 32U) {
            throw std::invalid_argument("AES key must be 32 bytes");
        }
        if (ng_blob_bytes.size() < NG_BLOB_SIZE) {
            throw std::invalid_argument("NG blob is truncated");
        }
#ifdef _WIN32
        aes = std::make_unique<AesEcbCipher>(aes_key_bytes);
        ps3_aes = std::make_unique<AesEcbCipher>(
            std::vector<std::uint8_t>(GTA5_PS3_AES_KEY.begin(), GTA5_PS3_AES_KEY.end())
        );
#endif
        ng_tables.resize(NG_TABLES_SIZE / sizeof(std::uint32_t));
        const auto* tables_data = ng_blob_bytes.data() + NG_KEYS_SIZE;
        for (std::size_t i = 0; i < ng_tables.size(); ++i) {
            ng_tables[i] = read_u32_le(tables_data + (i * 4U));
        }
        ng_subkeys.resize(101U * 17U * 4U);
        for (std::size_t key_index = 0; key_index < 101U; ++key_index) {
            const auto* key_base = ng_blob_bytes.data() + (key_index * 272U);
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

    void enable_encryption(const std::vector<std::uint8_t>& blob) {
        if (blob.size() != NG_ENCRYPT_BLOB_SIZE) {
            throw std::invalid_argument("NG encryption blob has an invalid size");
        }
        ng_encrypt_tables.resize(NG_ENCRYPT_TABLES_SIZE / sizeof(std::uint32_t));
        for (std::size_t i = 0; i < ng_encrypt_tables.size(); ++i) {
            ng_encrypt_tables[i] = read_u32_le(blob.data() + (i * 4U));
        }
        ng_encrypt_luts.assign(blob.begin() + NG_ENCRYPT_TABLES_SIZE, blob.end());
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
        if (encryption == AES_ENCRYPTION || encryption == PS3_AES_ENCRYPTION) {
#ifdef _WIN32
            return (encryption == PS3_AES_ENCRYPTION ? ps3_aes : aes)->decrypt_aligned(data);
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
        const auto key_seed = (jenk_hash(archive_name, hash_lut) + archive_size + 61U) & 0xFFFFFFFFU;
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

    std::vector<std::uint8_t> encrypt_archive_table(
        const std::vector<std::uint8_t>& data,
        const std::uint32_t encryption,
        const std::string& archive_name,
        const std::uint32_t archive_size,
        const std::string& hash_lut
    ) const {
        if (encryption == NONE_ENCRYPTION || encryption == OPEN_ENCRYPTION) {
            return data;
        }
        if (encryption == AES_ENCRYPTION || encryption == PS3_AES_ENCRYPTION) {
#ifdef _WIN32
            return (encryption == PS3_AES_ENCRYPTION ? ps3_aes : aes)->encrypt_aligned(data);
#else
            throw std::runtime_error("AES encryption is unavailable");
#endif
        }
        if (encryption != NG_ENCRYPTION) {
            throw std::runtime_error("unsupported RPF encryption");
        }
        return encrypt_ng(data, archive_name, archive_size, hash_lut);
    }

    std::vector<std::uint8_t> encrypt_ng(
        const std::vector<std::uint8_t>& data,
        const std::string& name,
        const std::uint32_t length,
        const std::string& hash_lut
    ) const {
        if (ng_encrypt_luts.empty()) {
            throw std::runtime_error("NG encryption tables are not loaded");
        }
        const auto key_seed = (jenk_hash(name, hash_lut) + length + 61U) & 0xFFFFFFFFU;
        const auto key_index = static_cast<std::size_t>(key_seed % 0x65U);
        std::vector<std::uint8_t> out(data.begin(), data.end());
        const auto aligned = out.size() - (out.size() % 16U);
        const auto subkey_base = key_index * 17U * 4U;
        for (std::size_t offset = 0; offset < aligned; offset += 16U) {
            encrypt_ng_block(out.data() + offset, &data[offset], subkey_base);
        }
        return out;
    }

    void encrypt_ng_block(std::uint8_t* out, const std::uint8_t* in, const std::size_t subkey_base) const {
        std::array<std::uint8_t, 16> buffer{};
        std::memcpy(buffer.data(), in, 16U);
        encrypt_round_a(buffer.data(), subkey_base + 16U * 4U, 16U);
        for (std::size_t round_index = 15U; round_index >= 2U; --round_index) {
            encrypt_round_b(buffer.data(), subkey_base + round_index * 4U, round_index);
        }
        encrypt_round_a(buffer.data(), subkey_base + 1U * 4U, 1U);
        encrypt_round_a(buffer.data(), subkey_base, 0U);
        std::memcpy(out, buffer.data(), 16U);
    }

    void encrypt_round_a(
        std::uint8_t* block,
        const std::size_t subkey_offset,
        const std::size_t round_index
    ) const {
        std::array<std::uint8_t, 16> input{};
        xor_subkey(input.data(), block, subkey_offset);
        const auto tbase = round_index * 16U * 256U;
        for (std::size_t word = 0; word < 4U; ++word) {
            const auto byte = word * 4U;
            const auto value = encrypt_table(tbase + (byte + 0U) * 256U, input[byte + 0U]) ^
                               encrypt_table(tbase + (byte + 1U) * 256U, input[byte + 1U]) ^
                               encrypt_table(tbase + (byte + 2U) * 256U, input[byte + 2U]) ^
                               encrypt_table(tbase + (byte + 3U) * 256U, input[byte + 3U]);
            write_u32_le(value, block + byte);
        }
    }

    void encrypt_round_b(
        std::uint8_t* block,
        const std::size_t subkey_offset,
        const std::size_t round_index
    ) const {
        std::array<std::uint8_t, 16> input{};
        xor_subkey(input.data(), block, subkey_offset);
        const std::array<std::size_t, 16> source_words = {
            0U, 1U, 2U, 3U, 1U, 2U, 3U, 0U,
            2U, 3U, 0U, 1U, 3U, 0U, 1U, 2U,
        };
        for (std::size_t output_index = 0; output_index < 16U; ++output_index) {
            const auto source = source_words[output_index] * 4U;
            const auto value = read_u32_le(input.data() + source);
            block[output_index] = encrypt_lut(round_index, output_index, value);
        }
    }

    void xor_subkey(
        std::uint8_t* out,
        const std::uint8_t* block,
        const std::size_t subkey_offset
    ) const noexcept {
        for (std::size_t word = 0; word < 4U; ++word) {
            const auto key = ng_subkeys[subkey_offset + word];
            for (std::size_t byte = 0; byte < 4U; ++byte) {
                const auto index = word * 4U + byte;
                out[index] = block[index] ^ static_cast<std::uint8_t>(key >> (byte * 8U));
            }
        }
    }

    std::uint32_t encrypt_table(const std::size_t base, const std::uint8_t index) const noexcept {
        return ng_encrypt_tables[base + index];
    }

    std::uint8_t encrypt_lut(
        const std::size_t round_index,
        const std::size_t table_index,
        const std::uint32_t value
    ) const noexcept {
        const auto base = (round_index * 16U + table_index) * NG_LUT_SIZE;
        const auto high = static_cast<std::uint16_t>(value >> 16U);
        const auto middle = static_cast<std::uint8_t>(value >> 8U);
        const auto low = static_cast<std::uint8_t>(value);
        const auto first = ng_encrypt_luts[base + 2U * 65536U + high];
        const auto second = ng_encrypt_luts[base + 65536U + static_cast<std::size_t>(first) * 256U + middle];
        return ng_encrypt_luts[base + static_cast<std::size_t>(second) * 256U + low];
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

    std::vector<std::uint32_t> ng_tables;
    std::vector<std::uint32_t> ng_subkeys;
    std::vector<std::uint32_t> ng_encrypt_tables;
    std::vector<std::uint8_t> ng_encrypt_luts;
#ifdef _WIN32
    std::unique_ptr<AesEcbCipher> aes;
    std::unique_ptr<AesEcbCipher> ps3_aes;
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

bool NativeCryptoContext::can_encrypt() const noexcept {
    return impl_ != nullptr;
}

void NativeCryptoContext::enable_encryption(std::vector<std::uint8_t> ng_encrypt_blob) {
    if (impl_ == nullptr) {
        throw std::runtime_error("crypto context is not initialized");
    }
    impl_->enable_encryption(ng_encrypt_blob);
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
    if (encryption == AES_ENCRYPTION || encryption == PS3_AES_ENCRYPTION) {
#ifdef _WIN32
        return (encryption == PS3_AES_ENCRYPTION ? impl_->ps3_aes : impl_->aes)->decrypt_aligned(data);
#else
        throw std::runtime_error("AES decryption is unavailable");
#endif
    }
    if (encryption == NG_ENCRYPTION) {
        return impl_->decrypt_ng(data, entry_name, entry_length, hash_lut);
    }
    return data;
}

std::vector<std::uint8_t> NativeCryptoContext::encrypt_archive_table(
    const std::vector<std::uint8_t>& data,
    const std::uint32_t encryption,
    const std::string& archive_name,
    const std::uint32_t archive_size,
    const std::string& hash_lut
) const {
    if (impl_ == nullptr) {
        throw std::runtime_error("crypto context is not initialized");
    }
    return impl_->encrypt_archive_table(data, encryption, archive_name, archive_size, hash_lut);
}

std::vector<std::uint8_t> NativeCryptoContext::encrypt_data(
    const std::vector<std::uint8_t>& data,
    const std::uint32_t encryption,
    const std::string& entry_name,
    const std::uint32_t entry_length,
    const std::string& hash_lut
) const {
    if (impl_ == nullptr) {
        throw std::runtime_error("crypto context is not initialized");
    }
    if (data.empty() || encryption == NONE_ENCRYPTION || encryption == OPEN_ENCRYPTION) {
        return data;
    }
    return impl_->encrypt_archive_table(data, encryption, entry_name, entry_length, hash_lut);
}

}  // namespace fivefury_native
