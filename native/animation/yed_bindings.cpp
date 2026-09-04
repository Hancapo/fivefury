#include "animation/bindings.h"

#include <exception>
#include <memory>
#include <stdexcept>
#include <string>

#include "animation/yed_vm.h"

using namespace fivefury_native;

namespace fivefury_py {
namespace {

class PyHandle {
public:
    explicit PyHandle(PyObject* object = nullptr) : object_(object) {}
    ~PyHandle() { Py_XDECREF(object_); }
    PyHandle(const PyHandle&) = delete;
    PyHandle& operator=(const PyHandle&) = delete;
    PyHandle(PyHandle&& other) noexcept : object_(other.object_) { other.object_ = nullptr; }
    PyObject* get() const { return object_; }
    PyObject* release() { auto* result = object_; object_ = nullptr; return result; }
    explicit operator bool() const { return object_ != nullptr; }

private:
    PyObject* object_;
};

bool tuple_take(PyObject* tuple, Py_ssize_t index, PyObject* value) {
    if (value == nullptr) return false;
    if (PyTuple_SetItem(tuple, index, value) < 0) {
        Py_DECREF(value);
        return false;
    }
    return true;
}

bool list_take(PyObject* list, Py_ssize_t index, PyObject* value) {
    if (value == nullptr) return false;
    if (PyList_SetItem(list, index, value) < 0) {
        Py_DECREF(value);
        return false;
    }
    return true;
}

PyHandle item(PyObject* sequence, Py_ssize_t index) {
    return PyHandle(PySequence_GetItem(sequence, index));
}

std::string as_string(PyObject* object, const char* label) {
    std::string value;
    if (!unicode_to_utf8(object, value, label)) throw std::invalid_argument(label);
    return value;
}

std::int64_t as_i64(PyObject* object, const char* label) {
    const auto value = PyLong_AsLongLong(object);
    if (PyErr_Occurred()) throw std::invalid_argument(label);
    return value;
}

std::uint64_t as_u64_mask(PyObject* object, const char* label) {
    const auto value = PyLong_AsUnsignedLongLongMask(object);
    if (PyErr_Occurred()) throw std::invalid_argument(label);
    return value;
}

double as_double(PyObject* object, const char* label) {
    const auto value = PyFloat_AsDouble(object);
    if (PyErr_Occurred()) throw std::invalid_argument(label);
    return value;
}

bool as_bool(PyObject* object, const char* label) {
    const auto value = PyObject_IsTrue(object);
    if (value < 0) throw std::invalid_argument(label);
    return value != 0;
}

Vec4 as_vec4(PyObject* object, const char* label) {
    if (PySequence_Size(object) < 4) throw std::invalid_argument(label);
    Vec4 value;
    for (Py_ssize_t index = 0; index < 4; ++index) {
        auto component = item(object, index);
        if (!component) throw std::invalid_argument(label);
        value[static_cast<std::size_t>(index)] = as_double(component.get(), label);
    }
    return value;
}

Vec4 as_track_vec4(PyObject* object) {
    const auto size = PySequence_Size(object);
    if (size < 0) {
        PyErr_Clear();
        return {as_double(object, "track value"), 0.0, 0.0, 0.0};
    }
    if (size >= 4) return as_vec4(object, "track value");
    if (size == 3) {
        auto x = item(object, 0);
        auto y = item(object, 1);
        auto z = item(object, 2);
        if (!x || !y || !z) throw std::invalid_argument("track value");
        return {
            as_double(x.get(), "track value"),
            as_double(y.get(), "track value"),
            as_double(z.get(), "track value"),
            0.0,
        };
    }
    if (size == 1) {
        auto value = item(object, 0);
        if (!value) throw std::invalid_argument("track value");
        return {as_double(value.get(), "track value"), 0.0, 0.0, 0.0};
    }
    return {};
}

void parse_track_payload(YedInstructionProgram& instruction, PyObject* payload) {
    if (PySequence_Size(payload) != 5) throw std::invalid_argument("invalid track operand");
    auto bone = item(payload, 0);
    auto track = item(payload, 1);
    auto component = item(payload, 2);
    auto format = item(payload, 3);
    auto defaults = item(payload, 4);
    if (!bone || !track || !component || !format || !defaults) {
        throw std::invalid_argument("invalid track operand");
    }
    instruction.track_key = yed_track_key(
        as_i64(bone.get(), "bone_id"), as_i64(track.get(), "track")
    );
    instruction.component = static_cast<std::uint8_t>(as_i64(component.get(), "component"));
    instruction.format = static_cast<std::uint8_t>(as_i64(format.get(), "format"));
    instruction.use_defaults = as_bool(defaults.get(), "use_defaults");
}

void parse_variable_payload(YedInstructionProgram& instruction, PyObject* payload) {
    if (PySequence_Size(payload) != 2) throw std::invalid_argument("invalid variable operand");
    auto hash = item(payload, 0);
    auto index = item(payload, 1);
    if (!hash || !index) throw std::invalid_argument("invalid variable operand");
    instruction.variable_key = yed_variable_key(
        as_u64_mask(hash.get(), "variable"), as_u64_mask(index.get(), "variable_index")
    );
}

void parse_blend_payload(YedInstructionProgram& instruction, PyObject* payload) {
    const auto source_count = PySequence_Size(payload);
    if (source_count < 0) throw std::invalid_argument("invalid blend operand");
    instruction.blend_sources.reserve(static_cast<std::size_t>(source_count));
    for (Py_ssize_t source_index = 0; source_index < source_count; ++source_index) {
        auto source_object = item(payload, source_index);
        if (!source_object || PySequence_Size(source_object.get()) != 4) {
            throw std::invalid_argument("invalid blend source");
        }
        auto bone = item(source_object.get(), 0);
        auto track = item(source_object.get(), 1);
        auto component = item(source_object.get(), 2);
        auto axes = item(source_object.get(), 3);
        if (!bone || !track || !component || !axes || PySequence_Size(axes.get()) != 3) {
            throw std::invalid_argument("invalid blend source");
        }
        YedBlendSource source;
        source.key = yed_track_key(as_i64(bone.get(), "bone_id"), as_i64(track.get(), "track"));
        source.component = static_cast<std::uint8_t>(as_i64(component.get(), "component"));
        for (Py_ssize_t axis_index = 0; axis_index < 3; ++axis_index) {
            auto axis_object = item(axes.get(), axis_index);
            if (!axis_object || PySequence_Size(axis_object.get()) != 3) {
                throw std::invalid_argument("invalid blend axis");
            }
            auto multiplier = item(axis_object.get(), 0);
            auto additive = item(axis_object.get(), 1);
            auto intervals = item(axis_object.get(), 2);
            if (!multiplier || !additive || !intervals) throw std::invalid_argument("invalid blend axis");
            auto& axis = source.axes[static_cast<std::size_t>(axis_index)];
            axis.multiplier = as_double(multiplier.get(), "blend multiplier");
            axis.additive = as_double(additive.get(), "blend additive");
            const auto interval_count = PySequence_Size(intervals.get());
            if (interval_count < 0) throw std::invalid_argument("invalid blend intervals");
            axis.intervals.reserve(static_cast<std::size_t>(interval_count));
            for (Py_ssize_t interval_index = 0; interval_index < interval_count; ++interval_index) {
                auto interval_object = item(intervals.get(), interval_index);
                if (!interval_object || PySequence_Size(interval_object.get()) != 3) {
                    throw std::invalid_argument("invalid blend interval");
                }
                auto begin = item(interval_object.get(), 0);
                auto interval_multiplier = item(interval_object.get(), 1);
                auto interval_additive = item(interval_object.get(), 2);
                if (!begin || !interval_multiplier || !interval_additive) {
                    throw std::invalid_argument("invalid blend interval");
                }
                axis.intervals.push_back({
                    as_double(begin.get(), "blend begin"),
                    as_double(interval_multiplier.get(), "blend multiplier"),
                    as_double(interval_additive.get(), "blend additive"),
                });
            }
        }
        instruction.blend_sources.push_back(std::move(source));
    }
}

YedInstructionProgram parse_instruction(PyObject* object) {
    if (PySequence_Size(object) != 6) throw std::invalid_argument("invalid YED instruction spec");
    auto opcode = item(object, 0);
    auto index = item(object, 1);
    auto parsed = item(object, 2);
    auto parse_error = item(object, 3);
    auto operand_error = item(object, 4);
    auto payload = item(object, 5);
    if (!opcode || !index || !parsed || !parse_error || !operand_error || !payload) {
        throw std::invalid_argument("invalid YED instruction spec");
    }
    YedInstructionProgram instruction;
    instruction.opcode = static_cast<std::uint8_t>(as_i64(opcode.get(), "opcode"));
    instruction.index = static_cast<std::int32_t>(as_i64(index.get(), "instruction index"));
    instruction.parsed = as_bool(parsed.get(), "parsed");
    instruction.parse_error = as_string(parse_error.get(), "parse_error");
    instruction.operand_error = as_string(operand_error.get(), "operand_error");
    if (!instruction.parsed || !instruction.operand_error.empty() || payload.get() == Py_None) {
        return instruction;
    }
    switch (instruction.opcode) {
        case 0x05:
            {
            const auto scalar = as_double(payload.get(), "float operand");
            instruction.value = {
                scalar, scalar, scalar, scalar,
            };
            break;
            }
        case 0x0B: instruction.value = as_vec4(payload.get(), "vector operand"); break;
        case 0x06: case 0x07: case 0x08: case 0x09: case 0x0A: case 0x20:
        case 0x23: case 0x26: case 0x27: case 0x28: case 0x29: case 0x2A:
            parse_track_payload(instruction, payload.get());
            break;
        case 0x2B: case 0x2C: case 0x2D:
            instruction.jump_offset = static_cast<std::int32_t>(as_i64(payload.get(), "jump offset"));
            break;
        case 0x42: case 0x43: parse_variable_payload(instruction, payload.get()); break;
        case 0x44: case 0x45: parse_blend_payload(instruction, payload.get()); break;
        default: break;
    }
    return instruction;
}

std::unique_ptr<YedProgram> parse_program(PyObject* expressions, PyObject* defaults) {
    auto program = std::make_unique<YedProgram>();
    const auto expression_count = PySequence_Size(expressions);
    if (expression_count < 0) throw std::invalid_argument("expressions must be a sequence");
    for (Py_ssize_t expression_index = 0; expression_index < expression_count; ++expression_index) {
        auto expression = item(expressions, expression_index);
        if (!expression || PySequence_Size(expression.get()) != 2) {
            throw std::invalid_argument("invalid YED expression spec");
        }
        auto expression_name = item(expression.get(), 0);
        auto streams = item(expression.get(), 1);
        if (!expression_name || !streams) throw std::invalid_argument("invalid YED expression spec");
        const auto name = as_string(expression_name.get(), "expression name");
        const auto stream_count = PySequence_Size(streams.get());
        if (stream_count < 0) throw std::invalid_argument("streams must be a sequence");
        for (Py_ssize_t stream_index = 0; stream_index < stream_count; ++stream_index) {
            auto stream_object = item(streams.get(), stream_index);
            if (!stream_object || PySequence_Size(stream_object.get()) != 2) {
                throw std::invalid_argument("invalid YED stream spec");
            }
            auto stream_name = item(stream_object.get(), 0);
            auto instructions = item(stream_object.get(), 1);
            if (!stream_name || !instructions) throw std::invalid_argument("invalid YED stream spec");
            YedStreamProgram stream;
            stream.expression = name;
            stream.name = as_string(stream_name.get(), "stream name");
            const auto instruction_count = PySequence_Size(instructions.get());
            if (instruction_count < 0) throw std::invalid_argument("instructions must be a sequence");
            stream.instructions.reserve(static_cast<std::size_t>(instruction_count));
            for (Py_ssize_t instruction_index = 0; instruction_index < instruction_count; ++instruction_index) {
                auto instruction = item(instructions.get(), instruction_index);
                if (!instruction) throw std::invalid_argument("invalid YED instruction spec");
                stream.instructions.push_back(parse_instruction(instruction.get()));
            }
            program->streams.push_back(std::move(stream));
        }
    }
    const auto bone_count = PySequence_Size(defaults);
    if (bone_count < 0) throw std::invalid_argument("skeleton defaults must be a sequence");
    for (Py_ssize_t bone_index = 0; bone_index < bone_count; ++bone_index) {
        auto bone = item(defaults, bone_index);
        if (!bone || PySequence_Size(bone.get()) != 4) throw std::invalid_argument("invalid bone defaults");
        auto tag = item(bone.get(), 0);
        auto translation = item(bone.get(), 1);
        auto rotation = item(bone.get(), 2);
        auto scale = item(bone.get(), 3);
        if (!tag || !translation || !rotation || !scale) throw std::invalid_argument("invalid bone defaults");
        program->bones[as_i64(tag.get(), "bone tag")] = {
            as_vec4(translation.get(), "bone translation"),
            as_vec4(rotation.get(), "bone rotation"),
            as_vec4(scale.get(), "bone scale"),
        };
    }
    return program;
}

void yed_program_destructor(PyObject* capsule) {
    auto* program = static_cast<YedProgram*>(PyCapsule_GetPointer(capsule, YED_PROGRAM_CAPSULE_NAME));
    if (program == nullptr) {
        PyErr_Clear();
        return;
    }
    delete program;
}

YedProgram* require_yed_program(PyObject* capsule) {
    return static_cast<YedProgram*>(PyCapsule_GetPointer(capsule, YED_PROGRAM_CAPSULE_NAME));
}

void parse_track_mapping(PyObject* mapping, std::unordered_map<YedTrackKey, Vec4>& output) {
    PyHandle pairs(PyMapping_Items(mapping));
    if (!pairs) throw std::invalid_argument("tracks must be a mapping");
    const auto count = PySequence_Size(pairs.get());
    output.reserve(static_cast<std::size_t>(std::max<Py_ssize_t>(count, 0)));
    for (Py_ssize_t index = 0; index < count; ++index) {
        auto pair = item(pairs.get(), index);
        if (!pair || PySequence_Size(pair.get()) != 2) {
            throw std::invalid_argument("invalid track mapping item");
        }
        auto key = item(pair.get(), 0);
        auto value = item(pair.get(), 1);
        if (!key || !value || PySequence_Size(key.get()) != 2) {
            throw std::invalid_argument("invalid track mapping item");
        }
        auto bone = item(key.get(), 0);
        auto track = item(key.get(), 1);
        if (!bone || !track) throw std::invalid_argument("invalid track key");
        output[yed_track_key(as_i64(bone.get(), "bone_id"), as_i64(track.get(), "track"))] =
            as_track_vec4(value.get());
    }
}

void parse_variable_mapping(PyObject* mapping, std::unordered_map<YedVariableKey, Vec4>& output) {
    PyHandle pairs(PyMapping_Items(mapping));
    if (!pairs) throw std::invalid_argument("variables must be a mapping");
    const auto count = PySequence_Size(pairs.get());
    output.reserve(static_cast<std::size_t>(std::max<Py_ssize_t>(count, 0)));
    for (Py_ssize_t index = 0; index < count; ++index) {
        auto pair = item(pairs.get(), index);
        if (!pair || PySequence_Size(pair.get()) != 2) {
            throw std::invalid_argument("invalid variable mapping item");
        }
        auto key = item(pair.get(), 0);
        auto value = item(pair.get(), 1);
        if (!key || !value || PySequence_Size(key.get()) != 2) {
            throw std::invalid_argument("invalid variable mapping item");
        }
        auto hash = item(key.get(), 0);
        auto variable_index = item(key.get(), 1);
        if (!hash || !variable_index) throw std::invalid_argument("invalid variable key");
        output[yed_variable_key(as_u64_mask(hash.get(), "variable"), as_u64_mask(variable_index.get(), "variable_index"))] =
            as_vec4(value.get(), "variable value");
    }
}

PyObject* make_vec4(const Vec4& value) {
    PyObject* result = PyTuple_New(4);
    if (result == nullptr) return nullptr;
    for (Py_ssize_t index = 0; index < 4; ++index) {
        PyObject* component = PyFloat_FromDouble(value[static_cast<std::size_t>(index)]);
        if (!tuple_take(result, index, component)) {
            Py_DECREF(result);
            return nullptr;
        }
    }
    return result;
}

PyObject* make_pair_key(std::uint32_t left, std::uint32_t right) {
    PyObject* key = PyTuple_New(2);
    if (key == nullptr) return nullptr;
    PyObject* left_object = PyLong_FromUnsignedLong(left);
    PyObject* right_object = PyLong_FromUnsignedLong(right);
    if (!tuple_take(key, 0, left_object) || !tuple_take(key, 1, right_object)) {
        Py_DECREF(key);
        return nullptr;
    }
    return key;
}

template <typename Map>
PyObject* make_mapping(const Map& values) {
    PyObject* result = PyDict_New();
    if (result == nullptr) return nullptr;
    for (const auto& [packed, vector] : values) {
        PyHandle key(make_pair_key(static_cast<std::uint32_t>(packed >> 32U), static_cast<std::uint32_t>(packed)));
        PyHandle value(make_vec4(vector));
        if (!key || !value || PyDict_SetItem(result, key.get(), value.get()) < 0) {
            Py_DECREF(result);
            return nullptr;
        }
    }
    return result;
}

PyObject* make_issues(const std::vector<YedIssueData>& issues) {
    PyObject* result = PyList_New(static_cast<Py_ssize_t>(issues.size()));
    if (result == nullptr) return nullptr;
    for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(issues.size()); ++index) {
        const auto& issue = issues[static_cast<std::size_t>(index)];
        PyObject* value = PyTuple_New(5);
        if (value == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        PyObject* instruction = nullptr;
        if (issue.instruction < 0) {
            instruction = Py_None;
            Py_INCREF(instruction);
        } else {
            instruction = PyLong_FromLong(issue.instruction);
        }
        if (!tuple_take(value, 0, PyUnicode_FromStringAndSize(issue.code.data(), static_cast<Py_ssize_t>(issue.code.size()))) ||
            !tuple_take(value, 1, PyUnicode_FromStringAndSize(issue.message.data(), static_cast<Py_ssize_t>(issue.message.size()))) ||
            !tuple_take(value, 2, PyUnicode_FromStringAndSize(issue.expression.data(), static_cast<Py_ssize_t>(issue.expression.size()))) ||
            !tuple_take(value, 3, PyUnicode_FromStringAndSize(issue.stream.data(), static_cast<Py_ssize_t>(issue.stream.size())))) {
            Py_XDECREF(instruction);
            Py_DECREF(value);
            Py_DECREF(result);
            return nullptr;
        }
        if (!tuple_take(value, 4, instruction)) {
            Py_DECREF(value);
            Py_DECREF(result);
            return nullptr;
        }
        if (!list_take(result, index, value)) {
            Py_DECREF(result);
            return nullptr;
        }
    }
    return result;
}

}

PyObject* mod_yed_compile(PyObject*, PyObject* args) {
    PyObject* expressions = nullptr;
    PyObject* defaults = nullptr;
    if (!PyArg_ParseTuple(args, "OO", &expressions, &defaults)) return nullptr;
    try {
        auto program = parse_program(expressions, defaults);
        return PyCapsule_New(program.release(), YED_PROGRAM_CAPSULE_NAME, yed_program_destructor);
    } catch (...) {
        return translate_cpp_exception();
    }
}

PyObject* mod_yed_evaluate(PyObject*, PyObject* args) {
    PyObject* capsule = nullptr;
    PyObject* tracks = nullptr;
    PyObject* variables = nullptr;
    double time = 0.0;
    double delta_time = 0.0;
    if (!PyArg_ParseTuple(args, "OOOdd", &capsule, &tracks, &variables, &time, &delta_time)) return nullptr;
    auto* program = require_yed_program(capsule);
    if (program == nullptr) return nullptr;
    try {
        YedFrameData frame;
        parse_track_mapping(tracks, frame.tracks);
        parse_variable_mapping(variables, frame.variables);
        std::exception_ptr execution_error;
        PyThreadState* thread_state = PyEval_SaveThread();
        try {
            evaluate_yed_program(*program, frame, time, delta_time);
        } catch (...) {
            execution_error = std::current_exception();
        }
        PyEval_RestoreThread(thread_state);
        if (execution_error) std::rethrow_exception(execution_error);

        PyHandle result_tracks(make_mapping(frame.tracks));
        PyHandle result_outputs(make_mapping(frame.outputs));
        PyHandle result_variables(make_mapping(frame.variables));
        PyHandle result_issues(make_issues(frame.issues));
        if (!result_tracks || !result_outputs || !result_variables || !result_issues) return nullptr;
        PyObject* result = PyTuple_New(4);
        if (result == nullptr) return nullptr;
        if (!tuple_take(result, 0, result_tracks.release()) ||
            !tuple_take(result, 1, result_outputs.release()) ||
            !tuple_take(result, 2, result_variables.release()) ||
            !tuple_take(result, 3, result_issues.release())) {
            Py_DECREF(result);
            return nullptr;
        }
        return result;
    } catch (...) {
        return translate_cpp_exception();
    }
}

}
