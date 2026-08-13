#include "py_bindings.h"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <vector>

namespace fivefury_py {

namespace {

bool checked_size(std::size_t count, std::size_t width, std::size_t& result) {
    if (width != 0U && count > std::numeric_limits<std::size_t>::max() / width) {
        return false;
    }
    result = count * width;
    return true;
}

bool acquire_buffer(
    PyObject* object,
    Py_buffer& buffer,
    std::size_t expected_size,
    const char* name
) {
    if (PyObject_GetBuffer(object, &buffer, PyBUF_SIMPLE) < 0) {
        return false;
    }
    if (buffer.len < 0 || static_cast<std::size_t>(buffer.len) != expected_size) {
        PyBuffer_Release(&buffer);
        PyErr_Format(
            PyExc_ValueError,
            "%s buffer has %zd bytes; expected %zu",
            name,
            buffer.len,
            expected_size
        );
        return false;
    }
    return true;
}

void multiply_matrix4(const float* left, const float* right, float* output) {
    float result[16]{};
    for (std::size_t row = 0; row < 4U; ++row) {
        for (std::size_t column = 0; column < 4U; ++column) {
            result[(row * 4U) + column] =
                (left[(row * 4U)] * right[column]) +
                (left[(row * 4U) + 1U] * right[4U + column]) +
                (left[(row * 4U) + 2U] * right[8U + column]) +
                (left[(row * 4U) + 3U] * right[12U + column]);
        }
    }
    std::memcpy(output, result, sizeof(result));
}

}  // namespace

PyObject* mod_skin_compose_matrices(PyObject*, PyObject* args) {
    PyObject* local_object = nullptr;
    PyObject* parents_object = nullptr;
    Py_ssize_t count_value = 0;
    if (!PyArg_ParseTuple(
            args,
            "OOn:skin_compose_matrices",
            &local_object,
            &parents_object,
            &count_value
        )) {
        return nullptr;
    }
    if (count_value < 0) {
        PyErr_SetString(PyExc_ValueError, "matrix count cannot be negative");
        return nullptr;
    }

    const auto count = static_cast<std::size_t>(count_value);
    std::size_t matrix_values = 0;
    std::size_t matrix_bytes = 0;
    std::size_t parent_bytes = 0;
    if (!checked_size(count, 16U, matrix_values) ||
        !checked_size(matrix_values, sizeof(float), matrix_bytes) ||
        !checked_size(count, sizeof(std::int32_t), parent_bytes)) {
        PyErr_SetString(PyExc_OverflowError, "skeleton dimensions overflow address space");
        return nullptr;
    }

    Py_buffer local_buffer{};
    Py_buffer parent_buffer{};
    if (!acquire_buffer(local_object, local_buffer, matrix_bytes, "local matrices")) {
        return nullptr;
    }
    if (!acquire_buffer(parents_object, parent_buffer, parent_bytes, "parent indices")) {
        PyBuffer_Release(&local_buffer);
        return nullptr;
    }

    PyObject* output_object = PyByteArray_FromStringAndSize(nullptr, static_cast<Py_ssize_t>(matrix_bytes));
    if (output_object == nullptr) {
        PyBuffer_Release(&parent_buffer);
        PyBuffer_Release(&local_buffer);
        return nullptr;
    }
    const auto* local = static_cast<const float*>(local_buffer.buf);
    const auto* parents = static_cast<const std::int32_t*>(parent_buffer.buf);
    auto* output = reinterpret_cast<float*>(PyByteArray_AsString(output_object));
    std::vector<std::uint8_t> states(count, 0U);
    std::vector<std::size_t> path;
    path.reserve(count);
    bool cycle = false;

    Py_BEGIN_ALLOW_THREADS
    for (std::size_t start = 0; start < count && !cycle; ++start) {
        if (states[start] == 2U) {
            continue;
        }
        path.clear();
        auto current = start;
        while (states[current] == 0U) {
            states[current] = 1U;
            path.push_back(current);
            const auto parent = parents[current];
            if (parent < 0 || static_cast<std::size_t>(parent) >= count ||
                static_cast<std::size_t>(parent) == current) {
                break;
            }
            current = static_cast<std::size_t>(parent);
        }
        if (states[current] == 1U && (path.empty() || current != path.back())) {
            cycle = true;
            break;
        }
        while (!path.empty()) {
            const auto index = path.back();
            path.pop_back();
            const auto parent = parents[index];
            float* target = output + (index * 16U);
            if (parent >= 0 && static_cast<std::size_t>(parent) < count &&
                static_cast<std::size_t>(parent) != index) {
                multiply_matrix4(
                    local + (index * 16U),
                    output + (static_cast<std::size_t>(parent) * 16U),
                    target
                );
            } else {
                std::memcpy(target, local + (index * 16U), 16U * sizeof(float));
            }
            states[index] = 2U;
        }
    }
    Py_END_ALLOW_THREADS

    PyBuffer_Release(&parent_buffer);
    PyBuffer_Release(&local_buffer);
    if (cycle) {
        Py_DECREF(output_object);
        PyErr_SetString(PyExc_ValueError, "Skeleton bone hierarchy contains a cycle");
        return nullptr;
    }
    return output_object;
}

PyObject* mod_skin_vertices(PyObject*, PyObject* args) {
    PyObject* positions_object = nullptr;
    PyObject* matrices_object = nullptr;
    PyObject* indices_object = nullptr;
    PyObject* weights_object = nullptr;
    PyObject* normals_object = nullptr;
    Py_ssize_t vertex_count_value = 0;
    Py_ssize_t bone_count_value = 0;
    Py_ssize_t influence_count_value = 0;
    int normalize_weights = 1;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOnnnp:skin_vertices",
            &positions_object,
            &matrices_object,
            &indices_object,
            &weights_object,
            &normals_object,
            &vertex_count_value,
            &bone_count_value,
            &influence_count_value,
            &normalize_weights
        )) {
        return nullptr;
    }
    if (vertex_count_value < 0 || bone_count_value < 0 || influence_count_value <= 0) {
        PyErr_SetString(PyExc_ValueError, "skinning dimensions are invalid");
        return nullptr;
    }

    const auto vertex_count = static_cast<std::size_t>(vertex_count_value);
    const auto bone_count = static_cast<std::size_t>(bone_count_value);
    const auto influence_count = static_cast<std::size_t>(influence_count_value);
    std::size_t vector_values = 0;
    std::size_t matrix_values = 0;
    std::size_t influence_values = 0;
    std::size_t vector_bytes = 0;
    std::size_t matrix_bytes = 0;
    std::size_t index_bytes = 0;
    std::size_t weight_bytes = 0;
    if (!checked_size(vertex_count, 3U, vector_values) ||
        !checked_size(bone_count, 16U, matrix_values) ||
        !checked_size(vertex_count, influence_count, influence_values) ||
        !checked_size(vector_values, sizeof(float), vector_bytes) ||
        !checked_size(matrix_values, sizeof(float), matrix_bytes) ||
        !checked_size(influence_values, sizeof(std::uint32_t), index_bytes) ||
        !checked_size(influence_values, sizeof(float), weight_bytes)) {
        PyErr_SetString(PyExc_OverflowError, "skinning dimensions overflow address space");
        return nullptr;
    }

    Py_buffer positions_buffer{};
    Py_buffer matrices_buffer{};
    Py_buffer indices_buffer{};
    Py_buffer weights_buffer{};
    Py_buffer normals_buffer{};
    if (!acquire_buffer(positions_object, positions_buffer, vector_bytes, "positions")) {
        return nullptr;
    }
    if (!acquire_buffer(matrices_object, matrices_buffer, matrix_bytes, "matrices") ||
        !acquire_buffer(indices_object, indices_buffer, index_bytes, "blend indices") ||
        !acquire_buffer(weights_object, weights_buffer, weight_bytes, "blend weights") ||
        (normals_object != Py_None &&
         !acquire_buffer(normals_object, normals_buffer, vector_bytes, "normals"))) {
        if (normals_buffer.obj != nullptr) PyBuffer_Release(&normals_buffer);
        if (weights_buffer.obj != nullptr) PyBuffer_Release(&weights_buffer);
        if (indices_buffer.obj != nullptr) PyBuffer_Release(&indices_buffer);
        if (matrices_buffer.obj != nullptr) PyBuffer_Release(&matrices_buffer);
        PyBuffer_Release(&positions_buffer);
        return nullptr;
    }

    PyObject* positions_output = PyByteArray_FromStringAndSize(nullptr, static_cast<Py_ssize_t>(vector_bytes));
    PyObject* normals_output = normals_object == Py_None
        ? nullptr
        : PyByteArray_FromStringAndSize(nullptr, static_cast<Py_ssize_t>(vector_bytes));
    if (positions_output == nullptr || (normals_object != Py_None && normals_output == nullptr)) {
        Py_XDECREF(normals_output);
        Py_XDECREF(positions_output);
        if (normals_buffer.obj != nullptr) PyBuffer_Release(&normals_buffer);
        PyBuffer_Release(&weights_buffer);
        PyBuffer_Release(&indices_buffer);
        PyBuffer_Release(&matrices_buffer);
        PyBuffer_Release(&positions_buffer);
        return nullptr;
    }

    const auto* positions = static_cast<const float*>(positions_buffer.buf);
    const auto* matrices = static_cast<const float*>(matrices_buffer.buf);
    const auto* indices = static_cast<const std::uint32_t*>(indices_buffer.buf);
    const auto* weights = static_cast<const float*>(weights_buffer.buf);
    const auto* normals = normals_object == Py_None
        ? nullptr
        : static_cast<const float*>(normals_buffer.buf);
    auto* skinned_positions = reinterpret_cast<float*>(PyByteArray_AsString(positions_output));
    auto* skinned_normals = normals_output == nullptr
        ? nullptr
        : reinterpret_cast<float*>(PyByteArray_AsString(normals_output));
    std::size_t invalid_index = bone_count;

    Py_BEGIN_ALLOW_THREADS
    for (std::size_t vertex = 0; vertex < vertex_count; ++vertex) {
        const auto vector_offset = vertex * 3U;
        const auto influence_offset = vertex * influence_count;
        float weight_sum = 0.0F;
        for (std::size_t influence = 0; influence < influence_count; ++influence) {
            weight_sum += weights[influence_offset + influence];
        }
        if (weight_sum <= 1.0e-8F) {
            std::memcpy(
                skinned_positions + vector_offset,
                positions + vector_offset,
                3U * sizeof(float)
            );
            if (skinned_normals != nullptr) {
                std::memcpy(
                    skinned_normals + vector_offset,
                    normals + vector_offset,
                    3U * sizeof(float)
                );
            }
            continue;
        }

        const float weight_scale = normalize_weights != 0 ? 1.0F / weight_sum : 1.0F;
        const float px = positions[vector_offset];
        const float py = positions[vector_offset + 1U];
        const float pz = positions[vector_offset + 2U];
        const float nx = normals == nullptr ? 0.0F : normals[vector_offset];
        const float ny = normals == nullptr ? 0.0F : normals[vector_offset + 1U];
        const float nz = normals == nullptr ? 0.0F : normals[vector_offset + 2U];
        float out_px = 0.0F;
        float out_py = 0.0F;
        float out_pz = 0.0F;
        float out_nx = 0.0F;
        float out_ny = 0.0F;
        float out_nz = 0.0F;
        for (std::size_t influence = 0; influence < influence_count; ++influence) {
            const auto source_index = influence_offset + influence;
            const float weight = weights[source_index] * weight_scale;
            if (weight == 0.0F) {
                continue;
            }
            const auto bone = static_cast<std::size_t>(indices[source_index]);
            if (bone >= bone_count) {
                invalid_index = bone;
                break;
            }
            const float* matrix = matrices + (bone * 16U);
            out_px += weight * ((px * matrix[0]) + (py * matrix[4]) + (pz * matrix[8]) + matrix[12]);
            out_py += weight * ((px * matrix[1]) + (py * matrix[5]) + (pz * matrix[9]) + matrix[13]);
            out_pz += weight * ((px * matrix[2]) + (py * matrix[6]) + (pz * matrix[10]) + matrix[14]);
            if (normals != nullptr) {
                out_nx += weight * ((nx * matrix[0]) + (ny * matrix[4]) + (nz * matrix[8]));
                out_ny += weight * ((nx * matrix[1]) + (ny * matrix[5]) + (nz * matrix[9]));
                out_nz += weight * ((nx * matrix[2]) + (ny * matrix[6]) + (nz * matrix[10]));
            }
        }
        if (invalid_index != bone_count) {
            break;
        }
        skinned_positions[vector_offset] = out_px;
        skinned_positions[vector_offset + 1U] = out_py;
        skinned_positions[vector_offset + 2U] = out_pz;
        if (skinned_normals != nullptr) {
            const float length = std::sqrt((out_nx * out_nx) + (out_ny * out_ny) + (out_nz * out_nz));
            if (length > 1.0e-8F) {
                const float inverse_length = 1.0F / length;
                out_nx *= inverse_length;
                out_ny *= inverse_length;
                out_nz *= inverse_length;
            }
            skinned_normals[vector_offset] = out_nx;
            skinned_normals[vector_offset + 1U] = out_ny;
            skinned_normals[vector_offset + 2U] = out_nz;
        }
    }
    Py_END_ALLOW_THREADS

    if (normals_buffer.obj != nullptr) PyBuffer_Release(&normals_buffer);
    PyBuffer_Release(&weights_buffer);
    PyBuffer_Release(&indices_buffer);
    PyBuffer_Release(&matrices_buffer);
    PyBuffer_Release(&positions_buffer);
    if (invalid_index != bone_count) {
        Py_XDECREF(normals_output);
        Py_DECREF(positions_output);
        PyErr_Format(
            PyExc_ValueError,
            "blend index %zu is outside the %zu available matrices",
            invalid_index,
            bone_count
        );
        return nullptr;
    }

    PyObject* result = PyTuple_New(2);
    if (result == nullptr) {
        Py_XDECREF(normals_output);
        Py_DECREF(positions_output);
        return nullptr;
    }
    PyTuple_SetItem(result, 0, positions_output);
    if (normals_output == nullptr) {
        Py_INCREF(Py_None);
        PyTuple_SetItem(result, 1, Py_None);
    } else {
        PyTuple_SetItem(result, 1, normals_output);
    }
    return result;
}

}  // namespace fivefury_py
