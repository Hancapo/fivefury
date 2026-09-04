#include "animation/bindings.h"
#include "binary/primitives.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace fivefury_py {

namespace {

struct DecodeChannel {
    int kind = 0;
    std::size_t bit_offset = 0;
    int bit_count = 0;
    double quantum = 0.0;
    double offset = 0.0;
    std::vector<double> values;
    std::vector<std::uint32_t> indices;
};

struct EncodeChannel {
    int kind = 0;
    int bit_count = 0;
    std::vector<std::uint32_t> values;
};

bool valid_frame_channel(int kind, int bits) {
    if (kind < 3 || kind > 5) {
        PyErr_SetString(PyExc_ValueError, "YCD frame channel type must be 3, 4, or 5");
        return false;
    }
    if (bits < 0 || bits > 32 || (kind == 3 && bits != 32)) {
        PyErr_SetString(PyExc_ValueError, "YCD frame channel bit width is invalid");
        return false;
    }
    return true;
}

PyObject* build_value_pair(
    const std::vector<double>& values,
    const std::vector<std::uint32_t>& encoded
) {
    PyObject* decoded_list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    PyObject* encoded_list = PyList_New(static_cast<Py_ssize_t>(encoded.size()));
    if (decoded_list == nullptr || encoded_list == nullptr) {
        Py_XDECREF(decoded_list);
        Py_XDECREF(encoded_list);
        return nullptr;
    }
    for (std::size_t index = 0; index < values.size(); ++index) {
        PyList_SetItem(
            decoded_list,
            static_cast<Py_ssize_t>(index),
            PyFloat_FromDouble(values[index])
        );
    }
    for (std::size_t index = 0; index < encoded.size(); ++index) {
        PyList_SetItem(
            encoded_list,
            static_cast<Py_ssize_t>(index),
            PyLong_FromUnsignedLong(encoded[index])
        );
    }
    PyObject* result = PyTuple_New(2);
    if (result == nullptr) {
        Py_DECREF(decoded_list);
        Py_DECREF(encoded_list);
        return nullptr;
    }
    PyTuple_SetItem(result, 0, decoded_list);
    PyTuple_SetItem(result, 1, encoded_list);
    return result;
}

std::uint32_t read_bits(
    const auto* data,
    std::size_t data_size,
    std::size_t bit_offset,
    int bit_count
) {
    std::uint64_t value = 0;
    const int count = std::clamp(bit_count, 0, 32);
    for (int index = 0; index < count; ++index) {
        const auto source_bit = bit_offset + static_cast<std::size_t>(index);
        const auto byte_index = source_bit >> 3U;
        if (byte_index >= data_size) {
            break;
        }
        const auto bit = (data[byte_index] >> (source_bit & 7U)) & 1U;
        value |= static_cast<std::uint64_t>(bit) << index;
    }
    return static_cast<std::uint32_t>(value);
}

void write_bits(
    std::uint8_t* data,
    std::size_t data_size,
    std::size_t bit_offset,
    std::uint32_t value,
    int bit_count
) {
    const int count = std::clamp(bit_count, 0, 32);
    for (int index = 0; index < count; ++index) {
        const auto target_bit = bit_offset + static_cast<std::size_t>(index);
        const auto byte_index = target_bit >> 3U;
        if (byte_index >= data_size) {
            break;
        }
        const auto mask = static_cast<std::uint8_t>(1U << (target_bit & 7U));
        if (((value >> index) & 1U) != 0U) {
            data[byte_index] |= mask;
        }
    }
}

bool parse_decode_channels(PyObject* object, std::vector<DecodeChannel>& out) {
    PyHandle sequence_owner(PySequence_Fast(object, "YCD channel descriptors must be a sequence"));
    PyObject* sequence = sequence_owner.get();
    if (sequence == nullptr) {
        return false;
    }
    const auto count = PySequence_Size(sequence);
    out.reserve(static_cast<std::size_t>(std::max<Py_ssize_t>(count, 0)));
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        PyObject* descriptor = item == nullptr
            ? nullptr
            : PySequence_Fast(item, "YCD channel descriptor must be a sequence");
        Py_XDECREF(item);
        if (descriptor == nullptr) {
            return false;
        }
        if (PySequence_Size(descriptor) != 5) {
            Py_DECREF(descriptor);
            PyErr_SetString(PyExc_ValueError, "YCD decode descriptor must contain five values");
            return false;
        }
        PyObject* kind = PySequence_GetItem(descriptor, 0);
        PyObject* bit_offset = PySequence_GetItem(descriptor, 1);
        PyObject* bit_count = PySequence_GetItem(descriptor, 2);
        PyObject* quantum = PySequence_GetItem(descriptor, 3);
        PyObject* offset = PySequence_GetItem(descriptor, 4);
        DecodeChannel channel;
        channel.kind = static_cast<int>(PyLong_AsLong(kind));
        channel.bit_offset = static_cast<std::size_t>(PyLong_AsUnsignedLongLong(bit_offset));
        channel.bit_count = static_cast<int>(PyLong_AsLong(bit_count));
        channel.quantum = PyFloat_AsDouble(quantum);
        channel.offset = PyFloat_AsDouble(offset);
        Py_XDECREF(kind);
        Py_XDECREF(bit_offset);
        Py_XDECREF(bit_count);
        Py_XDECREF(quantum);
        Py_XDECREF(offset);
        Py_DECREF(descriptor);
        if (PyErr_Occurred() != nullptr) {
            return false;
        }
        if (!valid_frame_channel(channel.kind, channel.bit_count)) return false;
        out.push_back(std::move(channel));
    }
    return true;
}

