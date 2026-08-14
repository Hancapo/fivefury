#include "yed_vm.h"

#include <algorithm>
#include <cstdio>
#include <cmath>
#include <stdexcept>

namespace fivefury_native {
namespace {

constexpr std::uint8_t OP_END = 0x00;
constexpr std::uint8_t OP_POP = 0x01;
constexpr std::uint8_t OP_DUP = 0x02;
constexpr std::uint8_t OP_PUSH0 = 0x03;
constexpr std::uint8_t OP_PUSH1 = 0x04;
constexpr std::uint8_t OP_PUSH_FLOAT = 0x05;
constexpr std::uint8_t OP_TRACK_GET = 0x06;
constexpr std::uint8_t OP_TRACK_GET_COMP = 0x07;
constexpr std::uint8_t OP_TRACK_GET_OFFSET = 0x08;
constexpr std::uint8_t OP_TRACK_GET_OFFSET_COMP = 0x09;
constexpr std::uint8_t OP_TRACK_GET_BONE_TRANSFORM = 0x0A;
constexpr std::uint8_t OP_PUSH_VECTOR = 0x0B;
constexpr std::uint8_t OP_DEFINE_SPRING = 0x0E;
constexpr std::uint8_t OP_VECTOR_ABS = 0x0F;
constexpr std::uint8_t OP_VECTOR_NEG = 0x10;
constexpr std::uint8_t OP_VECTOR_RCP = 0x11;
constexpr std::uint8_t OP_VECTOR_SQRT = 0x12;
constexpr std::uint8_t OP_VECTOR_NEG3 = 0x1B;
constexpr std::uint8_t OP_VECTOR_SQUARE = 0x1C;
constexpr std::uint8_t OP_VECTOR_DEG2RAD = 0x1D;
constexpr std::uint8_t OP_VECTOR_RAD2DEG = 0x1E;
constexpr std::uint8_t OP_VECTOR_SATURATE = 0x1F;
constexpr std::uint8_t OP_TRACK_VALID = 0x20;
constexpr std::uint8_t OP_FROM_EULER = 0x21;
constexpr std::uint8_t OP_TO_EULER = 0x22;
constexpr std::uint8_t OP_UNKNOWN_23 = 0x23;
constexpr std::uint8_t OP_TRACK_SET = 0x26;
constexpr std::uint8_t OP_TRACK_SET_COMP = 0x27;
constexpr std::uint8_t OP_TRACK_SET_OFFSET = 0x28;
constexpr std::uint8_t OP_TRACK_SET_OFFSET_COMP = 0x29;
constexpr std::uint8_t OP_TRACK_SET_BONE_TRANSFORM = 0x2A;
constexpr std::uint8_t OP_JUMP = 0x2B;
constexpr std::uint8_t OP_JUMP_IF_FALSE = 0x2C;
constexpr std::uint8_t OP_JUMP_IF_TRUE = 0x2D;
constexpr std::uint8_t OP_VECTOR_ADD = 0x2E;
constexpr std::uint8_t OP_VECTOR_SUB = 0x2F;
constexpr std::uint8_t OP_VECTOR_MUL = 0x30;
constexpr std::uint8_t OP_VECTOR_MIN = 0x31;
constexpr std::uint8_t OP_VECTOR_MAX = 0x32;
constexpr std::uint8_t OP_QUAT_MUL = 0x33;
constexpr std::uint8_t OP_VECTOR_GREATER_THAN = 0x35;
constexpr std::uint8_t OP_VECTOR_LESS_THAN = 0x36;
constexpr std::uint8_t OP_VECTOR_GREATER_EQUAL = 0x37;
constexpr std::uint8_t OP_VECTOR_LESS_EQUAL = 0x38;
constexpr std::uint8_t OP_VECTOR_CLAMP = 0x39;
constexpr std::uint8_t OP_VECTOR_LERP = 0x3A;
constexpr std::uint8_t OP_VECTOR_MAD = 0x3B;
constexpr std::uint8_t OP_QUAT_SLERP = 0x3C;
constexpr std::uint8_t OP_TO_VECTOR = 0x3D;
constexpr std::uint8_t OP_LOOK_AT = 0x3E;
constexpr std::uint8_t OP_PUSH_TIME = 0x3F;
constexpr std::uint8_t OP_VECTOR_TRANSFORM = 0x40;
constexpr std::uint8_t OP_GET_VARIABLE = 0x42;
constexpr std::uint8_t OP_SET_VARIABLE = 0x43;
constexpr std::uint8_t OP_BLEND_VECTOR = 0x44;
constexpr std::uint8_t OP_BLEND_QUATERNION = 0x45;
constexpr std::uint8_t OP_PUSH_DELTA_TIME = 0x46;
constexpr std::uint8_t OP_VECTOR_EQUAL = 0x48;
constexpr std::uint8_t OP_VECTOR_NOT_EQUAL = 0x49;

class Frame {
public:
    Frame(const YedProgram& program, YedFrameData& data) : program_(program), data_(data) {}

