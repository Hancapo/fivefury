from fivefury import YcdChannelType
from fivefury.ycd.sequence_channels import (
    YcdCachedQuaternionChannel,
    YcdRawFloatChannel,
)

PAIRS = (
    (
        3,
        (
            0.7500555515289307,
            -0.18713344633579254,
            -0.6336289048194885,
            0.030201885046735766,
        ),
        (
            -0.7221301198005676,
            0.2660178244113922,
            0.6377001404762268,
            0.03318339959751179,
        ),
    ),
    (
        1,
        (
            0.6469215154647827,
            0.013298065472475832,
            0.689765989780426,
            0.32486703991889954,
        ),
        (
            -0.6486276984214783,
            0.04947353642910962,
            -0.6504743695259094,
            -0.3920683264732361,
        ),
    ),
)


def packed_channels(samples, omitted):
    components = [index for index in range(4) if index != omitted]
    return [
        *(
            YcdRawFloatChannel(
                channel_type=YcdChannelType.RAW_FLOAT,
                channel_index=slot,
                values=[value[index] for value in samples],
            )
            for slot, index in enumerate(components)
        ),
        YcdCachedQuaternionChannel(
            channel_type=(
                YcdChannelType.CACHED_QUATERNION1
                if omitted >= 0
                else YcdChannelType.CACHED_QUATERNION2
            ),
            channel_index=len(components),
            quat_index=max(omitted, 0),
        ),
    ]
