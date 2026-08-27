from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import overload

from .._native import NativeYcdTrackSampler
from ..vector import Quaternion, Vector3
from .sequence_tracks import YcdTrackFormat

YcdTrackSample = float | Vector3 | Quaternion


@dataclass(frozen=True, slots=True)
class YcdSampleWindow:
    components: tuple[Sequence[float], ...]
    dynamic: bool
    omitted_component: int = -1


def _coerce_sample(value: object, track_format: YcdTrackFormat) -> YcdTrackSample:
    if track_format is YcdTrackFormat.FLOAT:
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            raise TypeError("Float tracks require float samples, not sequences")
        return float(value)
    if track_format is YcdTrackFormat.VECTOR3:
        if not isinstance(value, Vector3):
            raise TypeError(
                f"Vector3 tracks require Vector3 samples, got {type(value).__name__}"
            )
        return value
    if not isinstance(value, Quaternion):
        raise TypeError(
            f"Quaternion tracks require Quaternion samples, got {type(value).__name__}"
        )
    return value.normalized_strict()


def _is_per_frame_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, Vector3, Quaternion)
    )


def _mapping_keyframes(
    source: Mapping[object, object],
    *,
    track_format: YcdTrackFormat,
    frame_count: int,
    fps: float,
) -> tuple[list[int], list[YcdTrackSample]]:
    if not source:
        raise ValueError("Keyframe mapping cannot be empty")
    keyed = [
        (
            min(max(round(float(time) * fps), 0), frame_count - 1),
            _coerce_sample(value, track_format),
        )
        for time, value in source.items()
    ]
    keyed.sort(key=lambda item: item[0])
    deduped: list[tuple[int, YcdTrackSample]] = []
    for frame, value in keyed:
        if deduped and deduped[-1][0] == frame:
            deduped[-1] = (frame, value)
        else:
            deduped.append((frame, value))
    return (
        [frame for frame, _ in deduped],
        [value for _, value in deduped],
    )


class YcdTrackSamples(Sequence[YcdTrackSample]):
    __slots__ = ("_format", "_frame_count", "_sampler")

    def __init__(
        self,
        source: object,
        *,
        track_format: YcdTrackFormat,
        frame_count: int,
        fps: float,
    ) -> None:
        self._format = YcdTrackFormat(track_format)
        self._frame_count = int(frame_count)
        if self.frame_count <= 0:
            raise ValueError("YCD track frame_count must be positive")

        frames: list[int] | None
        values: object
        if isinstance(source, Mapping):
            frames, values = _mapping_keyframes(
                source,
                track_format=self.format,
                frame_count=self.frame_count,
                fps=float(fps),
            )
        elif _is_per_frame_sequence(source):
            if len(source) != self.frame_count:
                raise ValueError(
                    f"Expected {self.frame_count} per-frame samples, got {len(source)}"
                )
            frames = None
            values = source
        else:
            frames = [0]
            values = [_coerce_sample(source, self.format)]

        self._sampler = NativeYcdTrackSampler(
            values,
            frames,
            int(self.format),
            self.frame_count,
            Vector3,
            Quaternion,
        )

    def __len__(self) -> int:
        return self.frame_count

    @property
    def format(self) -> YcdTrackFormat:
        return self._format

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def __deepcopy__(self, memo: dict[int, object]) -> YcdTrackSamples:
        del memo
        return self

    def __iter__(self) -> Iterator[YcdTrackSample]:
        components = self.window(0, self.frame_count).components
        if self.format is YcdTrackFormat.FLOAT:
            yield from components[0]
            return
        sample_type = (
            Vector3 if self.format is YcdTrackFormat.VECTOR3 else Quaternion
        )
        for values in zip(*components, strict=True):
            yield sample_type.from_iterable(values)

    @property
    def retained_count(self) -> int:
        return self._sampler.retained_count

    def window(
        self,
        start: int,
        count: int,
        *,
        orient_cached: bool = False,
    ) -> YcdSampleWindow:
        components, dynamic, omitted = self._sampler.window(
            start,
            count,
            orient_cached=orient_cached,
        )
        return YcdSampleWindow(components, dynamic, omitted)

    def _sample(self, index: int) -> YcdTrackSample:
        normalized = int(index)
        if normalized < 0:
            normalized += self.frame_count
        if normalized < 0 or normalized >= self.frame_count:
            raise IndexError("YCD track sample index out of range")
        components = self.window(normalized, 1).components
        if self.format is YcdTrackFormat.FLOAT:
            return components[0][0]
        values = tuple(component[0] for component in components)
        if self.format is YcdTrackFormat.VECTOR3:
            return Vector3.from_iterable(values)
        return Quaternion.from_iterable(values)

    @overload
    def __getitem__(self, index: int) -> YcdTrackSample: ...

    @overload
    def __getitem__(self, index: slice) -> list[YcdTrackSample]: ...

    def __getitem__(self, index: int | slice) -> YcdTrackSample | list[YcdTrackSample]:
        if isinstance(index, int):
            return self._sample(index)
        indices = range(*index.indices(self.frame_count))
        if indices.step != 1:
            return [self._sample(frame) for frame in indices]
        count = len(indices)
        if count == 0:
            return []
        window = self.window(indices.start, count)
        if self.format is YcdTrackFormat.FLOAT:
            return list(window.components[0])
        sample_type = (
            Vector3 if self.format is YcdTrackFormat.VECTOR3 else Quaternion
        )
        return [
            sample_type.from_iterable(values)
            for values in zip(*window.components, strict=True)
        ]


__all__ = ["YcdSampleWindow", "YcdTrackSample", "YcdTrackSamples"]