    Vec4 default_value(YedTrackKey key) const {
        const auto bone = static_cast<std::int64_t>(key >> 32U);
        const auto track = static_cast<std::uint32_t>(key);
        const auto found = program_.bones.find(bone);
        if (found != program_.bones.end()) {
            if (track == 0U) return found->second.translation;
            if (track == 1U) return found->second.rotation;
            if (track == 2U) return found->second.scale;
        }
        if (track == 37U || track == 38U) return {1.0, 1.0, 1.0, 0.0};
        return {0.0, 0.0, 0.0, 1.0};
    }

    Vec4 get(YedTrackKey key, bool force_default = false) const {
        if (!force_default) {
            const auto found = data_.tracks.find(key);
            if (found != data_.tracks.end()) return found->second;
        }
        return default_value(key);
    }

    double get_component(
        YedTrackKey key,
        std::uint8_t component,
        std::uint8_t format,
        bool force_default = false
    ) const {
        component = std::min<std::uint8_t>(component, 3U);
        if (!force_default) {
            const auto found = data_.tracks.find(key);
            if (found != data_.tracks.end()) {
                const auto value = format == 1U ? quat_to_euler_xyz(found->second) : found->second;
                return value[component];
            }
        }
        const auto bone = static_cast<std::int64_t>(key >> 32U);
        const auto track = static_cast<std::uint32_t>(key);
        const auto found = program_.bones.find(bone);
        if (found == program_.bones.end() || track > 2U) return 0.0;
        const auto value = track == 1U
            ? quat_to_euler_xyz(found->second.rotation)
            : default_value(key);
        return value[component];
    }

    Vec4 relative(YedTrackKey key, bool force_default = false) const {
        const auto current = data_.tracks.find(key);
        if (force_default || current == data_.tracks.end()) return {0.0, 0.0, 0.0, 1.0};
        const auto bone = static_cast<std::int64_t>(key >> 32U);
        const auto track = static_cast<std::uint32_t>(key);
        if (program_.bones.find(bone) == program_.bones.end()) return {0.0, 0.0, 0.0, 1.0};
        const auto base = default_value(key);
        if (track == 1U) return quat_multiply(quat_inverse(base), current->second);
        if (track == 0U || track == 2U) return vec4_sub(current->second, base);
        return {0.0, 0.0, 0.0, 1.0};
    }

    void set(YedTrackKey key, const Vec4& value) {
        data_.tracks[key] = value;
        data_.outputs[key] = value;
    }

    void set_relative(YedTrackKey key, Vec4 value) {
        const auto bone = static_cast<std::int64_t>(key >> 32U);
        const auto track = static_cast<std::uint32_t>(key);
        if (program_.bones.find(bone) != program_.bones.end()) {
            const auto base = default_value(key);
            if (track == 1U) value = quat_multiply(base, value);
            else if (track == 0U || track == 2U) value = vec4_add(base, value);
        }
        set(key, value);
    }

    void set_component(YedTrackKey key, std::uint8_t component, std::uint8_t format, double scalar) {
        auto current = get(key);
        component = std::min<std::uint8_t>(component, 3U);
        if (format == 1U) {
            auto euler = quat_to_euler_xyz(current);
            euler[component] = scalar;
            set(key, quat_from_euler_xyz(euler));
            return;
        }
        current[component] = scalar;
        set(key, current);
    }

