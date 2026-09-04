#include "drawable/bindings.h"

#include <cmath>
#include <array>
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
    Buffer& buffer,
    std::size_t expected_size,
    const char* name
) {
    if (PyObject_GetBuffer(object, &buffer, PyBUF_SIMPLE) < 0) {
        return false;
    }
    if (buffer.len < 0 || static_cast<std::size_t>(buffer.len) != expected_size) {
        buffer.release();
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

struct SkinningDimensions {
    std::size_t vertex_count{};
    std::size_t bone_count{};
    std::size_t influence_count{};
    std::size_t vector_bytes{};
    std::size_t matrix_bytes{};
    std::size_t index_bytes{};
    std::size_t weight_bytes{};
};

bool resolve_skinning_dimensions(
    Py_ssize_t vertex_count_value,
    Py_ssize_t bone_count_value,
    Py_ssize_t influence_count_value,
    SkinningDimensions& dimensions
) {
    if (vertex_count_value < 0 || bone_count_value < 0 || influence_count_value <= 0) {
        PyErr_SetString(PyExc_ValueError, "skinning dimensions are invalid");
        return false;
    }
    dimensions.vertex_count = static_cast<std::size_t>(vertex_count_value);
    dimensions.bone_count = static_cast<std::size_t>(bone_count_value);
    dimensions.influence_count = static_cast<std::size_t>(influence_count_value);
    std::size_t vector_values = 0;
    std::size_t matrix_values = 0;
    std::size_t influence_values = 0;
    if (!checked_size(dimensions.vertex_count, 3U, vector_values) ||
        !checked_size(dimensions.bone_count, 16U, matrix_values) ||
        !checked_size(
            dimensions.vertex_count,
            dimensions.influence_count,
            influence_values
        ) ||
        !checked_size(vector_values, sizeof(float), dimensions.vector_bytes) ||
        !checked_size(matrix_values, sizeof(float), dimensions.matrix_bytes) ||
        !checked_size(
            influence_values,
            sizeof(std::uint32_t),
            dimensions.index_bytes
        ) ||
        !checked_size(influence_values, sizeof(float), dimensions.weight_bytes)) {
        PyErr_SetString(PyExc_OverflowError, "skinning dimensions overflow address space");
        return false;
    }
    return true;
}

bool acquire_writable_buffer(
    PyObject* object,
    Buffer& buffer,
    std::size_t expected_size,
    const char* name
) {
    if (PyObject_GetBuffer(object, &buffer, PyBUF_WRITABLE) < 0) {
        return false;
    }
    if (buffer.len < 0 || static_cast<std::size_t>(buffer.len) != expected_size) {
        buffer.release();
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

bool skin_vertex_buffers(
    const float* positions,
    const float* matrices,
    const std::uint32_t* indices,
    const float* weights,
    const float* normals,
    float* skinned_positions,
    float* skinned_normals,
    std::size_t vertex_count,
    std::size_t bone_count,
    std::size_t influence_count,
    bool normalize_weights,
    std::size_t& invalid_index
) {
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

        const float weight_scale = normalize_weights ? 1.0F / weight_sum : 1.0F;
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
                return false;
            }
            const float* matrix = matrices + (bone * 16U);
            out_px += weight * (
                (px * matrix[0]) + (py * matrix[4]) + (pz * matrix[8]) + matrix[12]
            );
            out_py += weight * (
                (px * matrix[1]) + (py * matrix[5]) + (pz * matrix[9]) + matrix[13]
            );
            out_pz += weight * (
                (px * matrix[2]) + (py * matrix[6]) + (pz * matrix[10]) + matrix[14]
            );
            if (normals != nullptr) {
                out_nx += weight * (
                    (nx * matrix[0]) + (ny * matrix[4]) + (nz * matrix[8])
                );
                out_ny += weight * (
                    (nx * matrix[1]) + (ny * matrix[5]) + (nz * matrix[9])
                );
                out_nz += weight * (
                    (nx * matrix[2]) + (ny * matrix[6]) + (nz * matrix[10])
                );
            }
        }
        skinned_positions[vector_offset] = out_px;
        skinned_positions[vector_offset + 1U] = out_py;
        skinned_positions[vector_offset + 2U] = out_pz;
        if (skinned_normals != nullptr) {
            const float length = std::sqrt(
                (out_nx * out_nx) + (out_ny * out_ny) + (out_nz * out_nz)
            );
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
    return true;
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

    Buffer local_buffer{};
    Buffer parent_buffer{};
    if (!acquire_buffer(local_object, local_buffer, matrix_bytes, "local matrices")) {
        return nullptr;
    }
    if (!acquire_buffer(parents_object, parent_buffer, parent_bytes, "parent indices")) {
        local_buffer.release();
        return nullptr;
    }

    PyObject* output_object = PyByteArray_FromStringAndSize(nullptr, static_cast<Py_ssize_t>(matrix_bytes));
    if (output_object == nullptr) {
        parent_buffer.release();
        local_buffer.release();
        return nullptr;
    }
    const auto* local = static_cast<const float*>(local_buffer.buf);
    const auto* parents = static_cast<const std::int32_t*>(parent_buffer.buf);
    auto* output = reinterpret_cast<float*>(PyByteArray_AsString(output_object));
    std::vector<std::uint8_t> states(count, 0U);
    std::vector<std::size_t> path;
    path.reserve(count);
    bool cycle = false;

    {
    GilRelease gil_release;
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
    }

    parent_buffer.release();
    local_buffer.release();
    if (cycle) {
        Py_DECREF(output_object);
        PyErr_SetString(PyExc_ValueError, "Skeleton bone hierarchy contains a cycle");
        return nullptr;
    }
    return output_object;
}

PyObject* mod_skin_vertices_into(PyObject*, PyObject* args) {
    PyObject* positions_object = nullptr;
    PyObject* matrices_object = nullptr;
    PyObject* indices_object = nullptr;
    PyObject* weights_object = nullptr;
    PyObject* normals_object = nullptr;
    PyObject* positions_output_object = nullptr;
    PyObject* normals_output_object = nullptr;
    Py_ssize_t vertex_count_value = 0;
    Py_ssize_t bone_count_value = 0;
    Py_ssize_t influence_count_value = 0;
    int normalize_weights = 1;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOOOnnnp:skin_vertices_into",
            &positions_object,
            &matrices_object,
            &indices_object,
            &weights_object,
            &normals_object,
            &positions_output_object,
            &normals_output_object,
            &vertex_count_value,
            &bone_count_value,
            &influence_count_value,
            &normalize_weights
        )) {
        return nullptr;
    }
    if ((normals_object == Py_None) != (normals_output_object == Py_None)) {
        PyErr_SetString(
            PyExc_ValueError,
            "normals and output normals must either both be present or both be absent"
        );
        return nullptr;
    }

    SkinningDimensions dimensions;
    if (!resolve_skinning_dimensions(
            vertex_count_value,
            bone_count_value,
            influence_count_value,
            dimensions
        )) {
        return nullptr;
    }

    Buffer positions_buffer{};
    Buffer matrices_buffer{};
    Buffer indices_buffer{};
    Buffer weights_buffer{};
    Buffer normals_buffer{};
    Buffer positions_output_buffer{};
    Buffer normals_output_buffer{};
    if (!acquire_buffer(
            positions_object,
            positions_buffer,
            dimensions.vector_bytes,
            "positions"
        )) {
        return nullptr;
    }
    if (!acquire_buffer(
            matrices_object,
            matrices_buffer,
            dimensions.matrix_bytes,
            "matrices"
        ) ||
        !acquire_buffer(
            indices_object,
            indices_buffer,
            dimensions.index_bytes,
            "blend indices"
        ) ||
        !acquire_buffer(
            weights_object,
            weights_buffer,
            dimensions.weight_bytes,
            "blend weights"
        ) ||
        (normals_object != Py_None &&
         !acquire_buffer(
             normals_object,
             normals_buffer,
             dimensions.vector_bytes,
             "normals"
         )) ||
        !acquire_writable_buffer(
            positions_output_object,
            positions_output_buffer,
            dimensions.vector_bytes,
            "output positions"
        ) ||
        (normals_output_object != Py_None &&
         !acquire_writable_buffer(
             normals_output_object,
             normals_output_buffer,
             dimensions.vector_bytes,
             "output normals"
         ))) {
        if (normals_output_buffer.obj != nullptr) normals_output_buffer.release();
        if (positions_output_buffer.obj != nullptr) positions_output_buffer.release();
        if (normals_buffer.obj != nullptr) normals_buffer.release();
        if (weights_buffer.obj != nullptr) weights_buffer.release();
        if (indices_buffer.obj != nullptr) indices_buffer.release();
        if (matrices_buffer.obj != nullptr) matrices_buffer.release();
        positions_buffer.release();
        return nullptr;
    }

    const std::array<const Buffer*, 5> inputs{
        &positions_buffer, &matrices_buffer, &indices_buffer, &weights_buffer, &normals_buffer,
    };
    for (const auto* input : inputs) {
        if (positions_output_buffer.overlaps(*input) || normals_output_buffer.overlaps(*input)) {
            PyErr_SetString(PyExc_ValueError, "skinning output must not overlap input buffers");
            return nullptr;
        }
    }
    if (positions_output_buffer.overlaps(normals_output_buffer)) {
        PyErr_SetString(PyExc_ValueError, "skinning output buffers must not overlap each other");
        return nullptr;
    }

    std::size_t invalid_index = 0;
    bool valid_indices = false;
    {
    GilRelease gil_release;
    valid_indices = skin_vertex_buffers(
        static_cast<const float*>(positions_buffer.buf),
        static_cast<const float*>(matrices_buffer.buf),
        static_cast<const std::uint32_t*>(indices_buffer.buf),
        static_cast<const float*>(weights_buffer.buf),
        normals_object == Py_None
            ? nullptr
            : static_cast<const float*>(normals_buffer.buf),
        static_cast<float*>(positions_output_buffer.buf),
        normals_output_object == Py_None
            ? nullptr
            : static_cast<float*>(normals_output_buffer.buf),
        dimensions.vertex_count,
        dimensions.bone_count,
        dimensions.influence_count,
        normalize_weights != 0,
        invalid_index
    );
    }

    if (normals_output_buffer.obj != nullptr) normals_output_buffer.release();
    positions_output_buffer.release();
    if (normals_buffer.obj != nullptr) normals_buffer.release();
    weights_buffer.release();
    indices_buffer.release();
    matrices_buffer.release();
    positions_buffer.release();
    if (!valid_indices) {
        PyErr_Format(
            PyExc_ValueError,
            "blend index %zu is outside the %zu available matrices",
            invalid_index,
            dimensions.bone_count
        );
        return nullptr;
    }
    Py_RETURN_NONE;
}

PyObject* mod_skin_pack_palette_into(PyObject*, PyObject* args) {
    PyObject* matrices_object = nullptr;
    PyObject* output_object = nullptr;
    Py_ssize_t bone_count_value = 0;
    if (!PyArg_ParseTuple(
            args,
            "OOn:skin_pack_palette_into",
            &matrices_object,
            &output_object,
            &bone_count_value
        )) {
        return nullptr;
    }
    if (bone_count_value < 0) {
        PyErr_SetString(PyExc_ValueError, "bone count cannot be negative");
        return nullptr;
    }

    const auto bone_count = static_cast<std::size_t>(bone_count_value);
    std::size_t matrix_values = 0;
    std::size_t palette_values = 0;
    std::size_t matrix_bytes = 0;
    std::size_t palette_bytes = 0;
    if (!checked_size(bone_count, 16U, matrix_values) ||
        !checked_size(bone_count, 12U, palette_values) ||
        !checked_size(matrix_values, sizeof(float), matrix_bytes) ||
        !checked_size(palette_values, sizeof(float), palette_bytes)) {
        PyErr_SetString(PyExc_OverflowError, "bone palette dimensions overflow address space");
        return nullptr;
    }

    Buffer matrices_buffer{};
    Buffer output_buffer{};
    if (!acquire_buffer(
            matrices_object,
            matrices_buffer,
            matrix_bytes,
            "matrices"
        )) {
        return nullptr;
    }
    if (!acquire_writable_buffer(
            output_object,
            output_buffer,
            palette_bytes,
            "output palette"
        )) {
        matrices_buffer.release();
        return nullptr;
    }

    if (output_buffer.overlaps(matrices_buffer)) {
        PyErr_SetString(PyExc_ValueError, "palette output must not overlap matrices");
        return nullptr;
    }
    const auto* matrices = static_cast<const float*>(matrices_buffer.buf);
    auto* palette = static_cast<float*>(output_buffer.buf);
    {
    GilRelease gil_release;
    for (std::size_t bone = 0; bone < bone_count; ++bone) {
        const float* source = matrices + (bone * 16U);
        float* target = palette + (bone * 12U);
        target[0] = source[0];
        target[1] = source[4];
        target[2] = source[8];
        target[3] = source[12];
        target[4] = source[1];
        target[5] = source[5];
        target[6] = source[9];
        target[7] = source[13];
        target[8] = source[2];
        target[9] = source[6];
        target[10] = source[10];
        target[11] = source[14];
    }
    }

    output_buffer.release();
    matrices_buffer.release();
    Py_RETURN_NONE;
}

}  // namespace fivefury_py
