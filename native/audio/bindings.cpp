#ifndef PY_SSIZE_T_CLEAN
#define PY_SSIZE_T_CLEAN
#endif
#include "audio/bindings.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <limits>
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

std::uint16_t read_u16(const char* source) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(source);
    return static_cast<std::uint16_t>(bytes[0]) |
           (static_cast<std::uint16_t>(bytes[1]) << 8U);
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

void write_u16(char* destination, std::uint16_t value) {
    destination[0] = static_cast<char>(value & 0xFFU);
    destination[1] = static_cast<char>((value >> 8U) & 0xFFU);
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

PyObject* mod_awc_parse_pcm_wav(PyObject*, PyObject* args) {
    const char* source = nullptr;
    Py_ssize_t source_size = 0;
    if (!PyArg_ParseTuple(args, "y#", &source, &source_size)) {
        return nullptr;
    }
    if (
        source_size < 12 || std::memcmp(source, "RIFF", 4) != 0 ||
        std::memcmp(source + 8, "WAVE", 4) != 0
    ) {
        PyErr_SetString(PyExc_ValueError, "Expected a RIFF/WAVE file");
        return nullptr;
    }

    bool has_format = false;
    bool has_data = false;
    std::uint16_t audio_format = 0;
    std::uint16_t channels = 0;
    std::uint32_t sample_rate = 0;
    std::uint16_t bits_per_sample = 0;
    const char* pcm = nullptr;
    Py_ssize_t pcm_size = 0;
    Py_ssize_t offset = 12;
    while (offset <= source_size - 8) {
        const auto chunk_size = static_cast<Py_ssize_t>(read_u32(source + offset + 4));
        const auto payload_start = offset + 8;
        if (chunk_size > source_size - payload_start) {
            PyErr_SetString(PyExc_ValueError, "WAV chunk points outside the file");
            return nullptr;
        }
        const auto* chunk_id = source + offset;
        if (std::memcmp(chunk_id, "fmt ", 4) == 0) {
            if (chunk_size < 16) {
                PyErr_SetString(PyExc_ValueError, "WAV fmt chunk is truncated");
                return nullptr;
            }
            audio_format = read_u16(source + payload_start);
            channels = read_u16(source + payload_start + 2);
            sample_rate = read_u32(source + payload_start + 4);
            bits_per_sample = read_u16(source + payload_start + 14);
            has_format = true;
        } else if (std::memcmp(chunk_id, "data", 4) == 0) {
            pcm = source + payload_start;
            pcm_size = chunk_size;
            has_data = true;
        }
        const auto padded_size = chunk_size + (chunk_size & 1);
        if (padded_size > source_size - payload_start) {
            offset = source_size;
        } else {
            offset = payload_start + padded_size;
        }
    }
    if (!has_format) {
        PyErr_SetString(PyExc_ValueError, "WAV fmt chunk not found");
        return nullptr;
    }
    if (!has_data) {
        PyErr_SetString(PyExc_ValueError, "WAV data chunk not found");
        return nullptr;
    }
    if (audio_format != 1) {
        PyErr_SetString(PyExc_ValueError, "Only PCM WAV files are supported");
        return nullptr;
    }
    return Py_BuildValue(
        "(y#IHH)",
        pcm,
        pcm_size,
        sample_rate,
        channels,
        bits_per_sample
    );
}

PyObject* mod_awc_build_pcm_wav(PyObject*, PyObject* args) {
    const char* pcm = nullptr;
    Py_ssize_t pcm_size = 0;
    unsigned int sample_rate = 0;
    unsigned int channels = 1;
    unsigned int bits_per_sample = 16;
    if (!PyArg_ParseTuple(
            args,
            "y#I|II",
            &pcm,
            &pcm_size,
            &sample_rate,
            &channels,
            &bits_per_sample
        )) {
        return nullptr;
    }
    if (channels == 0 || channels > 0xFFFFU) {
        PyErr_SetString(PyExc_ValueError, "channels must fit a non-zero uint16");
        return nullptr;
    }
    if (bits_per_sample == 0 || bits_per_sample > 0xFFFFU || bits_per_sample % 8U != 0U) {
        PyErr_SetString(PyExc_ValueError, "bits_per_sample must be byte-aligned and fit uint16");
        return nullptr;
    }
    const auto block_align = channels * (bits_per_sample / 8U);
    if (block_align > 0xFFFFU) {
        PyErr_SetString(PyExc_ValueError, "PCM block alignment exceeds uint16");
        return nullptr;
    }
    const auto byte_rate = static_cast<std::uint64_t>(sample_rate) * block_align;
    const auto padded_data_size = static_cast<std::uint64_t>(pcm_size) + (pcm_size & 1);
    if (byte_rate > 0xFFFFFFFFULL || padded_data_size + 36ULL > 0xFFFFFFFFULL) {
        PyErr_SetString(PyExc_OverflowError, "WAV output exceeds RIFF limits");
        return nullptr;
    }
    std::string output(static_cast<std::size_t>(44 + padded_data_size), '\0');
    std::memcpy(output.data(), "RIFF", 4);
    write_u32(output.data() + 4, static_cast<std::uint32_t>(36ULL + padded_data_size));
    std::memcpy(output.data() + 8, "WAVEfmt ", 8);
    write_u32(output.data() + 16, 16);
    write_u16(output.data() + 20, 1);
    write_u16(output.data() + 22, static_cast<std::uint16_t>(channels));
    write_u32(output.data() + 24, sample_rate);
    write_u32(output.data() + 28, static_cast<std::uint32_t>(byte_rate));
    write_u16(output.data() + 32, static_cast<std::uint16_t>(block_align));
    write_u16(output.data() + 34, static_cast<std::uint16_t>(bits_per_sample));
    std::memcpy(output.data() + 36, "data", 4);
    write_u32(output.data() + 40, static_cast<std::uint32_t>(pcm_size));
    if (pcm_size != 0) {
        std::memcpy(output.data() + 44, pcm, static_cast<std::size_t>(pcm_size));
    }
    return PyBytes_FromStringAndSize(output.data(), static_cast<Py_ssize_t>(output.size()));
}

PyObject* mod_awc_extract_multichannel_blocks(PyObject*, PyObject* args) {
    const char* source = nullptr;
    Py_ssize_t source_size = 0;
    Py_ssize_t block_count = 0;
    Py_ssize_t block_size = 0;
    Py_ssize_t channel_count = 0;
    if (!PyArg_ParseTuple(
            args,
            "y#nnn",
            &source,
            &source_size,
            &block_count,
            &block_size,
            &channel_count
        )) {
        return nullptr;
    }
    if (block_count < 0 || block_size <= 0 || channel_count <= 0) {
        PyErr_SetString(PyExc_ValueError, "invalid AWC multichannel block dimensions");
        return nullptr;
    }
    if (
        block_count > 0
        && (block_count - 1) > source_size / block_size
    ) {
        PyErr_SetString(PyExc_ValueError, "AWC multichannel data is truncated");
        return nullptr;
    }

    PyObject* result = PyList_New(channel_count);
    if (result == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t channel = 0; channel < channel_count; ++channel) {
        PyObject* channel_blocks = PyList_New(0);
        if (channel_blocks == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        PyList_SetItem(result, channel, channel_blocks);
    }

    for (Py_ssize_t block_index = 0; block_index < block_count; ++block_index) {
        const auto block_offset = block_index * block_size;
        const auto current_block_size = std::min(
            block_size,
            source_size - block_offset
        );
        if (current_block_size < 0 || channel_count > current_block_size / 24) {
            Py_DECREF(result);
            PyErr_SetString(PyExc_ValueError, "AWC multichannel header table is truncated");
            return nullptr;
        }
        const char* block = source + block_offset;
        Py_ssize_t cursor = channel_count * 24;
        std::vector<std::int32_t> counts(static_cast<std::size_t>(channel_count));
        std::vector<std::int32_t> samples(static_cast<std::size_t>(channel_count));
        std::vector<std::int32_t> encoded_sizes(static_cast<std::size_t>(channel_count));
        for (Py_ssize_t channel = 0; channel < channel_count; ++channel) {
            const char* header = block + channel * 24;
            counts[static_cast<std::size_t>(channel)] = static_cast<std::int32_t>(read_u32(header + 4));
            samples[static_cast<std::size_t>(channel)] = static_cast<std::int32_t>(read_u32(header + 12));
            encoded_sizes[static_cast<std::size_t>(channel)] = static_cast<std::int32_t>(read_u32(header + 20));
            if (
                counts[static_cast<std::size_t>(channel)] < 0
                || samples[static_cast<std::size_t>(channel)] < 0
                || encoded_sizes[static_cast<std::size_t>(channel)] < 0
            ) {
                Py_DECREF(result);
                PyErr_SetString(PyExc_ValueError, "AWC multichannel block contains a negative size");
                return nullptr;
            }
            const auto table_bytes = static_cast<std::int64_t>(counts[static_cast<std::size_t>(channel)]) * 4LL;
            if (table_bytes > current_block_size - cursor) {
                Py_DECREF(result);
                PyErr_SetString(PyExc_ValueError, "AWC multichannel offset table is truncated");
                return nullptr;
            }
            cursor += static_cast<Py_ssize_t>(table_bytes);
        }
        const auto alignment = (0x800 - (cursor % 0x800)) % 0x800;
        if (alignment > current_block_size - cursor) {
            Py_DECREF(result);
            PyErr_SetString(PyExc_ValueError, "AWC multichannel payload alignment is invalid");
            return nullptr;
        }
        cursor += alignment;

        std::vector<Py_ssize_t> stored_payload_sizes(
            static_cast<std::size_t>(channel_count)
        );
        auto payload_cursor = cursor;
        for (Py_ssize_t channel = 0; channel < channel_count; ++channel) {
            const auto encoded_size = encoded_sizes[static_cast<std::size_t>(channel)];
            const auto stored_payload_size = encoded_size > 0
                ? static_cast<std::int64_t>(encoded_size)
                : static_cast<std::int64_t>(
                      counts[static_cast<std::size_t>(channel)]
                  ) * 2048LL;
            if (
                stored_payload_size
                > static_cast<std::int64_t>(
                    std::numeric_limits<Py_ssize_t>::max()
                )
            ) {
                Py_DECREF(result);
                PyErr_SetString(PyExc_OverflowError, "AWC multichannel payload exceeds platform limits");
                return nullptr;
            }
            const auto stride = static_cast<Py_ssize_t>(stored_payload_size);
            if (stride > current_block_size - payload_cursor) {
                Py_DECREF(result);
                PyErr_SetString(PyExc_ValueError, "AWC multichannel payload is truncated");
                return nullptr;
            }
            stored_payload_sizes[static_cast<std::size_t>(channel)] = stride;
            payload_cursor += stride;
        }

        for (Py_ssize_t channel = 0; channel < channel_count; ++channel) {
            const auto stored_payload_size =
                stored_payload_sizes[static_cast<std::size_t>(channel)];
            PyObject* item = Py_BuildValue(
                "(iy#)",
                samples[static_cast<std::size_t>(channel)],
                block + cursor,
                stored_payload_size
            );
            if (item == nullptr || PyList_Append(PyList_GetItem(result, channel), item) != 0) {
                Py_XDECREF(item);
                Py_DECREF(result);
                return nullptr;
            }
            Py_DECREF(item);
            cursor += stored_payload_size;
        }
    }
    return result;
}

}  // namespace fivefury_py
