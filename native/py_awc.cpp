#include "py_bindings.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace fivefury_py {

namespace {

constexpr std::array<int, 16> IMA_INDEX_TABLE = {
    -1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8,
};

constexpr std::array<int, 89> IMA_STEP_TABLE = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130,
    143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449,
    494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411,
    1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026,
    4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
};

constexpr std::uint32_t RSXXTEA_CONSTANT = 0x7B3A207FU;
constexpr std::uint32_t RSXXTEA_DELTA = 0x9E3779B9U;

std::int16_t read_i16(const char* source) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(source);
    return static_cast<std::int16_t>(
        static_cast<std::uint16_t>(bytes[0]) |
        (static_cast<std::uint16_t>(bytes[1]) << 8U)
    );
}

void write_i16(char* destination, std::int16_t value) {
    const auto bits = static_cast<std::uint16_t>(value);
    destination[0] = static_cast<char>(bits & 0xFFU);
    destination[1] = static_cast<char>((bits >> 8U) & 0xFFU);
}

std::uint32_t read_u32(const char* source) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(source);
    return static_cast<std::uint32_t>(bytes[0]) |
           (static_cast<std::uint32_t>(bytes[1]) << 8U) |
           (static_cast<std::uint32_t>(bytes[2]) << 16U) |
           (static_cast<std::uint32_t>(bytes[3]) << 24U);
}

void write_u32(char* destination, std::uint32_t value) {
    destination[0] = static_cast<char>(value & 0xFFU);
    destination[1] = static_cast<char>((value >> 8U) & 0xFFU);
    destination[2] = static_cast<char>((value >> 16U) & 0xFFU);
    destination[3] = static_cast<char>((value >> 24U) & 0xFFU);
}

std::uint32_t rsxxtea_mix(
    std::uint32_t left,
    std::uint32_t right,
    std::uint32_t total,
    std::uint32_t key_value
) {
    const auto mixed_a = (left >> 5U) ^ (right << 2U);
    const auto mixed_b = (right >> 3U) ^ (left << 4U);
    const auto mixed_c = (total ^ right) + (key_value ^ left ^ RSXXTEA_CONSTANT);
    return (mixed_a + mixed_b) ^ mixed_c;
}

bool parse_key(PyObject* object, std::array<std::uint32_t, 4>& key) {
    if (PySequence_Size(object) != 4) {
        PyErr_SetString(PyExc_ValueError, "AWC encryption key must contain four uint32 values");
        return false;
    }
    for (Py_ssize_t index = 0; index < 4; ++index) {
        PyObject* item = PySequence_GetItem(object, index);
        if (item == nullptr) {
            return false;
        }
        const auto value = PyLong_AsUnsignedLongMask(item);
        Py_DECREF(item);
        if (PyErr_Occurred()) {
            return false;
        }
        key[static_cast<std::size_t>(index)] = static_cast<std::uint32_t>(value);
    }
    return true;
}

}  // namespace

