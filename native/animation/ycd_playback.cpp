#include "animation/bindings.h"
#include "math/vector.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <limits>
#include <memory>
#include <vector>

namespace fivefury_py {
namespace {
using namespace fivefury_native;
constexpr const char* name = "fivefury.YcdPlayback";

struct Lane { std::size_t offset = 0, count = 0; };
struct Track {
    bool present = false;
    int layout = -1;
    std::array<Lane, 4> lanes{};
};
struct Block { std::vector<Track> tracks, cached; };
struct Plan {
    Plan(PyObject* k, PyObject* v, PyObject* q)
        : keys(Py_NewRef(k)), vector_type(Py_NewRef(v)), quaternion_type(Py_NewRef(q)) {}
    PyHandle keys, vector_type, quaternion_type;
    std::vector<int> track_ids;
    std::vector<bool> rotations;
    std::vector<double> values;
    std::vector<Block> blocks;
};

void destroy(PyObject* capsule) {
    delete static_cast<Plan*>(PyCapsule_GetPointer(capsule, name));
}

Vec4 packed(const Plan& plan, const Track& track, std::size_t frame) {
    Vec4 result;
    for (std::size_t i = 0; i < 4; ++i) {
        const auto lane = track.lanes[i];
        if (lane.count) result[i] = plan.values[lane.offset + frame % lane.count];
    }
    return result;
}

Vec4 reconstruct(const Vec4& value, int layout) {
    if (layout >= 0) return quat_reconstruct(value, static_cast<std::size_t>(layout));
    return layout == -2 ? quat_normalize(value) : value;
}

struct Sample { std::size_t key; Vec4 value; };

std::vector<Sample> evaluate(const Plan& plan, double frame, bool integer, std::size_t frames,
                             std::size_t limit, bool filtered, int track_id) {
    std::vector<Sample> result;
    if (plan.blocks.empty()) return result;
    frame = std::max(frame, 0.0);
    auto first = static_cast<std::size_t>(frame);
    if (!integer && frames) first = std::min(first, frames - 1);
    auto second = first;
    double alpha = 0.0;
    if (!integer) {
        second = first + 1;
        if (frames) second = std::min(second, frames - 1);
        alpha = frame - static_cast<double>(first);
    }
    const bool blend = first != second && alpha > 0.0;
    const auto& left = plan.blocks[std::min(first / limit, plan.blocks.size() - 1)];
    const auto& right = plan.blocks[std::min(second / limit, plan.blocks.size() - 1)];
    result.reserve(plan.track_ids.size());
    for (std::size_t key = 0; key < plan.track_ids.size(); ++key) {
        if (filtered && plan.track_ids[key] != track_id) continue;
        const auto& a = left.tracks[key];
        const auto& b = right.tracks[key];
        if (!a.present && !(blend && b.present)) continue;
        Vec4 start = a.present ? reconstruct(packed(plan, a, first % limit), a.layout)
                               : reconstruct(packed(plan, b, second % limit), b.layout);
        Vec4 value = start;
        if (blend) {
            const auto& cached = left.cached[key];
            if (cached.present) {
                const auto local = first % limit;
                value = reconstruct(vec4_lerp(packed(plan, cached, local),
                                             packed(plan, cached, local + 1), alpha), cached.layout);
            } else {
                const Vec4 end = b.present ? reconstruct(packed(plan, b, second % limit), b.layout) : start;
                value = plan.rotations[key] ? quat_nlerp(start, end, alpha) : vec4_lerp(start, end, alpha);
            }
        }
        result.push_back({key, value});
    }
    return result;
}

PyObject* typed_result(const Plan& plan, const std::vector<Sample>& values) {
    PyHandle result(PyDict_New());
    if (!result) return nullptr;
    for (const auto& sample : values) {
        const auto& v = sample.value;
        PyHandle value(PyObject_CallFunction(
            plan.rotations[sample.key] ? plan.quaternion_type.get() : plan.vector_type.get(),
            "dddd", v.x, v.y, v.z, v.w));
        if (!value || PyDict_SetItem(result.get(), PyTuple_GetItem(plan.keys.get(), sample.key), value.get()) < 0) return nullptr;
    }
    return result.release();
}
}

PyObject* mod_ycd_playback_compile(PyObject*, PyObject* args) {
    PyObject *blocks, *keys, *rotations, *vector_type, *quaternion_type;
    if (!PyArg_ParseTuple(args, "OOOOO:ycd_playback_compile", &blocks, &keys, &rotations,
                         &vector_type, &quaternion_type)) return nullptr;
    const auto count = PyTuple_Size(keys);
    const auto block_count = PyTuple_Size(blocks);
    if (count < 0 || block_count < 0) return nullptr;
    if (PyTuple_Size(rotations) != count || !PyCallable_Check(vector_type) || !PyCallable_Check(quaternion_type)) {
        PyErr_SetString(PyExc_ValueError, "Invalid YCD playback key or type layout"); return nullptr;
    }
    auto plan = std::make_unique<Plan>(keys, vector_type, quaternion_type);
    for (Py_ssize_t key = 0; key < count; ++key) {
        PyObject* pair = PyTuple_GetItem(keys, key);
        if (PyTuple_Size(pair) != 2) { PyErr_SetString(PyExc_ValueError, "Invalid YCD track key"); return nullptr; }
        const long id = PyLong_AsLong(PyTuple_GetItem(pair, 1));
        const int rotation = PyObject_IsTrue(PyTuple_GetItem(rotations, key));
        if (PyErr_Occurred() || rotation < 0) return nullptr;
        if (id < std::numeric_limits<int>::min() || id > std::numeric_limits<int>::max()) {
            PyErr_SetString(PyExc_OverflowError, "YCD track ID is out of range"); return nullptr;
        }
        plan->track_ids.push_back(static_cast<int>(id));
        plan->rotations.push_back(rotation != 0);
    }
    for (Py_ssize_t bi = 0; bi < block_count; ++bi) {
        Block block;
        block.tracks.resize(count); block.cached.resize(count);
        PyObject* entries = PyTuple_GetItem(blocks, bi);
        const auto size = PyTuple_Size(entries);
        if (size < 0) return nullptr;
        for (Py_ssize_t i = 0; i < size; ++i) {
            Py_ssize_t key; int layout; PyObject* lanes;
            if (!PyArg_ParseTuple(PyTuple_GetItem(entries, i), "niO", &key, &layout, &lanes)) return nullptr;
            const auto width = PyTuple_Size(lanes);
            if (key < 0 || key >= count || layout < -2 || layout > 3 || width < 0 || width > 4) {
                PyErr_SetString(PyExc_ValueError, "Invalid YCD playback sequence"); return nullptr;
            }
            Track track; track.present = true; track.layout = layout;
            for (Py_ssize_t lane = 0; lane < width; ++lane) {
                Buffer data;
                if (!data.acquire(PyTuple_GetItem(lanes, lane), PyBUF_FORMAT | PyBUF_C_CONTIGUOUS)) return nullptr;
                if (!data.len || data.len % sizeof(double) || data.itemsize != sizeof(double) ||
                    data.ndim != 1 || !data.format || std::strcmp(data.format, "d") != 0) {
                    PyErr_SetString(PyExc_ValueError, "YCD component buffer requires float64 samples"); return nullptr;
                }
                const auto offset = plan->values.size();
                const auto samples = static_cast<std::size_t>(data.len) / sizeof(double);
                plan->values.resize(offset + samples);
                std::memcpy(plan->values.data() + offset, data.buf, data.len);
                track.lanes[lane] = {offset, samples};
            }
            block.tracks[key] = track;
            if (layout != -1) block.cached[key] = track;
        }
        plan->blocks.push_back(std::move(block));
    }
    return owned_capsule(std::move(plan), name, destroy);
}

PyObject* mod_ycd_playback_evaluate(PyObject*, PyObject* args) {
    PyObject *capsule, *filter; double frame; int integer; Py_ssize_t frames, limit;
    if (!PyArg_ParseTuple(args, "OdpnnO:ycd_playback_evaluate", &capsule, &frame, &integer, &frames, &limit, &filter)) return nullptr;
    auto* plan = static_cast<Plan*>(PyCapsule_GetPointer(capsule, name));
    if (!plan) return nullptr;
    if (!std::isfinite(frame) || frame >= static_cast<double>(PY_SSIZE_T_MAX - 1) || limit <= 0) {
        PyErr_SetString(PyExc_ValueError, "Invalid YCD sampling frame or sequence limit"); return nullptr;
    }
    const long track = filter == Py_None ? 0 : PyLong_AsLong(filter);
    if (PyErr_Occurred()) return nullptr;
    std::vector<Sample> values;
    {
        GilRelease released;
        values = evaluate(*plan, frame, integer != 0, std::max<Py_ssize_t>(frames, 0), limit,
                          filter != Py_None, static_cast<int>(track));
    }
    return typed_result(*plan, values);
}
}