    void set_relative_component(
        YedTrackKey key,
        std::uint8_t component,
        std::uint8_t format,
        double scalar
    ) {
        const auto bone = static_cast<std::int64_t>(key >> 32U);
        const auto track = static_cast<std::uint32_t>(key);
        if (program_.bones.find(bone) == program_.bones.end() || track > 2U) return;
        component = std::min<std::uint8_t>(component, 3U);
        const auto base = default_value(key);
        if (track == 1U || format == 1U) {
            auto relative_euler = quat_to_euler_xyz(quat_multiply(quat_inverse(base), get(key)));
            const auto base_euler = quat_to_euler_xyz(base);
            relative_euler[component] = scalar + base_euler[component];
            set(key, quat_multiply(base, quat_from_euler_xyz(relative_euler)));
            return;
        }
        auto current = get(key);
        current[component] = scalar + base[component];
        set(key, current);
    }

private:
    const YedProgram& program_;
    YedFrameData& data_;
};

Vec4 pop(std::vector<Vec4>& stack) {
    if (stack.empty()) throw std::runtime_error("stack underflow");
    const auto value = stack.back();
    stack.pop_back();
    return value;
}

Vec4& top(std::vector<Vec4>& stack) {
    if (stack.empty()) throw std::runtime_error("stack underflow");
    return stack.back();
}

bool all_zero(const Vec4& value) {
    return value.x == 0.0 && value.y == 0.0 && value.z == 0.0 && value.w == 0.0;
}

Vec4 blend(const YedInstructionProgram& instruction, const Frame& frame, bool quaternion) {
    auto result = quaternion ? Vec4{0.0, 0.0, 0.0, 1.0} : Vec4{};
    for (const auto& source : instruction.blend_sources) {
        const auto input = frame.get(source.key)[source.component];
        Vec4 partial;
        for (std::size_t axis = 0; axis < 3U; ++axis) {
            const auto& curve = source.axes[axis];
            auto value = curve.additive + curve.multiplier * input;
            for (const auto& interval : curve.intervals) {
                if (input > interval.begin) {
                    value = interval.additive + interval.multiplier * input;
                }
            }
            partial[axis] = value;
        }
        if (quaternion) {
            result = quat_multiply_raw(result, quat_from_euler_xyz_raw(partial));
        } else {
            result.x += partial.x;
            result.y += partial.y;
            result.z += partial.z;
        }
    }
    return quaternion ? quat_normalize(result) : result;
}

const char* opcode_name(std::uint8_t opcode) {
    switch (opcode) {
        case OP_POP: return "POP";
        case OP_DUP: return "DUP";
        case OP_PUSH_FLOAT: return "PUSH_FLOAT";
        case OP_TRACK_GET: return "TRACK_GET";
        case OP_TRACK_GET_COMP: return "TRACK_GET_COMP";
        case OP_TRACK_GET_OFFSET: return "TRACK_GET_OFFSET";
        case OP_TRACK_GET_OFFSET_COMP: return "TRACK_GET_OFFSET_COMP";
        case OP_TRACK_SET: return "TRACK_SET";
        case OP_TRACK_SET_COMP: return "TRACK_SET_COMP";
        case OP_TRACK_SET_OFFSET: return "TRACK_SET_OFFSET";
        case OP_TRACK_SET_OFFSET_COMP: return "TRACK_SET_OFFSET_COMP";
        case OP_VECTOR_CLAMP: return "VECTOR_CLAMP";
        case OP_VECTOR_LERP: return "VECTOR_LERP";
        case OP_VECTOR_MAD: return "VECTOR_MAD";
        case OP_TO_VECTOR: return "TO_VECTOR";
        default: return "YED_INSTRUCTION";
    }
}

bool known_unsupported(std::uint8_t opcode) {
    return opcode == OP_TRACK_GET_BONE_TRANSFORM || opcode == OP_UNKNOWN_23 ||
           opcode == OP_TRACK_SET_BONE_TRANSFORM || opcode == OP_LOOK_AT;
}

void append_issue(
    YedFrameData& frame,
    const YedStreamProgram& stream,
    const YedInstructionProgram& instruction,
    std::string code,
    std::string message
) {
    frame.issues.push_back({
        std::move(code), std::move(message), stream.expression, stream.name, instruction.index
    });
}

void run_stream(
    const YedStreamProgram& stream,
    Frame& frame,
    YedFrameData& data,
    double time,
    double delta_time
) {
    std::vector<Vec4> stack;
    stack.reserve(32U);
    std::int64_t pc = 0;
    std::size_t steps = 0;
    const auto max_steps = std::max<std::size_t>(1024U, stream.instructions.size() * 8U);
    while (pc >= 0 && static_cast<std::size_t>(pc) < stream.instructions.size() && steps < max_steps) {
        const auto& instruction = stream.instructions[static_cast<std::size_t>(pc)];
        ++steps;
        if (!instruction.parsed) {
            append_issue(data, stream, instruction, "yed.vm.unparsed_instruction", instruction.parse_error);
            break;
        }
        if (!instruction.operand_error.empty()) {
            append_issue(
                data,
                stream,
                instruction,
                "yed.vm.execution_error",
                std::string(opcode_name(instruction.opcode)) + ": " + instruction.operand_error
            );
            break;
        }
        auto next_pc = pc + 1;
        try {
            switch (instruction.opcode) {
                case OP_END: return;
                case OP_POP: pop(stack); break;
                case OP_DUP: stack.push_back(top(stack)); break;
                case OP_PUSH0: stack.push_back({}); break;
                case OP_PUSH1: stack.push_back({1.0, 1.0, 1.0, 1.0}); break;
                case OP_PUSH_FLOAT:
                case OP_PUSH_VECTOR: stack.push_back(instruction.value); break;
                case OP_TRACK_GET: stack.push_back(frame.get(instruction.track_key, instruction.use_defaults)); break;
                case OP_TRACK_GET_COMP: {
                    const auto scalar = frame.get_component(
                        instruction.track_key,
                        instruction.component,
                        instruction.format,
                        instruction.use_defaults
                    );
                    stack.push_back({scalar, scalar, scalar, scalar});
                    break;
                }
                case OP_TRACK_GET_OFFSET: stack.push_back(frame.relative(instruction.track_key, instruction.use_defaults)); break;
                case OP_TRACK_GET_OFFSET_COMP: {
                    auto value = frame.relative(instruction.track_key, instruction.use_defaults);
                    if (instruction.format == 1U) value = quat_to_euler_xyz(value);
                    const auto scalar = value[std::min<std::uint8_t>(instruction.component, 3U)];
                    stack.push_back({scalar, scalar, scalar, scalar});
                    break;
                }
                case OP_TRACK_VALID: {
                    const auto valid = data.tracks.find(instruction.track_key) != data.tracks.end() ? 1.0 : 0.0;
                    stack.push_back({valid, valid, valid, valid});
                    break;
                }
                case OP_TRACK_SET: frame.set(instruction.track_key, pop(stack)); break;
                case OP_TRACK_SET_COMP: {
                    const auto value = pop(stack);
                    frame.set_component(instruction.track_key, instruction.component, instruction.format, value.x);
                    break;
                }
                case OP_TRACK_SET_OFFSET: frame.set_relative(instruction.track_key, pop(stack)); break;
                case OP_TRACK_SET_OFFSET_COMP: {
                    const auto value = pop(stack);
                    frame.set_relative_component(instruction.track_key, instruction.component, instruction.format, value.x);
                    break;
                }
                case OP_DEFINE_SPRING: break;
                case OP_VECTOR_ABS: {
                    auto& value = top(stack);
                    value = {std::abs(value.x), std::abs(value.y), std::abs(value.z), std::abs(value.w)};
                    break;
                }
                case OP_VECTOR_NEG: {
                    auto& value = top(stack);
                    value = {-value.x, -value.y, -value.z, -value.w};
                    break;
                }
                case OP_VECTOR_RCP: {
                    auto& value = top(stack);
                    value = {
                        value.x == 0.0 ? 0.0 : 1.0 / value.x,
                        value.y == 0.0 ? 0.0 : 1.0 / value.y,
                        value.z == 0.0 ? 0.0 : 1.0 / value.z,
                        value.w == 0.0 ? 0.0 : 1.0 / value.w,
                    };
                    break;
                }
                case OP_VECTOR_SQRT: {
                    auto& value = top(stack);
                    value = {
                        std::sqrt(std::max(0.0, value.x)), std::sqrt(std::max(0.0, value.y)),
                        std::sqrt(std::max(0.0, value.z)), std::sqrt(std::max(0.0, value.w)),
                    };
                    break;
                }
                case OP_VECTOR_NEG3: {
                    auto& value = top(stack);
                    value = {-value.x, -value.y, -value.z, value.w};
                    break;
                }
                case OP_VECTOR_SQUARE: {
                    auto& value = top(stack);
                    value = {value.x * value.x, value.y * value.y, value.z * value.z, value.w * value.w};
                    break;
                }
                case OP_VECTOR_DEG2RAD: {
                    auto& value = top(stack);
                    constexpr auto factor = 3.14159265358979323846 / 180.0;
                    value = {value.x * factor, value.y * factor, value.z * factor, value.w * factor};
                    break;
                }
                case OP_VECTOR_RAD2DEG: {
                    auto& value = top(stack);
                    constexpr auto factor = 180.0 / 3.14159265358979323846;
                    value = {value.x * factor, value.y * factor, value.z * factor, value.w * factor};
                    break;
                }
                case OP_VECTOR_SATURATE: {
                    auto& value = top(stack);
                    value = {
                        std::clamp(value.x, 0.0, 1.0), std::clamp(value.y, 0.0, 1.0),
                        std::clamp(value.z, 0.0, 1.0), std::clamp(value.w, 0.0, 1.0),
                    };
                    break;
                }
                case OP_FROM_EULER: top(stack) = quat_from_euler_xyz(top(stack)); break;
                case OP_TO_EULER: top(stack) = quat_to_euler_xyz(top(stack)); break;
                case OP_VECTOR_ADD:
                case OP_VECTOR_SUB:
                case OP_VECTOR_MUL:
                case OP_VECTOR_MIN:
                case OP_VECTOR_MAX:
                case OP_VECTOR_GREATER_THAN:
                case OP_VECTOR_LESS_THAN:
                case OP_VECTOR_GREATER_EQUAL:
                case OP_VECTOR_LESS_EQUAL:
                case OP_VECTOR_EQUAL:
                case OP_VECTOR_NOT_EQUAL: {
                    const auto right = pop(stack);
                    const auto left = pop(stack);
                    Vec4 result;
                    for (std::size_t index = 0; index < 4U; ++index) {
                        switch (instruction.opcode) {
                            case OP_VECTOR_ADD: result[index] = left[index] + right[index]; break;
                            case OP_VECTOR_SUB: result[index] = left[index] - right[index]; break;
                            case OP_VECTOR_MUL: result[index] = left[index] * right[index]; break;
                            case OP_VECTOR_MIN: result[index] = std::min(left[index], right[index]); break;
                            case OP_VECTOR_MAX: result[index] = std::max(left[index], right[index]); break;
                            case OP_VECTOR_GREATER_THAN: result[index] = left[index] > right[index] ? 1.0 : 0.0; break;
                            case OP_VECTOR_LESS_THAN: result[index] = left[index] < right[index] ? 1.0 : 0.0; break;
                            case OP_VECTOR_GREATER_EQUAL: result[index] = left[index] >= right[index] ? 1.0 : 0.0; break;
                            case OP_VECTOR_LESS_EQUAL: result[index] = left[index] <= right[index] ? 1.0 : 0.0; break;
                            case OP_VECTOR_EQUAL: result[index] = left[index] == right[index] ? 1.0 : 0.0; break;
                            default: result[index] = left[index] != right[index] ? 1.0 : 0.0; break;
                        }
                    }
                    stack.push_back(result);
                    break;
                }
                case OP_QUAT_MUL: {
                    const auto right = pop(stack);
                    const auto left = pop(stack);
                    stack.push_back(quat_multiply(left, right));
                    break;
                }
                case OP_VECTOR_CLAMP: {
                    const auto maximum = pop(stack);
                    const auto minimum = pop(stack);
                    const auto value = pop(stack);
                    stack.push_back({
                        std::max(minimum.x, std::min(maximum.x, value.x)),
                        std::max(minimum.y, std::min(maximum.y, value.y)),
                        std::max(minimum.z, std::min(maximum.z, value.z)),
                        std::max(minimum.w, std::min(maximum.w, value.w)),
                    });
                    break;
                }
                case OP_VECTOR_LERP: {
                    const auto amount = pop(stack);
                    const auto end = pop(stack);
                    const auto start = pop(stack);
                    stack.push_back({
                        start.x + (end.x - start.x) * amount.x,
                        start.y + (end.y - start.y) * amount.y,
                        start.z + (end.z - start.z) * amount.z,
                        start.w + (end.w - start.w) * amount.w,
                    });
                    break;
                }
                case OP_VECTOR_MAD: {
                    const auto add = pop(stack);
                    const auto multiplier = pop(stack);
                    const auto value = pop(stack);
                    stack.push_back({
                        add.x + value.x * multiplier.x, add.y + value.y * multiplier.y,
                        add.z + value.z * multiplier.z, add.w + value.w * multiplier.w,
                    });
                    break;
                }
                case OP_QUAT_SLERP: {
                    const auto amount = pop(stack);
                    const auto end = pop(stack);
                    const auto start = pop(stack);
                    stack.push_back(quat_nlerp(start, end, amount.x));
                    break;
                }
                case OP_TO_VECTOR: {
                    const auto z = pop(stack);
                    const auto y = pop(stack);
                    const auto x = pop(stack);
                    stack.push_back({x.x, y.x, z.x, 0.0});
                    break;
                }
                case OP_PUSH_TIME: stack.push_back({time, time, time, time}); break;
                case OP_PUSH_DELTA_TIME: stack.push_back({delta_time, delta_time, delta_time, delta_time}); break;
                case OP_VECTOR_TRANSFORM: {
                    const auto rotation = pop(stack);
                    const auto vector = pop(stack);
                    stack.push_back(quat_rotate_vector(rotation, vector));
                    break;
                }
                case OP_GET_VARIABLE: {
                    const auto found = data.variables.find(instruction.variable_key);
                    stack.push_back(found == data.variables.end() ? Vec4{} : found->second);
                    break;
                }
                case OP_SET_VARIABLE: data.variables[instruction.variable_key] = pop(stack); break;
                case OP_BLEND_VECTOR: stack.push_back(blend(instruction, frame, false)); break;
                case OP_BLEND_QUATERNION: stack.push_back(blend(instruction, frame, true)); break;
                case OP_JUMP:
                case OP_JUMP_IF_FALSE:
                case OP_JUMP_IF_TRUE: {
                    auto take = instruction.opcode == OP_JUMP;
                    if (instruction.opcode == OP_JUMP_IF_FALSE) take = all_zero(top(stack));
                    else if (instruction.opcode == OP_JUMP_IF_TRUE) take = !all_zero(top(stack));
                    if (take) {
                        next_pc = pc + 1 + instruction.jump_offset;
                        if (next_pc < 0 || static_cast<std::size_t>(next_pc) >= stream.instructions.size()) {
                            throw std::runtime_error("jump target is outside the stream");
                        }
                    }
                    break;
                }
                default:
                    if (known_unsupported(instruction.opcode)) {
                        append_issue(
                            data,
                            stream,
                            instruction,
                            "yed.vm.unsupported_instruction",
                            std::string(opcode_name(instruction.opcode)) + " is not implemented"
                        );
                    } else {
                        char message[32];
                        std::snprintf(message, sizeof(message), "unsupported opcode 0x%02X", instruction.opcode);
                        append_issue(data, stream, instruction, "yed.vm.unknown_opcode", message);
                    }
                    return;
            }
        } catch (const std::exception& exception) {
            append_issue(
                data,
                stream,
                instruction,
                "yed.vm.execution_error",
                std::string(opcode_name(instruction.opcode)) + ": " + exception.what()
            );
            return;
        }
        pc = next_pc;
    }
    if (pc >= 0 && static_cast<std::size_t>(pc) < stream.instructions.size() && steps >= max_steps) {
        data.issues.push_back({
            "yed.vm.step_limit",
            "expression stream exceeded its deterministic instruction limit",
            stream.expression,
            stream.name,
            -1,
        });
    }
}

}

void evaluate_yed_program(
    const YedProgram& program,
    YedFrameData& data,
    double time,
    double delta_time
) {
    Frame frame(program, data);
    for (const auto& stream : program.streams) {
        run_stream(stream, frame, data, time, delta_time);
    }
}

}