bool parse_encode_channels(
    PyObject* object,
    Py_ssize_t num_frames,
    std::vector<EncodeChannel>& out
) {
    PyHandle sequence_owner(PySequence_Fast(object, "YCD channel descriptors must be a sequence"));
    PyObject* sequence = sequence_owner.get();
    if (sequence == nullptr) {
        return false;
    }
    const auto count = PySequence_Size(sequence);
    out.reserve(static_cast<std::size_t>(std::max<Py_ssize_t>(count, 0)));
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        PyObject* descriptor = item == nullptr
            ? nullptr
            : PySequence_Fast(item, "YCD channel descriptor must be a sequence");
        Py_XDECREF(item);
        if (descriptor == nullptr) {
            return false;
        }
        if (PySequence_Size(descriptor) != 3) {
            Py_DECREF(descriptor);
            PyErr_SetString(PyExc_ValueError, "YCD encode descriptor must contain three values");
            return false;
        }
        PyObject* kind = PySequence_GetItem(descriptor, 0);
        PyObject* bit_count = PySequence_GetItem(descriptor, 1);
        PyObject* values_object = PySequence_GetItem(descriptor, 2);
        EncodeChannel channel;
        channel.kind = static_cast<int>(PyLong_AsLong(kind));
        channel.bit_count = static_cast<int>(PyLong_AsLong(bit_count));
        Py_XDECREF(kind);
        Py_XDECREF(bit_count);
        if (PyErr_Occurred() != nullptr || !valid_frame_channel(channel.kind, channel.bit_count)) {
            Py_XDECREF(values_object);
            Py_DECREF(descriptor);
            return false;
        }
        PyHandle values_owner(PySequence_Fast(values_object, "YCD channel values must be a sequence"));
        PyObject* values = values_owner.get();
        Py_XDECREF(values_object);
        if (values == nullptr) {
            Py_DECREF(descriptor);
            return false;
        }
        const auto value_count = PySequence_Size(values);
        channel.values.reserve(static_cast<std::size_t>(std::max<Py_ssize_t>(num_frames, 0)));
        for (Py_ssize_t frame = 0; frame < num_frames; ++frame) {
            std::uint32_t value = 0;
            if (value_count > 0) {
                PyObject* value_object = PySequence_GetItem(values, frame % value_count);
                if (channel.kind == 3) {
                    const auto number = static_cast<float>(PyFloat_AsDouble(value_object));
                    std::memcpy(&value, &number, sizeof(value));
                } else {
                    value = static_cast<std::uint32_t>(PyLong_AsUnsignedLongLongMask(value_object));
                }
                Py_XDECREF(value_object);
                if (PyErr_Occurred() != nullptr) {
                    Py_DECREF(descriptor);
                    return false;
                }
            }
            channel.values.push_back(value);
        }
        Py_DECREF(descriptor);
        out.push_back(std::move(channel));
    }
    return true;
}

}  // namespace

