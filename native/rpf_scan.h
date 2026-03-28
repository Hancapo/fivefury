#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "rpf_index.h"

namespace fivefury_native {

using ScanLogFn = void(*)(void* context, const char* message, std::size_t length);

class NativeCryptoContext {
public:
    NativeCryptoContext(std::vector<std::uint8_t> aes_key, std::vector<std::uint8_t> ng_blob);
    NativeCryptoContext(const NativeCryptoContext&) = delete;
    NativeCryptoContext& operator=(const NativeCryptoContext&) = delete;
    NativeCryptoContext(NativeCryptoContext&& other) noexcept;
    NativeCryptoContext& operator=(NativeCryptoContext&& other) noexcept;
    ~NativeCryptoContext();

    bool can_decrypt() const noexcept;
    std::vector<std::uint8_t> decrypt_archive_table(
        const std::vector<std::uint8_t>& data,
        std::uint32_t encryption,
        const std::string& archive_name,
        std::uint32_t archive_size,
        const std::string& hash_lut
    ) const;
    std::vector<std::uint8_t> decrypt_data(
        const std::vector<std::uint8_t>& data,
        std::uint32_t encryption,
        const std::string& entry_name,
        std::uint32_t entry_length,
        const std::string& hash_lut
    ) const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

std::size_t scan_rpf_into_index(
    CompactIndex& index,
    const std::string& path,
    const std::string& source_prefix,
    const std::string& hash_lut,
    const NativeCryptoContext* crypto,
    std::uint32_t skip_mask = 0,
    ScanLogFn log_fn = nullptr,
    void* log_context = nullptr
);

std::uint32_t jenk_hash(std::string_view value, std::string_view lut);

}  // namespace fivefury_native