PyObject* mod_awc_build_peak_values(PyObject*, PyObject* args) {
    const char* source = nullptr;
    Py_ssize_t source_size = 0;
    Py_ssize_t sample_count = 0;
    Py_ssize_t block_size = 4096;
    if (!PyArg_ParseTuple(args, "y#n|n", &source, &source_size, &sample_count, &block_size)) {
        return nullptr;
    }
    if (block_size <= 0) {
        PyErr_SetString(PyExc_ValueError, "block_size must be greater than zero");
        return nullptr;
    }
    if (sample_count <= 0) {
        return PyList_New(0);
    }
    const auto block_count = static_cast<std::size_t>(
        ((sample_count - 1) / block_size) + 1
    );
    std::vector<std::uint16_t> peaks(block_count, 0);
    Py_BEGIN_ALLOW_THREADS
    for (std::size_t block = 0; block < block_count; ++block) {
        const auto start = static_cast<Py_ssize_t>(block) * block_size;
        const auto end = std::min(start + block_size, sample_count);
        std::uint16_t peak = 0;
        for (Py_ssize_t sample = start; sample < end; ++sample) {
            const auto offset = sample * 2;
            if (offset + 2 > source_size) {
                continue;
            }
            const auto value = static_cast<std::int32_t>(read_i16(source + offset));
            const auto absolute = value < 0 ? -value : value;
            peak = std::max<std::uint16_t>(
                peak,
                static_cast<std::uint16_t>(std::min(absolute * 2, 65535))
            );
        }
        peaks[block] = peak;
    }
    Py_END_ALLOW_THREADS
    PyObject* result = PyList_New(static_cast<Py_ssize_t>(peaks.size()));
    if (result == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(peaks.size()); ++index) {
        PyObject* value = PyLong_FromUnsignedLong(peaks[static_cast<std::size_t>(index)]);
        if (value == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        PyList_SetItem(result, index, value);
    }
    return result;
}

PyObject* mod_awc_split_interleaved_pcm16(PyObject*, PyObject* args) {
    const char* source = nullptr;
    Py_ssize_t source_size = 0;
    int channels = 0;
    if (!PyArg_ParseTuple(args, "y#i", &source, &source_size, &channels)) {
        return nullptr;
    }
    if (channels <= 0) {
        PyErr_SetString(PyExc_ValueError, "channels must be greater than zero");
        return nullptr;
    }
    const auto frame_size = static_cast<Py_ssize_t>(channels) * 2;
    if (source_size % frame_size != 0) {
        PyErr_SetString(PyExc_ValueError, "PCM byte length is not aligned to the channel count");
        return nullptr;
    }
    const auto frames = source_size / frame_size;
    std::vector<std::string> outputs(static_cast<std::size_t>(channels));
    for (auto& output : outputs) {
        output.resize(static_cast<std::size_t>(frames) * 2U);
    }
    Py_BEGIN_ALLOW_THREADS
    for (Py_ssize_t frame = 0; frame < frames; ++frame) {
        for (int channel = 0; channel < channels; ++channel) {
            const auto source_offset = frame * frame_size + channel * 2;
            const auto destination_offset = static_cast<std::size_t>(frame) * 2U;
            outputs[static_cast<std::size_t>(channel)][destination_offset] = source[source_offset];
            outputs[static_cast<std::size_t>(channel)][destination_offset + 1U] = source[source_offset + 1];
        }
    }
    Py_END_ALLOW_THREADS
    PyObject* result = PyList_New(channels);
    if (result == nullptr) {
        return nullptr;
    }
    for (int channel = 0; channel < channels; ++channel) {
        const auto& output = outputs[static_cast<std::size_t>(channel)];
        PyObject* value = PyBytes_FromStringAndSize(output.data(), static_cast<Py_ssize_t>(output.size()));
        if (value == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        PyList_SetItem(result, channel, value);
    }
    return result;
}

PyObject* mod_awc_interleave_pcm16(PyObject*, PyObject* args) {
    PyObject* sequence = nullptr;
    Py_ssize_t requested_samples = -1;
    if (!PyArg_ParseTuple(args, "O|n", &sequence, &requested_samples)) {
        return nullptr;
    }
    const auto channel_count = PySequence_Size(sequence);
    if (channel_count < 0) {
        return nullptr;
    }
    if (channel_count == 0) {
        return PyBytes_FromStringAndSize("", 0);
    }
    std::vector<std::string> channels;
    channels.reserve(static_cast<std::size_t>(channel_count));
    Py_ssize_t frame_count = PY_SSIZE_T_MAX;
    for (Py_ssize_t index = 0; index < channel_count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        if (item == nullptr) {
            return nullptr;
        }
        char* data = nullptr;
        Py_ssize_t size = 0;
        const auto ok = PyBytes_AsStringAndSize(item, &data, &size);
        if (ok != 0) {
            Py_DECREF(item);
            return nullptr;
        }
        if (size % 2 != 0) {
            Py_DECREF(item);
            PyErr_SetString(PyExc_ValueError, "PCM channel byte length must be 16-bit aligned");
            return nullptr;
        }
        channels.emplace_back(data, static_cast<std::size_t>(size));
        Py_DECREF(item);
        frame_count = std::min(frame_count, size / 2);
    }
    if (requested_samples >= 0) {
        frame_count = std::min(frame_count, requested_samples);
    }
    std::string output(
        static_cast<std::size_t>(frame_count * channel_count * 2),
        '\0'
    );
    Py_BEGIN_ALLOW_THREADS
    for (Py_ssize_t frame = 0; frame < frame_count; ++frame) {
        for (Py_ssize_t channel = 0; channel < channel_count; ++channel) {
            const auto source_offset = static_cast<std::size_t>(frame) * 2U;
            const auto destination_offset = static_cast<std::size_t>(
                (frame * channel_count + channel) * 2
            );
            output[destination_offset] = channels[static_cast<std::size_t>(channel)][source_offset];
            output[destination_offset + 1U] = channels[static_cast<std::size_t>(channel)][source_offset + 1U];
        }
    }
    Py_END_ALLOW_THREADS
    return PyBytes_FromStringAndSize(output.data(), static_cast<Py_ssize_t>(output.size()));
}

PyObject* mod_awc_decode_adpcm(PyObject*, PyObject* args) {
    const char* source = nullptr;
    Py_ssize_t source_size = 0;
    Py_ssize_t sample_count = 0;
    if (!PyArg_ParseTuple(args, "y#n", &source, &source_size, &sample_count)) {
        return nullptr;
    }
    sample_count = std::max<Py_ssize_t>(sample_count, 0);
    std::string output(static_cast<std::size_t>(sample_count) * 2U, '\0');
    Py_BEGIN_ALLOW_THREADS
    int predictor = 0;
    int step_index = 0;
    Py_ssize_t reading_offset = 0;
    int bytes_in_block = 0;
    Py_ssize_t written = 0;
    auto decode_nibble = [&](int nibble) {
        const auto step = IMA_STEP_TABLE[static_cast<std::size_t>(step_index)];
        auto difference = ((((nibble & 7) << 1) + 1) * step) >> 3;
        if ((nibble & 8) != 0) {
            difference = -difference;
        }
        predictor = std::clamp(predictor + difference, -32768, 32767);
        step_index = std::clamp(
            step_index + IMA_INDEX_TABLE[static_cast<std::size_t>(nibble & 0xF)],
            0,
            88
        );
        write_i16(output.data() + written * 2, static_cast<std::int16_t>(predictor));
        ++written;
    };
    while (reading_offset < source_size && written < sample_count) {
        if (bytes_in_block == 0) {
            if (reading_offset + 4 > source_size) {
                break;
            }
            step_index = std::clamp(static_cast<int>(static_cast<unsigned char>(source[reading_offset])), 0, 88);
            predictor = read_i16(source + reading_offset + 2);
            bytes_in_block = 2044;
            reading_offset += 4;
            continue;
        }
        const auto value = static_cast<unsigned char>(source[reading_offset]);
        decode_nibble(value & 0x0F);
        if (written < sample_count) {
            decode_nibble((value >> 4U) & 0x0F);
        }
        --bytes_in_block;
        ++reading_offset;
    }
    Py_END_ALLOW_THREADS
    return PyBytes_FromStringAndSize(output.data(), static_cast<Py_ssize_t>(output.size()));
}

PyObject* mod_awc_rsxxtea(PyObject*, PyObject* args) {
    const char* source = nullptr;
    Py_ssize_t source_size = 0;
    PyObject* key_object = nullptr;
    int decrypt = 0;
    if (!PyArg_ParseTuple(args, "y#Op", &source, &source_size, &key_object, &decrypt)) {
        return nullptr;
    }
    if (source_size % 4 != 0) {
        PyErr_SetString(PyExc_ValueError, "AWC RSXXTEA data size must be divisible by 4");
        return nullptr;
    }
    if (source_size < 8) {
        return PyBytes_FromStringAndSize(source, source_size);
    }
    std::array<std::uint32_t, 4> key{};
    if (!parse_key(key_object, key)) {
        return nullptr;
    }
    const auto block_count = static_cast<std::size_t>(source_size / 4);
    std::vector<std::uint32_t> blocks(block_count);
    for (std::size_t index = 0; index < block_count; ++index) {
        blocks[index] = read_u32(source + index * 4U);
    }
    Py_BEGIN_ALLOW_THREADS
    if (decrypt != 0) {
        auto total = RSXXTEA_DELTA * static_cast<std::uint32_t>(6U + (52U / block_count));
        auto right = blocks[0];
        while (total != 0U) {
            for (std::size_t reverse = block_count; reverse-- > 0U;) {
                const auto left = blocks[reverse == 0U ? block_count - 1U : reverse - 1U];
                const auto key_index = (reverse & 3U) ^ ((total >> 2U) & 3U);
                const auto value = blocks[reverse] - rsxxtea_mix(left, right, total, key[key_index]);
                blocks[reverse] = value;
                right = value;
            }
            total -= RSXXTEA_DELTA;
        }
    } else {
        auto rounds = 6U + (52U / static_cast<std::uint32_t>(block_count));
        std::uint32_t total = 0;
        auto left = blocks.back();
        while (rounds-- != 0U) {
            total += RSXXTEA_DELTA;
            const auto e = (total >> 2U) & 3U;
            for (std::size_t index = 0; index < block_count; ++index) {
                const auto right = blocks[(index + 1U) % block_count];
                const auto key_index = (index & 3U) ^ e;
                const auto value = blocks[index] + rsxxtea_mix(left, right, total, key[key_index]);
                blocks[index] = value;
                left = value;
            }
        }
    }
    Py_END_ALLOW_THREADS
    std::string output(static_cast<std::size_t>(source_size), '\0');
    for (std::size_t index = 0; index < block_count; ++index) {
        write_u32(output.data() + index * 4U, blocks[index]);
    }
    return PyBytes_FromStringAndSize(output.data(), source_size);
}

}  // namespace fivefury_py
