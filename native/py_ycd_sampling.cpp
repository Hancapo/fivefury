#include "py_bindings.h"

#include "vector_math.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <memory>
#include <vector>

namespace fivefury_py {
namespace {

constexpr const char* CAPSULE_NAME = "fivefury.YcdTrackSampler";

enum class TrackFormat : int {
    Vector3 = 0,
    Quaternion = 1,
    Float = 2,
};

struct TrackSampler {
    TrackFormat format = TrackFormat::Float;
    std::size_t frame_count = 0;
    std::size_t dense_start = 0;
    bool dense = false;
    std::vector<int> frames;
    std::vector<fivefury_native::Vec4> values;
};

void destroy_sampler(PyObject* capsule) {
    auto* sampler = static_cast<TrackSampler*>(
        PyCapsule_GetPointer(capsule, CAPSULE_NAME)
    );
    if (sampler != nullptr) {
        delete sampler;
    } else {
        PyErr_Clear();
    }
}

TrackSampler* require_sampler(PyObject* capsule) {
    return static_cast<TrackSampler*>(PyCapsule_GetPointer(capsule, CAPSULE_NAME));
}

bool read_component(PyObject* value, const char* name, double& result) {
    PyObject* component = PyObject_GetAttrString(value, name);
    if (component == nullptr) {
        return false;
    }
    result = PyFloat_AsDouble(component);
    Py_DECREF(component);
    return PyErr_Occurred() == nullptr;
}

bool parse_sample(
    PyObject* value,
    TrackFormat format,
    PyObject* vector3_type,
    PyObject* quaternion_type,
    fivefury_native::Vec4& result
) {
    result = {};
    if (format == TrackFormat::Float) {
        result.x = PyFloat_AsDouble(value);
        return PyErr_Occurred() == nullptr;
    }

    PyObject* expected_type = format == TrackFormat::Quaternion
        ? quaternion_type
        : vector3_type;
    const int matches = PyObject_IsInstance(value, expected_type);
    if (matches < 0) {
        return false;
    }
    if (matches == 0) {
        PyErr_SetString(
            PyExc_TypeError,
            format == TrackFormat::Quaternion
                ? "Quaternion tracks require Quaternion samples"
                : "Vector3 tracks require Vector3 samples"
        );
        return false;
    }

    if (!read_component(value, "x", result.x) ||
        !read_component(value, "y", result.y) ||
        !read_component(value, "z", result.z)) {
        return false;
    }
    if (format != TrackFormat::Quaternion) {
        return true;
    }
    if (!read_component(value, "w", result.w)) {
        return false;
    }
    if (!std::isfinite(result.x) || !std::isfinite(result.y) ||
        !std::isfinite(result.z) || !std::isfinite(result.w)) {
        PyErr_SetString(PyExc_ValueError, "Quaternion components must be finite");
        return false;
    }
    const double length = std::sqrt(
        result.x * result.x + result.y * result.y +
        result.z * result.z + result.w * result.w
    );
    if (length <= 1e-12) {
        PyErr_SetString(
            PyExc_ValueError,
            "Quaternion length must be greater than zero"
        );
        return false;
    }
    const double inverse = 1.0 / length;
    result.x *= inverse;
    result.y *= inverse;
    result.z *= inverse;
    result.w *= inverse;
    return true;
}

double dot(
    const fivefury_native::Vec4& left,
    const fivefury_native::Vec4& right
) {
    return left.x * right.x + left.y * right.y +
           left.z * right.z + left.w * right.w;
}

bool equal(
    const fivefury_native::Vec4& left,
    const fivefury_native::Vec4& right,
    TrackFormat format
) {
    const int count = format == TrackFormat::Float
        ? 1
        : (format == TrackFormat::Vector3 ? 3 : 4);
    for (int index = 0; index < count; ++index) {
        if (left[static_cast<std::size_t>(index)] !=
            right[static_cast<std::size_t>(index)]) {
            return false;
        }
    }
    return true;
}

bool parse_values(
    PyObject* source,
    TrackFormat format,
    PyObject* vector3_type,
    PyObject* quaternion_type,
    std::vector<fivefury_native::Vec4>& values
) {
    PyObject* sequence = PySequence_Fast(source, "samples must be a sequence");
    if (sequence == nullptr) {
        return false;
    }
    const Py_ssize_t count = PySequence_Size(sequence);
    values.reserve(static_cast<std::size_t>(count));
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        fivefury_native::Vec4 value;
        const bool valid = item != nullptr && parse_sample(
            item,
            format,
            vector3_type,
            quaternion_type,
            value
        );
        Py_XDECREF(item);
        if (!valid) {
            Py_DECREF(sequence);
            return false;
        }
        if (format == TrackFormat::Quaternion && !values.empty() &&
            dot(values.back(), value) < 0.0) {
            value = {-value.x, -value.y, -value.z, -value.w};
        }
        values.push_back(value);
    }
    Py_DECREF(sequence);
    return true;
}

bool parse_frames(PyObject* source, std::vector<int>& frames) {
    PyObject* sequence = PySequence_Fast(source, "frames must be a sequence");
    if (sequence == nullptr) {
        return false;
    }
    const Py_ssize_t count = PySequence_Size(sequence);
    frames.reserve(static_cast<std::size_t>(count));
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* item = PySequence_GetItem(sequence, index);
        const long value = item == nullptr ? -1 : PyLong_AsLong(item);
        Py_XDECREF(item);
        if (PyErr_Occurred() != nullptr) {
            Py_DECREF(sequence);
            return false;
        }
        frames.push_back(static_cast<int>(value));
    }
    Py_DECREF(sequence);
    return true;
}

