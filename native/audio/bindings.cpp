#include "binary/primitives.h"
#include "audio/bindings.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

namespace fivefury_py {
namespace binary = fivefury_native::binary;

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
    BytesView source_view;
    Py_ssize_t sample_count = 0;
    Py_ssize_t block_size = 4096;
    if (!PyArg_ParseTuple(args, "O&n|n", parse_bytes_view, &source_view, &sample_count, &block_size)) {
        return nullptr;
    }
    const auto* source = source_view.data;
    const auto source_size = source_view.size;
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
    {
    GilRelease gil_release;
    for (std::size_t block = 0; block < block_count; ++block) {
        const auto start = static_cast<Py_ssize_t>(block) * block_size;
        const auto end = start + std::min(block_size, sample_count - start);
        std::uint16_t peak = 0;
        for (Py_ssize_t sample = start; sample < std::min(end, source_size / 2); ++sample) {
            const auto offset = sample * 2;
            const auto value = static_cast<std::int32_t>(binary::load<std::int16_t>(source + offset));
            const auto absolute = value < 0 ? -value : value;
            peak = std::max<std::uint16_t>(
                peak,
                static_cast<std::uint16_t>(std::min(absolute * 2, 65535))
            );
        }
        peaks[block] = peak;
    }
    }
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
    BytesView source_view;
    int channels = 0;
    if (!PyArg_ParseTuple(args, "O&i", parse_bytes_view, &source_view, &channels)) {
        return nullptr;
    }
    const auto* source = source_view.data;
    const auto source_size = source_view.size;
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
    {
    GilRelease gil_release;
    for (Py_ssize_t frame = 0; frame < frames; ++frame) {
        for (int channel = 0; channel < channels; ++channel) {
            const auto source_offset = frame * frame_size + channel * 2;
            const auto destination_offset = static_cast<std::size_t>(frame) * 2U;
            outputs[static_cast<std::size_t>(channel)][destination_offset] = source[source_offset];
            outputs[static_cast<std::size_t>(channel)][destination_offset + 1U] = source[source_offset + 1];
        }
    }
    }
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
        static_cast<std::size_t>(checked_buffer_size(
            binary::checked_product(static_cast<std::size_t>(frame_count), static_cast<std::size_t>(channel_count)), 2U)),
        '\0'
    );
    {
    GilRelease gil_release;
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
    }
    return PyBytes_FromStringAndSize(output.data(), static_cast<Py_ssize_t>(output.size()));
}

PyObject* mod_awc_decode_adpcm(PyObject*, PyObject* args) {
    BytesView source_view;
    Py_ssize_t sample_count = 0;
    if (!PyArg_ParseTuple(args, "O&n", parse_bytes_view, &source_view, &sample_count)) {
        return nullptr;
    }
    const auto* source = source_view.data;
    const auto source_size = source_view.size;
    sample_count = std::max<Py_ssize_t>(sample_count, 0);
    const auto output_size = checked_buffer_size(static_cast<std::size_t>(sample_count), 2U);
    PyHandle output(PyBytes_FromStringAndSize(nullptr, output_size));
    if (!output) return nullptr;
    char* destination = PyBytes_AsString(output.get());
    if (destination == nullptr) return nullptr;
    {
    GilRelease gil_release;
    std::memset(destination, 0, static_cast<std::size_t>(output_size));
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
        binary::store<std::int16_t>(destination + written * 2, static_cast<std::int16_t>(predictor));
        ++written;
    };
    while (reading_offset < source_size && written < sample_count) {
        if (bytes_in_block == 0) {
            if (reading_offset + 4 > source_size) {
                break;
            }
            step_index = std::clamp(static_cast<int>(static_cast<unsigned char>(source[reading_offset])), 0, 88);
            predictor = binary::load<std::int16_t>(source + reading_offset + 2);
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
    }
    return output.release();
}

PyObject* mod_awc_rsxxtea(PyObject*, PyObject* args) {
    BytesView source_view;
    PyObject* key_object = nullptr;
    int decrypt = 0;
    if (!PyArg_ParseTuple(args, "O&Op", parse_bytes_view, &source_view, &key_object, &decrypt)) {
        return nullptr;
    }
    const auto* source = source_view.data;
    const auto source_size = source_view.size;
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
        blocks[index] = binary::load<std::uint32_t>(source + index * 4U);
    }
    {
    GilRelease gil_release;
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
    }
    std::string output(static_cast<std::size_t>(source_size), '\0');
    for (std::size_t index = 0; index < block_count; ++index) {
        binary::store<std::uint32_t>(output.data() + index * 4U, blocks[index]);
    }
    return PyBytes_FromStringAndSize(output.data(), source_size);
}

