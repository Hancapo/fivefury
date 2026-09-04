#include "indexing/bindings.h"

#include <array>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <vector>

namespace fivefury_py {
namespace {

constexpr std::uint32_t SYSTEM_BASE = 0x50000000U;
constexpr std::uint32_t GRAPHICS_BASE = 0x60000000U;
constexpr std::uint32_t CMAP_TYPES = 0xD98BB561U;
constexpr std::array<std::uint32_t, 3> ARCHETYPE_TYPES = {
    0x82D6FC83U,
    0x76B0C56CU,
    0x10506455U,
};

struct Block {
    std::uint32_t type = 0;
    const unsigned char* data = nullptr;
    std::size_t size = 0;
};

std::uint16_t read_u16(const unsigned char* data) {
    return static_cast<std::uint16_t>(data[0]) |
           (static_cast<std::uint16_t>(data[1]) << 8U);
}

std::uint32_t read_u32(const unsigned char* data) {
    return static_cast<std::uint32_t>(data[0]) |
           (static_cast<std::uint32_t>(data[1]) << 8U) |
           (static_cast<std::uint32_t>(data[2]) << 16U) |
           (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t read_u64(const unsigned char* data) {
    std::uint64_t value = 0;
    for (unsigned int index = 0; index < 8U; ++index) {
        value |= static_cast<std::uint64_t>(data[index]) << (index * 8U);
    }
    return value;
}

std::size_t absolute_offset(std::uint64_t pointer) {
    if (pointer >= GRAPHICS_BASE) {
        pointer -= GRAPHICS_BASE;
    } else if (pointer >= SYSTEM_BASE) {
        pointer -= SYSTEM_BASE;
    }
    if (pointer > std::numeric_limits<std::size_t>::max()) {
        throw std::invalid_argument("META pointer exceeds the host address range");
    }
    return static_cast<std::size_t>(pointer);
}

void require_range(std::size_t offset, std::size_t length, std::size_t size) {
    if (offset > size || length > size - offset) {
        throw std::invalid_argument("META payload is truncated");
    }
}

const Block& pointed_block(
    const std::vector<Block>& blocks,
    std::uint64_t pointer,
    std::size_t& offset
) {
    const auto block_id = static_cast<std::size_t>(pointer & 0xFFFU);
    offset = static_cast<std::size_t>((pointer >> 12U) & 0xFFFFFU);
    if (block_id == 0U || block_id > blocks.size()) {
        throw std::invalid_argument("META pointer references an invalid block");
    }
    return blocks[block_id - 1U];
}

bool is_archetype_type(std::uint32_t type) {
    for (const auto candidate : ARCHETYPE_TYPES) {
        if (type == candidate) {
            return true;
        }
    }
    return false;
}

PyObject* make_relationship(
    std::uint32_t name,
    std::uint32_t texture_dictionary,
    std::uint32_t asset_name
) {
    PyObject* result = PyTuple_New(3);
    if (result == nullptr) {
        return nullptr;
    }
    const std::array<std::uint32_t, 3> values = {name, texture_dictionary, asset_name};
    for (Py_ssize_t index = 0; index < 3; ++index) {
        PyObject* value = PyLong_FromUnsignedLong(values[static_cast<std::size_t>(index)]);
        if (value == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        PyTuple_SetItem(result, index, value);
    }
    return result;
}

}  // namespace

PyObject* mod_meta_extract_ytyp_texture_relationships(PyObject*, PyObject* args) {
    BytesView source;
    if (!PyArg_ParseTuple(
            args,
            "O&:meta_extract_ytyp_texture_relationships",
            parse_bytes_view,
            &source
        )) {
        return nullptr;
    }
    try {
        const auto* data = reinterpret_cast<const unsigned char*>(source.data);
        const auto size = static_cast<std::size_t>(source.size);
        require_range(0U, 80U, size);

        constexpr std::size_t meta_root = 16U;
        const auto root_block_id = static_cast<std::size_t>(read_u32(data + meta_root + 12U));
        const auto blocks_pointer = read_u64(data + meta_root + 32U);
        const auto block_count = static_cast<std::size_t>(read_u16(data + meta_root + 60U));
        if (root_block_id == 0U || root_block_id > block_count) {
            throw std::invalid_argument("META root block is invalid");
        }

        const auto table_offset = absolute_offset(blocks_pointer);
        if (block_count > (std::numeric_limits<std::size_t>::max() / 16U)) {
            throw std::invalid_argument("META block count is invalid");
        }
        require_range(table_offset, block_count * 16U, size);

        std::vector<Block> blocks;
        blocks.reserve(block_count);
        for (std::size_t index = 0; index < block_count; ++index) {
            const auto* descriptor = data + table_offset + index * 16U;
            const auto block_size = static_cast<std::size_t>(read_u32(descriptor + 4U));
            const auto block_offset = absolute_offset(read_u64(descriptor + 8U));
            require_range(block_offset, block_size, size);
            blocks.push_back({read_u32(descriptor), data + block_offset, block_size});
        }

        const auto& root = blocks[root_block_id - 1U];
        if (root.type != CMAP_TYPES) {
            throw std::invalid_argument("META root is not CMapTypes");
        }
        require_range(24U, 16U, root.size);
        const auto archetype_pointer = read_u64(root.data + 24U);
        const auto archetype_count = static_cast<std::size_t>(read_u16(root.data + 32U));
        const auto archetype_capacity = static_cast<std::size_t>(read_u16(root.data + 34U));
        if (archetype_count > archetype_capacity) {
            throw std::invalid_argument("CMapTypes archetype array count exceeds capacity");
        }
        if (archetype_count == 0U) {
            return PyList_New(0);
        }

        std::size_t pointer_offset = 0;
        const auto& pointer_block = pointed_block(blocks, archetype_pointer, pointer_offset);
        require_range(pointer_offset, archetype_count * 8U, pointer_block.size);
        PyObject* result = PyList_New(0);
        if (result == nullptr) {
            return nullptr;
        }
        for (std::size_t index = 0; index < archetype_count; ++index) {
            const auto pointer = read_u64(pointer_block.data + pointer_offset + index * 8U);
            if ((pointer & 0xFFFU) == 0U) {
                continue;
            }
            std::size_t archetype_offset = 0;
            const auto& archetype = pointed_block(blocks, pointer, archetype_offset);
            if (!is_archetype_type(archetype.type)) {
                continue;
            }
            require_range(archetype_offset, 116U, archetype.size);
            PyObject* item = make_relationship(
                read_u32(archetype.data + archetype_offset + 88U),
                read_u32(archetype.data + archetype_offset + 92U),
                read_u32(archetype.data + archetype_offset + 112U)
            );
            if (item == nullptr || PyList_Append(result, item) < 0) {
                Py_XDECREF(item);
                Py_DECREF(result);
                return nullptr;
            }
            Py_DECREF(item);
        }
        return result;
    } catch (...) {
        return translate_cpp_exception();
    }
}

}  // namespace fivefury_py