void trim_dense_storage(TrackSampler& sampler) {
    if (sampler.values.size() <= 1) {
        return;
    }
    std::size_t start = 0;
    while (start + 1 < sampler.values.size() &&
           equal(sampler.values[start + 1], sampler.values.front(), sampler.format)) {
        ++start;
    }
    std::size_t end = sampler.values.size() - 1;
    while (end > start &&
           equal(sampler.values[end - 1], sampler.values.back(), sampler.format)) {
        --end;
    }
    if (start == 0 && end + 1 == sampler.values.size()) {
        return;
    }
    std::vector<fivefury_native::Vec4> retained(
        sampler.values.begin() + static_cast<std::ptrdiff_t>(start),
        sampler.values.begin() + static_cast<std::ptrdiff_t>(end + 1)
    );
    sampler.values.swap(retained);
    sampler.dense_start = start;
}

fivefury_native::Vec4 sample_at(const TrackSampler& sampler, std::size_t frame) {
    if (sampler.values.size() == 1) {
        return sampler.values.front();
    }
    if (sampler.dense) {
        if (frame <= sampler.dense_start) {
            return sampler.values.front();
        }
        const std::size_t relative = frame - sampler.dense_start;
        return sampler.values[std::min(relative, sampler.values.size() - 1)];
    }

    const auto upper = std::upper_bound(
        sampler.frames.begin(),
        sampler.frames.end(),
        static_cast<int>(frame)
    );
    if (upper == sampler.frames.begin()) {
        return sampler.values.front();
    }
    if (upper == sampler.frames.end()) {
        return sampler.values.back();
    }
    const std::size_t right = static_cast<std::size_t>(
        std::distance(sampler.frames.begin(), upper)
    );
    const std::size_t left = right - 1;
    const int start_frame = sampler.frames[left];
    const int end_frame = sampler.frames[right];
    const double alpha = static_cast<double>(
        static_cast<int>(frame) - start_frame
    ) / static_cast<double>(std::max(end_frame - start_frame, 1));
    return sampler.format == TrackFormat::Quaternion
        ? fivefury_native::quat_nlerp(
            sampler.values[left], sampler.values[right], alpha
        )
        : fivefury_native::vec4_lerp(
            sampler.values[left], sampler.values[right], alpha
        );
}

int component_count(TrackFormat format) {
    if (format == TrackFormat::Float) {
        return 1;
    }
    return format == TrackFormat::Vector3 ? 3 : 4;
}

int orient_cached_quaternions(std::vector<fivefury_native::Vec4>& values) {
    std::array<std::array<double, 4>, 4> scores{};
    for (int component = 0; component < 4; ++component) {
        double minimum = std::numeric_limits<double>::infinity();
        double mean_square = 0.0;
        double peak = 0.0;
        for (const auto& value : values) {
            const double magnitude = std::abs(value[static_cast<std::size_t>(component)]);
            minimum = std::min(minimum, magnitude);
            mean_square += magnitude * magnitude;
            peak = std::max(peak, magnitude);
        }
        scores[static_cast<std::size_t>(component)] = {
            minimum,
            mean_square / static_cast<double>(values.size()),
            peak,
            -static_cast<double>(component),
        };
    }
    int omitted = 0;
    for (int component = 1; component < 4; ++component) {
        if (scores[static_cast<std::size_t>(component)] >
            scores[static_cast<std::size_t>(omitted)]) {
            omitted = component;
        }
    }
    for (auto& value : values) {
        if (value[static_cast<std::size_t>(omitted)] < 0.0) {
            value = {-value.x, -value.y, -value.z, -value.w};
        }
    }
    return omitted;
}

PyObject* build_component_buffers(
    const std::vector<fivefury_native::Vec4>& values,
    int count
) {
    PyObject* components = PyTuple_New(count);
    if (components == nullptr) {
        return nullptr;
    }
    for (int component = 0; component < count; ++component) {
        PyObject* data = PyBytes_FromStringAndSize(
            nullptr,
            static_cast<Py_ssize_t>(values.size() * sizeof(double))
        );
        if (data == nullptr) {
            Py_DECREF(components);
            return nullptr;
        }
        auto* output = reinterpret_cast<double*>(PyBytes_AsString(data));
        if (output == nullptr) {
            Py_DECREF(data);
            Py_DECREF(components);
            return nullptr;
        }
        for (std::size_t index = 0; index < values.size(); ++index) {
            output[index] = values[index][static_cast<std::size_t>(component)];
        }
        if (PyTuple_SetItem(components, component, data) < 0) {
            Py_DECREF(data);
            Py_DECREF(components);
            return nullptr;
        }
    }
    return components;
}

}  // namespace