PyObject* mod_awc_parse_pcm_wav(PyObject*, PyObject* args) {
    BytesView source_view;
    if (!PyArg_ParseTuple(args, "O&", parse_bytes_view, &source_view)) {
        return nullptr;
    }
    const auto* source = source_view.data;
    const auto source_size = source_view.size;
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
        const auto chunk_size = static_cast<Py_ssize_t>(binary::load<std::uint32_t>(source + offset + 4));
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
            audio_format = binary::load<std::uint16_t>(source + payload_start);
            channels = binary::load<std::uint16_t>(source + payload_start + 2);
            sample_rate = binary::load<std::uint32_t>(source + payload_start + 4);
            bits_per_sample = binary::load<std::uint16_t>(source + payload_start + 14);
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
    auto* pcm_bytes = PyBytes_FromStringAndSize(pcm, pcm_size);
    if (pcm_bytes == nullptr) return nullptr;
    return Py_BuildValue(
        "(NIHH)",
        pcm_bytes,
        sample_rate,
        channels,
        bits_per_sample
    );
}

PyObject* mod_awc_build_pcm_wav(PyObject*, PyObject* args) {
    BytesView pcm_view;
    unsigned int sample_rate = 0;
    unsigned int channels = 1;
    unsigned int bits_per_sample = 16;
    if (!PyArg_ParseTuple(
            args,
            "O&I|II",
            parse_bytes_view,
            &pcm_view,
            &sample_rate,
            &channels,
            &bits_per_sample
        )) {
        return nullptr;
    }
    const auto* pcm = pcm_view.data;
    const auto pcm_size = pcm_view.size;
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
    binary::store<std::uint32_t>(output.data() + 4, static_cast<std::uint32_t>(36ULL + padded_data_size));
    std::memcpy(output.data() + 8, "WAVEfmt ", 8);
    binary::store<std::uint32_t>(output.data() + 16, 16);
    binary::store<std::uint16_t>(output.data() + 20, 1);
    binary::store<std::uint16_t>(output.data() + 22, static_cast<std::uint16_t>(channels));
    binary::store<std::uint32_t>(output.data() + 24, sample_rate);
    binary::store<std::uint32_t>(output.data() + 28, static_cast<std::uint32_t>(byte_rate));
    binary::store<std::uint16_t>(output.data() + 32, static_cast<std::uint16_t>(block_align));
    binary::store<std::uint16_t>(output.data() + 34, static_cast<std::uint16_t>(bits_per_sample));
    std::memcpy(output.data() + 36, "data", 4);
    binary::store<std::uint32_t>(output.data() + 40, static_cast<std::uint32_t>(pcm_size));
    if (pcm_size != 0) {
        std::memcpy(output.data() + 44, pcm, static_cast<std::size_t>(pcm_size));
    }
    return PyBytes_FromStringAndSize(output.data(), static_cast<Py_ssize_t>(output.size()));
}

PyObject* mod_awc_extract_multichannel_blocks(PyObject*, PyObject* args) {
    BytesView source_view;
    Py_ssize_t block_count = 0;
    Py_ssize_t block_size = 0;
    Py_ssize_t channel_count = 0;
    if (!PyArg_ParseTuple(
            args,
            "O&nnn",
            parse_bytes_view,
            &source_view,
            &block_count,
            &block_size,
            &channel_count
        )) {
        return nullptr;
    }
    const auto* source = source_view.data;
    const auto source_size = source_view.size;
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
            counts[static_cast<std::size_t>(channel)] = static_cast<std::int32_t>(binary::load<std::uint32_t>(header + 4));
            samples[static_cast<std::size_t>(channel)] = static_cast<std::int32_t>(binary::load<std::uint32_t>(header + 12));
            encoded_sizes[static_cast<std::size_t>(channel)] = static_cast<std::int32_t>(binary::load<std::uint32_t>(header + 20));
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
            auto* payload = PyBytes_FromStringAndSize(block + cursor, stored_payload_size);
            if (payload == nullptr) { Py_DECREF(result); return nullptr; }
            PyObject* item = Py_BuildValue("(iN)", samples[static_cast<std::size_t>(channel)], payload);
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
