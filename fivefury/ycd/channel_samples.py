from __future__ import annotations

import numpy as np

from .sequence_channels import (
    YcdAnimChannel,
    YcdCachedQuaternionChannel,
    YcdIndirectQuantizeFloatChannel,
    YcdLinearFloatChannel,
    YcdQuantizeFloatChannel,
    YcdRawFloatChannel,
)


def decoded_channel_components(channel: YcdAnimChannel) -> np.ndarray:
    """Decoded component cycles; no quantization or interpolation is repeated."""
    if isinstance(channel, YcdCachedQuaternionChannel):
        raise ValueError("Cached quaternion opcodes require a sequence context")
    if isinstance(channel, YcdIndirectQuantizeFloatChannel):
        if not len(channel.frames) or not len(channel.values):
            return np.array([[channel.offset]], dtype=np.float64)
        indices = np.asarray(channel.frames, dtype=np.int64)
        values = np.asarray(channel.values, dtype=np.float64)
        result = np.full(len(indices), channel.offset, dtype=np.float64)
        valid = indices < len(values)
        result[valid] = values[indices[valid]]
        return result[:, None]
    if isinstance(
        channel, (YcdRawFloatChannel, YcdQuantizeFloatChannel, YcdLinearFloatChannel)
    ):
        values = np.asarray(channel.values, dtype=np.float64)
        if not len(values):
            values = np.array(
                [0.0 if isinstance(channel, YcdRawFloatChannel) else channel.offset],
                dtype=np.float64,
            )
        return values.reshape(-1, 1)
    return np.asarray(channel.evaluate_components(0), dtype=np.float64).reshape(1, -1)