PyObject* mod_ycd_track_sampler_new(PyObject*, PyObject* args) {
    PyObject* values_object = nullptr;
    PyObject* frames_object = nullptr;
    PyObject* vector3_type = nullptr;
    PyObject* quaternion_type = nullptr;
    int format_value = 0;
    Py_ssize_t frame_count = 0;
    if (!PyArg_ParseTuple(
            args,
            "OOinOO:ycd_track_sampler_new",
            &values_object,
            &frames_object,
            &format_value,
            &frame_count,
            &vector3_type,
            &quaternion_type
        )) {
        return nullptr;
    }
    if (format_value < 0 || format_value > 2 || frame_count <= 0) {
        PyErr_SetString(PyExc_ValueError, "invalid YCD track sampler dimensions");
        return nullptr;
    }

    auto sampler = std::make_unique<TrackSampler>();
    sampler->format = static_cast<TrackFormat>(format_value);
    sampler->frame_count = static_cast<std::size_t>(frame_count);
    sampler->dense = frames_object == Py_None;
    if (!parse_values(
            values_object,
            sampler->format,
            vector3_type,
            quaternion_type,
            sampler->values
        )) {
        return nullptr;
    }
    if (sampler->values.empty()) {
        PyErr_SetString(PyExc_ValueError, "YCD track samples cannot be empty");
        return nullptr;
    }
    if (sampler->dense) {
        if (sampler->values.size() != sampler->frame_count) {
            PyErr_SetString(
                PyExc_ValueError,
                "per-frame sample count does not match the YCD track duration"
            );
            return nullptr;
        }
        trim_dense_storage(*sampler);
    } else {
        if (!parse_frames(frames_object, sampler->frames)) {
            return nullptr;
        }
        if (sampler->frames.size() != sampler->values.size()) {
            PyErr_SetString(
                PyExc_ValueError,
                "keyframe and sample counts must match"
            );
            return nullptr;
        }
        if (!std::is_sorted(sampler->frames.begin(), sampler->frames.end()) ||
            std::adjacent_find(sampler->frames.begin(), sampler->frames.end()) !=
                sampler->frames.end()) {
            PyErr_SetString(
                PyExc_ValueError,
                "keyframe indices must be strictly increasing"
            );
            return nullptr;
        }
    }
    return PyCapsule_New(sampler.release(), CAPSULE_NAME, destroy_sampler);
}

PyObject* mod_ycd_track_sampler_window(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    Py_ssize_t start = 0;
    Py_ssize_t count = 0;
    int orient_cached = 0;
    if (!PyArg_ParseTuple(
            args,
            "Onnp:ycd_track_sampler_window",
            &capsule,
            &start,
            &count,
            &orient_cached
        )) {
        return nullptr;
    }
    TrackSampler* sampler = require_sampler(capsule);
    if (sampler == nullptr) {
        return nullptr;
    }
    if (start < 0 || count < 0 ||
        static_cast<std::size_t>(start) > sampler->frame_count ||
        static_cast<std::size_t>(count) >
            sampler->frame_count - static_cast<std::size_t>(start)) {
        PyErr_SetString(PyExc_IndexError, "YCD sample window is out of range");
        return nullptr;
    }

    std::vector<fivefury_native::Vec4> values;
    values.reserve(static_cast<std::size_t>(count));
    for (Py_ssize_t offset = 0; offset < count; ++offset) {
        values.push_back(sample_at(
            *sampler,
            static_cast<std::size_t>(start + offset)
        ));
    }
    bool dynamic = false;
    for (std::size_t index = 1; index < values.size(); ++index) {
        if (!equal(values.front(), values[index], sampler->format)) {
            dynamic = true;
            break;
        }
    }
    int omitted = -1;
    if (orient_cached != 0 && dynamic &&
        sampler->format == TrackFormat::Quaternion) {
        omitted = orient_cached_quaternions(values);
    }

    PyObject* components = build_component_buffers(
        values,
        component_count(sampler->format)
    );
    if (components == nullptr) {
        return nullptr;
    }
    PyObject* dynamic_object = PyBool_FromLong(dynamic ? 1 : 0);
    PyObject* omitted_object = PyLong_FromLong(omitted);
    if (dynamic_object == nullptr || omitted_object == nullptr) {
        Py_DECREF(components);
        Py_XDECREF(dynamic_object);
        Py_XDECREF(omitted_object);
        return nullptr;
    }
    PyObject* result = PyTuple_Pack(
        3,
        components,
        dynamic_object,
        omitted_object
    );
    Py_DECREF(components);
    Py_DECREF(dynamic_object);
    Py_DECREF(omitted_object);
    return result;
}

PyObject* mod_ycd_track_sampler_retained_count(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    if (!PyArg_ParseTuple(args, "O:ycd_track_sampler_retained_count", &capsule)) {
        return nullptr;
    }
    TrackSampler* sampler = require_sampler(capsule);
    if (sampler == nullptr) {
        return nullptr;
    }
    return PyLong_FromSize_t(sampler->values.size());
}

}  // namespace fivefury_py