PyObject* mod_ycd_decode_frame_channels(PyObject*, PyObject* args) {
    PyObject* data_object = nullptr;
    PyObject* descriptors_object = nullptr;
    Py_ssize_t num_frames = 0;
    Py_ssize_t frame_offset = 0;
    Py_ssize_t frame_length = 0;
    if (!PyArg_ParseTuple(
            args,
            "OnnnO",
            &data_object,
            &num_frames,
            &frame_offset,
            &frame_length,
            &descriptors_object
        )) {
        return nullptr;
    }
    if (num_frames < 0 || frame_offset < 0 || frame_length < 0) {
        PyErr_SetString(PyExc_ValueError, "YCD frame dimensions must be non-negative");
        return nullptr;
    }
    Buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    std::vector<DecodeChannel> channels;
    if (!parse_decode_channels(descriptors_object, channels)) {
        buffer.release();
        return nullptr;
    }
    const auto frame_bits = fivefury_native::binary::checked_product(
        static_cast<std::size_t>(frame_length), 8U);
    for (const auto& channel : channels) {
        if (!fivefury_native::binary::contains(
                channel.bit_offset, static_cast<std::size_t>(channel.bit_count), frame_bits)) {
            PyErr_SetString(PyExc_ValueError, "YCD channel extends beyond its frame");
            return nullptr;
        }
    }
    if (!channels.empty() && !fivefury_native::binary::contains(
            static_cast<std::size_t>(frame_offset),
            fivefury_native::binary::checked_product(
                static_cast<std::size_t>(num_frames), static_cast<std::size_t>(frame_length)),
            static_cast<std::size_t>(buffer.len))) {
        PyErr_SetString(PyExc_ValueError, "YCD frame data is truncated");
        return nullptr;
    }
    for (auto& channel : channels) {
        if (channel.kind == 5) {
            channel.indices.resize(static_cast<std::size_t>(num_frames));
        } else {
            channel.values.resize(static_cast<std::size_t>(num_frames));
        }
    }
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    const auto data_size = static_cast<std::size_t>(buffer.len);
    {
    GilRelease gil_release;
    for (Py_ssize_t frame = 0; frame < num_frames; ++frame) {
        const auto frame_base = (
            static_cast<std::size_t>(frame_offset) +
            static_cast<std::size_t>(frame_length) * static_cast<std::size_t>(frame)
        ) * 8U;
        for (auto& channel : channels) {
            const auto bits = read_bits(
                data,
                data_size,
                frame_base + channel.bit_offset,
                channel.bit_count
            );
            if (channel.kind == 3) {
                float value = 0.0F;
                std::memcpy(&value, &bits, sizeof(value));
                channel.values[static_cast<std::size_t>(frame)] = value;
            } else if (channel.kind == 4) {
                channel.values[static_cast<std::size_t>(frame)] =
                    static_cast<double>(bits) * channel.quantum + channel.offset;
            } else {
                channel.indices[static_cast<std::size_t>(frame)] = bits;
            }
        }
    }
    }
    buffer.release();

    PyObject* result = PyList_New(static_cast<Py_ssize_t>(channels.size()));
    if (result == nullptr) {
        return nullptr;
    }
    for (std::size_t channel_index = 0; channel_index < channels.size(); ++channel_index) {
        const auto& channel = channels[channel_index];
        PyObject* values = PyList_New(num_frames);
        if (values == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        for (Py_ssize_t frame = 0; frame < num_frames; ++frame) {
            PyObject* value = channel.kind == 5
                ? PyLong_FromUnsignedLong(channel.indices[static_cast<std::size_t>(frame)])
                : PyFloat_FromDouble(channel.values[static_cast<std::size_t>(frame)]);
            if (value == nullptr) {
                Py_DECREF(values);
                Py_DECREF(result);
                return nullptr;
            }
            PyList_SetItem(values, frame, value);
        }
        PyList_SetItem(result, static_cast<Py_ssize_t>(channel_index), values);
    }
    return result;
}

PyObject* mod_ycd_encode_frame_channels(PyObject*, PyObject* args) {
    Py_ssize_t num_frames = 0;
    PyObject* descriptors_object = nullptr;
    if (!PyArg_ParseTuple(args, "nO", &num_frames, &descriptors_object)) {
        return nullptr;
    }
    if (num_frames < 0) {
        PyErr_SetString(PyExc_ValueError, "YCD frame count must be non-negative");
        return nullptr;
    }
    std::vector<EncodeChannel> channels;
    if (!parse_encode_channels(descriptors_object, num_frames, channels)) {
        return nullptr;
    }
    std::size_t frame_bits = 0;
    for (const auto& channel : channels) {
        frame_bits += static_cast<std::size_t>(std::max(channel.bit_count, 0));
    }
    const auto frame_length = ((frame_bits + 31U) / 32U) * 4U;
    std::vector<std::uint8_t> output(
        fivefury_native::binary::checked_product(frame_length, static_cast<std::size_t>(num_frames)),
        0
    );
    {
    GilRelease gil_release;
    for (Py_ssize_t frame = 0; frame < num_frames; ++frame) {
        auto bit_offset = static_cast<std::size_t>(frame) * frame_length * 8U;
        for (const auto& channel : channels) {
            write_bits(
                output.data(),
                output.size(),
                bit_offset,
                channel.values[static_cast<std::size_t>(frame)],
                channel.bit_count
            );
            bit_offset += static_cast<std::size_t>(std::max(channel.bit_count, 0));
        }
    }
    }
    PyObject* data = PyBytes_FromStringAndSize(
        reinterpret_cast<const char*>(output.data()),
        static_cast<Py_ssize_t>(output.size())
    );
    if (data == nullptr) {
        return nullptr;
    }
    PyObject* result = PyTuple_New(2);
    if (result == nullptr) {
        Py_DECREF(data);
        return nullptr;
    }
    PyTuple_SetItem(result, 0, data);
    PyTuple_SetItem(result, 1, PyLong_FromSize_t(frame_length));
    return result;
}

PyObject* mod_ycd_decode_quantized_values(PyObject*, PyObject* args) {
    PyObject* data_object = nullptr;
    Py_ssize_t bit_offset = 0;
    Py_ssize_t count = 0;
    int bit_count = 0;
    double quantum = 0.0;
    double offset = 0.0;
    if (!PyArg_ParseTuple(
            args,
            "Onnidd",
            &data_object,
            &bit_offset,
            &count,
            &bit_count,
            &quantum,
            &offset
        )) {
        return nullptr;
    }
    if (bit_offset < 0 || count < 0 || bit_count < 0 || bit_count > 32) {
        PyErr_SetString(PyExc_ValueError, "Invalid YCD quantized channel dimensions");
        return nullptr;
    }
    Buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    std::vector<double> values(static_cast<std::size_t>(count));
    std::vector<std::uint32_t> encoded(static_cast<std::size_t>(count));
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    const auto data_size = static_cast<std::size_t>(buffer.len);
    {
    GilRelease gil_release;
    auto cursor = static_cast<std::size_t>(bit_offset);
    for (Py_ssize_t index = 0; index < count; ++index) {
        const auto bits = read_bits(data, data_size, cursor, bit_count);
        cursor += static_cast<std::size_t>(bit_count);
        encoded[static_cast<std::size_t>(index)] = bits;
        values[static_cast<std::size_t>(index)] =
            static_cast<double>(bits) * quantum + offset;
    }
    }
    buffer.release();
    return build_value_pair(values, encoded);
}

PyObject* mod_ycd_decode_linear_values(PyObject*, PyObject* args) {
    PyObject* data_object = nullptr;
    Py_ssize_t bit_offset = 0;
    Py_ssize_t num_frames = 0;
    int chunk_size = 0;
    std::uint32_t counts = 0;
    double quantum = 0.0;
    double offset = 0.0;
    if (!PyArg_ParseTuple(
            args,
            "OnniIdd",
            &data_object,
            &bit_offset,
            &num_frames,
            &chunk_size,
            &counts,
            &quantum,
            &offset
        )) {
        return nullptr;
    }
    if (bit_offset < 0 || num_frames < 0 || chunk_size <= 0) {
        PyErr_SetString(PyExc_ValueError, "Invalid YCD linear channel dimensions");
        return nullptr;
    }
    Buffer buffer{};
    if (PyObject_GetBuffer(data_object, &buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    const int count1 = static_cast<int>(counts & 0xFFU);
    const int count2 = static_cast<int>((counts >> 8U) & 0xFFU);
    const int count3 = static_cast<int>((counts >> 16U) & 0xFFU);
    if (count1 > 32 || count2 > 32 || count3 > 32) {
        buffer.release();
        PyErr_SetString(PyExc_ValueError, "YCD linear channel bit width exceeds 32");
        return nullptr;
    }
    const auto num_chunks = num_frames > 0
        ? (static_cast<std::size_t>(chunk_size) + static_cast<std::size_t>(num_frames) - 1U) /
            static_cast<std::size_t>(chunk_size)
        : 0U;
    std::vector<std::uint32_t> chunk_offsets(num_chunks);
    std::vector<std::uint32_t> chunk_values(num_chunks);
    std::vector<double> values(static_cast<std::size_t>(num_frames));
    std::vector<std::uint32_t> encoded(static_cast<std::size_t>(num_frames));
    const auto* data = static_cast<const std::uint8_t*>(buffer.buf);
    const auto data_size = static_cast<std::size_t>(buffer.len);
    const auto stream_length = data_size * 8U;
    {
    GilRelease gil_release;
    auto cursor = static_cast<std::size_t>(bit_offset);
    for (std::size_t index = 0; index < num_chunks; ++index) {
        chunk_offsets[index] = count1 > 0
            ? read_bits(data, data_size, cursor, count1)
            : 0U;
        cursor += static_cast<std::size_t>(count1);
    }
    for (std::size_t index = 0; index < num_chunks; ++index) {
        chunk_values[index] = count2 > 0
            ? read_bits(data, data_size, cursor, count2)
            : 0U;
        cursor += static_cast<std::size_t>(count2);
    }
    const auto delta_offset = static_cast<std::size_t>(bit_offset) +
        num_chunks * static_cast<std::size_t>(count1 + count2);
    for (std::size_t chunk_index = 0; chunk_index < num_chunks; ++chunk_index) {
        auto delta_cursor = delta_offset + chunk_offsets[chunk_index];
        std::int64_t value = chunk_values[chunk_index];
        std::int64_t increment = 0;
        const auto chunk_start = chunk_index * static_cast<std::size_t>(chunk_size);
        for (int local_frame = 0; local_frame < chunk_size; ++local_frame) {
            const auto frame_index = chunk_start + static_cast<std::size_t>(local_frame);
            if (frame_index >= static_cast<std::size_t>(num_frames)) {
                break;
            }
            encoded[frame_index] = static_cast<std::uint32_t>(value);
            values[frame_index] = static_cast<double>(value) * quantum + offset;
            if (local_frame + 1 >= chunk_size) {
                break;
            }
            std::uint64_t delta = count3 > 0
                ? read_bits(data, data_size, delta_cursor, count3)
                : 0U;
            delta_cursor += static_cast<std::size_t>(count3);
            const auto unary_start = delta_cursor;
            bool bit_found = false;
            while (!bit_found) {
                bit_found = read_bits(data, data_size, delta_cursor, 1) != 0U;
                ++delta_cursor;
                if (delta_cursor >= stream_length) {
                    break;
                }
            }
            delta |= (delta_cursor - unary_start - 1U) << count3;
            bool negative = false;
            if (delta != 0U) {
                negative = read_bits(data, data_size, delta_cursor, 1) != 0U;
                ++delta_cursor;
            }
            const auto signed_delta = negative
                ? -static_cast<std::int64_t>(delta)
                : static_cast<std::int64_t>(delta);
            increment += signed_delta;
            value += increment;
        }
    }
    }
    buffer.release();
    return build_value_pair(values, encoded);
}

}  // namespace fivefury_py
