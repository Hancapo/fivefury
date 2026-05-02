#include "crypto_magic.h"

#include <array>
#include <cstdlib>
#include <limits>

namespace fivefury_native {

namespace {

class MagicRandom {
public:
    explicit MagicRandom(std::int32_t seed) {
        int subtraction = seed == std::numeric_limits<std::int32_t>::min() ? MBIG : std::abs(seed);
        int mj = MSEED - subtraction;
        if (mj < 0) {
            mj += MBIG;
        }
        seed_array_.fill(0);
        seed_array_[55] = mj;
        int mk = 1;
        for (int i = 1; i < 55; ++i) {
            const int ii = (21 * i) % 55;
            seed_array_[ii] = mk;
            mk = mj - mk;
            if (mk < 0) {
                mk += MBIG;
            }
            mj = seed_array_[ii];
        }
        for (int round = 0; round < 4; ++round) {
            for (int i = 1; i < 56; ++i) {
                seed_array_[i] -= seed_array_[1 + (i + 30) % 55];
                if (seed_array_[i] < 0) {
                    seed_array_[i] += MBIG;
                }
            }
        }
    }

    std::uint8_t next_byte() {
        return static_cast<std::uint8_t>(internal_sample() % 256);
    }

private:
    static constexpr int MBIG = 2147483647;
    static constexpr int MSEED = 161803398;

    int internal_sample() {
        int loc_inext = inext_ + 1;
        if (loc_inext >= 56) {
            loc_inext = 1;
        }
        int loc_inextp = inextp_ + 1;
        if (loc_inextp >= 56) {
            loc_inextp = 1;
        }
        int result = seed_array_[loc_inext] - seed_array_[loc_inextp];
        if (result == MBIG) {
            --result;
        }
        if (result < 0) {
            result += MBIG;
        }
        seed_array_[loc_inext] = result;
        inext_ = loc_inext;
        inextp_ = loc_inextp;
        return result;
    }

    std::array<int, 56> seed_array_{};
    int inext_ = 0;
    int inextp_ = 21;
};

}  // namespace

std::string build_magic_mask(std::int32_t seed, std::size_t length, unsigned int rounds) {
    std::string mask(length, '\0');
    MagicRandom rng(seed);
    for (unsigned int round = 0; round < rounds; ++round) {
        for (std::size_t index = 0; index < mask.size(); ++index) {
            const auto current = static_cast<unsigned char>(mask[index]);
            mask[index] = static_cast<char>((current + rng.next_byte()) & 0xFFU);
        }
    }
    return mask;
}

}  // namespace fivefury_native
