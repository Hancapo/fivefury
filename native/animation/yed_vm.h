#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

#include "math/vector.h"

namespace fivefury_native {

using YedTrackKey = std::uint64_t;
using YedVariableKey = std::uint64_t;

inline YedTrackKey yed_track_key(std::int64_t bone, std::int64_t track) {
    return (static_cast<std::uint64_t>(bone) << 32U) |
           (static_cast<std::uint64_t>(track) & 0xFFFFFFFFULL);
}

inline YedVariableKey yed_variable_key(std::uint64_t hash, std::uint64_t index) {
    return ((hash & 0xFFFFFFFFULL) << 32U) | (index & 0xFFFFFFFFULL);
}

struct YedBlendInterval {
    double begin = 0.0;
    double multiplier = 0.0;
    double additive = 0.0;
};

struct YedBlendAxis {
    double multiplier = 0.0;
    double additive = 0.0;
    std::vector<YedBlendInterval> intervals;
};

struct YedBlendSource {
    YedTrackKey key = 0;
    std::uint8_t component = 0;
    std::array<YedBlendAxis, 3> axes;
};

struct YedInstructionProgram {
    std::uint8_t opcode = 0;
    std::int32_t index = 0;
    bool parsed = true;
    std::string parse_error;
    std::string operand_error;
    YedTrackKey track_key = 0;
    std::uint8_t component = 0;
    std::uint8_t format = 0;
    bool use_defaults = false;
    Vec4 value;
    YedVariableKey variable_key = 0;
    std::int32_t jump_offset = 0;
    std::vector<YedBlendSource> blend_sources;
};

struct YedStreamProgram {
    std::string expression;
    std::string name;
    std::vector<YedInstructionProgram> instructions;
};

struct YedBoneDefaults {
    Vec4 translation;
    Vec4 rotation{0.0, 0.0, 0.0, 1.0};
    Vec4 scale{1.0, 1.0, 1.0, 0.0};
};

struct YedProgram {
    std::vector<YedStreamProgram> streams;
    std::unordered_map<std::int64_t, YedBoneDefaults> bones;
};

struct YedIssueData {
    std::string code;
    std::string message;
    std::string expression;
    std::string stream;
    std::int32_t instruction = -1;
};

struct YedFrameData {
    std::unordered_map<YedTrackKey, Vec4> tracks;
    std::unordered_map<YedTrackKey, Vec4> outputs;
    std::unordered_map<YedVariableKey, Vec4> variables;
    std::vector<YedIssueData> issues;
};

void evaluate_yed_program(
    const YedProgram& program,
    YedFrameData& frame,
    double time,
    double delta_time
);

}
