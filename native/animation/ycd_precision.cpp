#include "animation/bindings.h"
#include "math/vector.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

namespace fivefury_py {
namespace {
using namespace fivefury_native;

Vec4 sample(const Buffer& buffer, Py_ssize_t frame) {
    Vec4 result;
    std::memcpy(&result, static_cast<const char*>(buffer.buf) + frame * 4 * sizeof(double), 4 * sizeof(double));
    return result;
}

Vec4 evaluate(const Vec4& packed, int layout) {
    if (layout >= 0) return quat_reconstruct(packed, static_cast<std::size_t>(layout));
    return layout == -2 ? quat_normalize(packed) : packed;
}

double angle(double cosine) {
    return std::isfinite(cosine) ? 360.0 / std::acos(-1.0) * std::acos(cosine)
                                : std::numeric_limits<double>::infinity();
}
}

PyObject* mod_ycd_compare_samples(PyObject*, PyObject* args) {
    PyObject* reference_object;
    PyObject* packed_object;
    int dimensions, layout;
    int subframes;
    Py_ssize_t integer_count;
    if (!PyArg_ParseTuple(args, "OOiinp:ycd_compare_samples", &reference_object,
                          &packed_object, &dimensions, &layout, &integer_count, &subframes)) {
        return nullptr;
    }
    Buffer reference, packed;
    if (!reference.acquire(reference_object) || !packed.acquire(packed_object)) return nullptr;
    const auto stride = static_cast<Py_ssize_t>(4 * sizeof(double));
    if (dimensions < 1 || dimensions > 4 || layout < -2 || layout > 3 ||
        (dimensions != 4 && layout != -1) || reference.len != packed.len ||
        reference.len % stride != 0 || reference.len == 0) {
        PyErr_SetString(PyExc_ValueError, "Invalid YCD precision buffers or quaternion layout");
        return nullptr;
    }
    const Py_ssize_t count = reference.len / stride;
    if (integer_count < 0 || integer_count > count) {
        PyErr_SetString(PyExc_ValueError, "YCD integer sample count exceeds its buffers");
        return nullptr;
    }
    double maximum_error = 0.0, minimum_cosine = 1.0, minimum_subframe_cosine = 1.0;
    double worst_frame = 0.0;
    const auto component_error = [dimensions](const Vec4& expected, const Vec4& actual) {
        return dimensions == 4 ? quat_component_error(expected, actual)
                               : vec_max_component_error(expected, actual, dimensions);
    };
    {
        GilRelease released;
        for (Py_ssize_t frame = 0; frame < count; ++frame) {
            const Vec4 expected = sample(reference, frame);
            const Vec4 raw = sample(packed, frame);
            const Vec4 actual = evaluate(raw, layout);
            if (frame < integer_count) {
                maximum_error = std::max(maximum_error, component_error(expected, actual));
                if (dimensions == 4) minimum_cosine = std::min(minimum_cosine, quat_angular_cosine(expected, actual));
            }
            if (!subframes || frame + 1 == count) continue;
            const Vec4 next_reference = sample(reference, frame + 1);
            const Vec4 next_raw = sample(packed, frame + 1);
            for (double alpha : {0.25, 0.5, 0.75}) {
                const Vec4 expected_subframe = dimensions == 4
                    ? quat_nlerp(expected, next_reference, alpha)
                    : vec4_lerp(expected, next_reference, alpha);
                const Vec4 actual_subframe = dimensions != 4
                    ? vec4_lerp(raw, next_raw, alpha)
                    : layout == -1
                    ? quat_nlerp(raw, next_raw, alpha)
                    : evaluate(vec4_lerp(raw, next_raw, alpha), layout);
                maximum_error = std::max(maximum_error, component_error(expected_subframe, actual_subframe));
                if (dimensions != 4) continue;
                const double cosine = quat_angular_cosine(expected_subframe, actual_subframe);
                if (cosine < minimum_subframe_cosine) {
                    minimum_subframe_cosine = cosine;
                    worst_frame = static_cast<double>(frame) + alpha;
                }
            }
        }
    }
    return Py_BuildValue("(dddd)", maximum_error, angle(minimum_cosine), angle(minimum_subframe_cosine), worst_frame);
}
}
