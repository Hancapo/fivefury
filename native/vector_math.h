#pragma once

#include <algorithm>
#include <cmath>

namespace fivefury_native {

struct Vec4 {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
    double w = 0.0;

    double& operator[](std::size_t index) { return (&x)[index]; }
    const double& operator[](std::size_t index) const { return (&x)[index]; }
};

inline Vec4 vec4_add(const Vec4& left, const Vec4& right) {
    return {left.x + right.x, left.y + right.y, left.z + right.z, left.w + right.w};
}

inline Vec4 vec4_sub(const Vec4& left, const Vec4& right) {
    return {left.x - right.x, left.y - right.y, left.z - right.z, left.w - right.w};
}

inline Vec4 quat_normalize(const Vec4& value) {
    const auto length = std::sqrt(
        value.x * value.x + value.y * value.y + value.z * value.z + value.w * value.w
    );
    if (length <= 1e-12) {
        return {0.0, 0.0, 0.0, 1.0};
    }
    const auto inverse = 1.0 / length;
    return {value.x * inverse, value.y * inverse, value.z * inverse, value.w * inverse};
}

inline Vec4 quat_inverse(const Vec4& value) {
    const auto normalized = quat_normalize(value);
    return {-normalized.x, -normalized.y, -normalized.z, normalized.w};
}

inline Vec4 quat_multiply_raw(const Vec4& left, const Vec4& right) {
    return {
        left.w * right.x + left.x * right.w + left.y * right.z - left.z * right.y,
        left.w * right.y - left.x * right.z + left.y * right.w + left.z * right.x,
        left.w * right.z + left.x * right.y - left.y * right.x + left.z * right.w,
        left.w * right.w - left.x * right.x - left.y * right.y - left.z * right.z,
    };
}

inline Vec4 quat_multiply(const Vec4& left, const Vec4& right) {
    return quat_normalize(quat_multiply_raw(left, right));
}

inline Vec4 quat_from_euler_xyz_raw(const Vec4& value) {
    const auto cx = std::cos(value.x * 0.5);
    const auto sx = std::sin(value.x * 0.5);
    const auto cy = std::cos(value.y * 0.5);
    const auto sy = std::sin(value.y * 0.5);
    const auto cz = std::cos(value.z * 0.5);
    const auto sz = std::sin(value.z * 0.5);
    return {
        sx * cy * cz + cx * sy * sz,
        cx * sy * cz - sx * cy * sz,
        cx * cy * sz + sx * sy * cz,
        cx * cy * cz - sx * sy * sz,
    };
}

inline Vec4 quat_from_euler_xyz(const Vec4& value) {
    return quat_normalize(quat_from_euler_xyz_raw(value));
}

inline Vec4 quat_to_euler_xyz(const Vec4& value) {
    const auto q = quat_normalize(value);
    const auto sin_x = 2.0 * (q.w * q.x - q.y * q.z);
    const auto cos_x = 1.0 - 2.0 * (q.x * q.x + q.y * q.y);
    const auto pitch = std::asin(std::clamp(2.0 * (q.w * q.y + q.z * q.x), -1.0, 1.0));
    const auto roll = std::atan2(sin_x, cos_x);
    const auto yaw = std::atan2(
        2.0 * (q.w * q.z - q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    );
    return {roll, pitch, yaw, 0.0};
}

inline Vec4 quat_nlerp(const Vec4& start, Vec4 end, double amount) {
    const auto dot = start.x * end.x + start.y * end.y + start.z * end.z + start.w * end.w;
    if (dot < 0.0) {
        end = {-end.x, -end.y, -end.z, -end.w};
    }
    return quat_normalize({
        start.x + (end.x - start.x) * amount,
        start.y + (end.y - start.y) * amount,
        start.z + (end.z - start.z) * amount,
        start.w + (end.w - start.w) * amount,
    });
}

inline Vec4 quat_rotate_vector(const Vec4& rotation, const Vec4& value) {
    const auto length_sq = rotation.x * rotation.x + rotation.y * rotation.y +
                           rotation.z * rotation.z + rotation.w * rotation.w;
    if (length_sq <= 1e-16) {
        return value;
    }
    const auto inverse_length = 1.0 / std::sqrt(length_sq);
    const auto qx = rotation.x * inverse_length;
    const auto qy = rotation.y * inverse_length;
    const auto qz = rotation.z * inverse_length;
    const auto qw = rotation.w * inverse_length;
    const auto uvx = qy * value.z - qz * value.y;
    const auto uvy = qz * value.x - qx * value.z;
    const auto uvz = qx * value.y - qy * value.x;
    const auto uuvx = qy * uvz - qz * uvy;
    const auto uuvy = qz * uvx - qx * uvz;
    const auto uuvz = qx * uvy - qy * uvx;
    return {
        value.x + uvx * (2.0 * qw) + uuvx * 2.0,
        value.y + uvy * (2.0 * qw) + uuvy * 2.0,
        value.z + uvz * (2.0 * qw) + uuvz * 2.0,
        value.w,
    };
}

}
