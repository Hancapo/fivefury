from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import ceil
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ..authoring import DiagnosticSeverity, ValidationReport
from ..awc.layout import AwcSpeaker, default_awc_speakers
from ..game_target import GameTarget, coerce_game_target
from .audio_profiles import (
    CutAudioProfile,
)

if TYPE_CHECKING:
    from ..authoring import BuildContext
    from ..awc import Awc
    from ..rel import RelFile


_LOGICAL_SUFFIXES = (
    "_EDITED",
    "_MASTERED",
    "_MASTERED_ONLY",
    "_MASTERED_REPLAY",
    "_MASTERED_REPLAY_ONLY",
    "_MASTERED_TRIMMED",
)


def _reference_base(reference: str) -> str:
    value = str(reference).strip().replace("\\", "/")
    path = PurePosixPath(value)
    if not value or path.name != value or path.suffix.casefold() != ".wa":
        raise ValueError("CUT audio reference must be a filename ending in .WA")
    base = path.stem.upper()
    if not base or base.endswith(_LOGICAL_SUFFIXES):
        raise ValueError(
            "CUT audio reference must not include an edited or mastered suffix"
        )
    return base


def _file_name(value: str, suffix: str, *, field: str) -> str:
    path = PurePosixPath(str(value).strip().replace("\\", "/"))
    if not path.name or path.name != str(path) or path.suffix.casefold() != suffix:
        raise ValueError(f"{field} must be a filename ending in {suffix}")
    return path.name.casefold()


def _wavepack_name(value: str) -> str:
    path = PurePosixPath(str(value).strip().replace("\\", "/"))
    name = path.name.casefold()
    if not name or name != str(path) or len(name) < 8:
        raise ValueError("wavepack_name must be one folder name of at least 8 characters")
    return name


def _stream_durations(awc: Awc) -> tuple[tuple[int, float], ...]:
    from ..awc import awc_playback_streams

    streams = awc_playback_streams(awc)
    if awc.multi_channel_flag:
        if len(streams) != 1 or streams[0].stream_format_chunk is None:
            return ()
        return tuple(
            (
                int(channel.id),
                (
                    float(channel.samples) / float(channel.sample_rate)
                    if channel.sample_rate
                    else 0.0
                ),
            )
            for channel in streams[0].stream_format_chunk.channels
        )
    return tuple((stream.hash, stream.duration) for stream in streams)


def _duration_ms(streams: tuple[tuple[int, float], ...]) -> int:
    return ceil(max((duration for _stream_hash, duration in streams), default=0.0) * 1000.0)


@dataclass(slots=True)
class CutsceneAudioAssets:
    reference: str
    awc: Awc
    sounds: RelFile
    awc_name: str
    sounds_name: str
    wavepack_name: str
    game: GameTarget = GameTarget.GTA5
    channels: tuple[AwcSpeaker, ...] = ()

    def __post_init__(self) -> None:
        self.game = coerce_game_target(self.game)
        channel_count = len(_stream_durations(self.awc))
        if not self.channels and channel_count:
            self.channels = default_awc_speakers(channel_count)
        else:
            self.channels = tuple(AwcSpeaker(channel) for channel in self.channels)

    @property
    def base_name(self) -> str:
        return _reference_base(self.reference)

    @property
    def root_name(self) -> str:
        return f"CUTSCENES_{self.base_name}_MASTERED_ONLY"

    @property
    def bank_name(self) -> str:
        return f"{self.wavepack_name}/{PurePosixPath(self.awc_name).stem}"

    @property
    def duration(self) -> float:
        return max(
            (duration for _stream_hash, duration in _stream_durations(self.awc)),
            default=0.0,
        )

    def validate(
        self,
        *,
        context: BuildContext | None = None,
    ) -> ValidationReport:
        from ..awc import awc_channel_codecs, validate_awc
        from ..rel import (
            Dat54SimpleSound,
            Dat54StreamingSound,
            RelDatFileType,
            RelSoundIndex,
            rel_hash,
        )

        target = self.game if context is None else context.game
        report = ValidationReport()
        if target is not self.game:
            report.issue(
                "cut.audio.target.mismatch",
                "CUT audio target does not match the build context",
                path="game",
            )
        try:
            _reference_base(self.reference)
        except ValueError as exc:
            report.issue("cut.audio.reference.invalid", str(exc), path="reference")
        for field, value, suffix in (
            ("awc_name", self.awc_name, ".awc"),
            ("sounds_name", self.sounds_name, ".dat"),
        ):
            try:
                _file_name(value, suffix, field=field)
            except ValueError as exc:
                report.issue("cut.audio.name.invalid", str(exc), path=field)
        try:
            _wavepack_name(self.wavepack_name)
        except ValueError as exc:
            report.issue("cut.audio.wavepack.invalid", str(exc), path="wavepack_name")

        report.extend(validate_awc(self.awc), path="awc")
        streams = _stream_durations(self.awc)
        if not streams:
            report.issue(
                "cut.audio.stream.unresolved",
                "AWC contains no playable stream for CUT audio",
                path="awc.streams",
            )
        durations = {round(duration, 9) for _stream_hash, duration in streams}
        if len(durations) > 1:
            report.issue(
                "cut.audio.stream.duration_mismatch",
                "CUT audio streams must have matching durations",
                path="awc.streams",
            )
        if len(self.channels) != len(streams):
            report.issue(
                "cut.audio.routing.count_mismatch",
                "CUT audio channel layout does not match the AWC channel count",
                path="channels",
            )
        if int(self.sounds.rel_type) != int(RelDatFileType.DAT54_DATA_ENTRIES):
            report.issue(
                "cut.audio.sounddata.invalid",
                "CUT audio sound metadata must be a DAT54 REL",
                path="sounds.rel_type",
            )
            return report

        items_by_hash = {
            int(item.name_hash) & 0xFFFFFFFF: item for item in self.sounds.items
        }
        if len(items_by_hash) != len(self.sounds.items):
            report.issue(
                "cut.audio.sound.collision",
                "DAT54 sound names contain a hash collision",
                path="sounds.items",
            )
        root = items_by_hash.get(rel_hash(self.root_name))
        if not isinstance(root, Dat54StreamingSound):
            report.issue(
                "cut.audio.sound.unresolved",
                f"DAT54 has no streaming root named {self.root_name}",
                path="sounds.items",
            )
            return report

        profile = CutAudioProfile.retail(self.game)
        expected_root = profile.streaming_header()
        for field in ("flags", "flags2", "release_time", "category", "speaker_mask"):
            if getattr(root.header, field) != getattr(expected_root, field):
                report.issue(
                    "cut.audio.header.streaming.invalid",
                    f"CUT streaming root has an invalid {field}",
                    path=f"sounds.items[0x{root.name_hash:08X}].header.{field}",
                )

        graph = RelSoundIndex((self.sounds,)).resolve(root.name_hash)
        for unresolved_hash in graph.unresolved_hashes:
            report.issue(
                "cut.audio.sound.child_unresolved",
                f"DAT54 references missing sound 0x{unresolved_hash:08X}",
                path="sounds.items",
            )
        expected_streams = {stream_hash & 0xFFFFFFFF for stream_hash, _ in streams}
        actual_streams = {endpoint.stream_hash for endpoint in graph.endpoints}
        if actual_streams != expected_streams:
            report.issue(
                "cut.audio.stream.unresolved",
                "DAT54 stream references do not match the playable AWC streams",
                path="sounds.items",
            )
        expected_container = rel_hash(self.bank_name)
        if any(
            endpoint.container_hash != expected_container for endpoint in graph.endpoints
        ):
            report.issue(
                "cut.audio.container.unresolved",
                "DAT54 container does not match the authored wavepack bank name",
                path="sounds.items",
            )
        children = [items_by_hash.get(rel_hash(value)) for value in root.child_sounds]
        if len(children) != len(self.channels):
            report.issue(
                "cut.audio.routing.count_mismatch",
                "DAT54 child count does not match the CUT audio channel layout",
                path="sounds.items",
            )
        routes = profile.routes(self.channels)
        for index, (item, route) in enumerate(zip(children, routes)):
            if not isinstance(item, Dat54SimpleSound):
                continue
            expected = route.header()
            for field in ("flags", "pan", "speaker_mask"):
                if getattr(item.header, field) != getattr(expected, field):
                    report.issue(
                        "cut.audio.routing.invalid",
                        f"CUT channel {index} has an invalid {field}",
                        path=f"sounds.items[0x{item.name_hash:08X}].header.{field}",
                    )
        for sound_hash in graph.sound_hashes:
            item = items_by_hash.get(sound_hash)
            if isinstance(item, Dat54SimpleSound) and item.wave_slot_index != 0:
                report.issue(
                    "cut.audio.wave_slot.invalid",
                    "CUT mastered audio requires wave slot index 0",
                    path=f"sounds.items[0x{sound_hash:08X}].wave_slot_index",
                )
        if self.awc.multi_channel_flag and int(self.awc.flags) != profile.multichannel_flags:
            report.issue(
                "cut.audio.awc.flags.invalid",
                f"CUT multichannel AWC flags must be 0x{profile.multichannel_flags:04X} for {self.game.value}",
                path="awc.flags",
            )
        codecs = awc_channel_codecs(self.awc)
        if self.game is GameTarget.GTA5_ENHANCED and codecs and any(
            int(codec) == 0 for codec in codecs
        ):
            report.issue(
                "cut.audio.codec.uncompressed",
                "Enhanced CUT audio is authored as uncompressed PCM",
                severity=DiagnosticSeverity.WARNING,
                path="awc.streams",
            )
        required_duration = _duration_ms(streams)
        if int(root.duration) < required_duration:
            report.issue(
                "cut.audio.duration.insufficient",
                f"DAT54 duration {root.duration} ms is shorter than the AWC duration {required_duration} ms",
                path="sounds.duration",
            )
        if self.bank_name not in self.sounds.name_table:
            report.issue(
                "cut.audio.container.unresolved",
                "DAT54 name table does not contain the AWC bank name",
                path="sounds.name_table",
            )
        return report

    def build_files(self) -> dict[str, bytes]:
        from ..awc import read_awc
        from ..rel import read_rel

        self.validate().raise_for_errors()
        awc_data = self.awc.to_bytes()
        sounds_data = self.sounds.to_bytes()
        rebuilt = CutsceneAudioAssets(
            reference=self.reference,
            awc=read_awc(awc_data, path=self.awc_name),
            sounds=read_rel(sounds_data, path=self.sounds_name),
            awc_name=self.awc_name,
            sounds_name=self.sounds_name,
            wavepack_name=self.wavepack_name,
            game=self.game,
            channels=self.channels,
        )
        from ..authoring import BuildContext

        rebuilt.validate(context=BuildContext(game=self.game)).raise_for_errors()
        return {self.sounds_name: sounds_data, self.awc_name: awc_data}


def build_cutscene_audio_assets(
    reference: str,
    awc: Awc,
    *,
    wavepack_name: str,
    awc_name: str | None = None,
    context: BuildContext,
    channels: tuple[AwcSpeaker, ...] | None = None,
) -> CutsceneAudioAssets:
    from ..rel import (
        Dat54SimpleSound,
        Dat54StreamingSound,
        RelDatFileType,
        RelFile,
        rel_hash,
    )

    base = _reference_base(reference)
    logical_reference = f"{base}.WA"
    pack_name = _wavepack_name(wavepack_name)
    physical_name = _file_name(
        awc_name or f"{base.casefold()}_mastered_only.awc",
        ".awc",
        field="awc_name",
    )
    sounds_name = f"{base.casefold()}_sounds.dat"
    authored_awc = deepcopy(awc)
    profile = CutAudioProfile.retail(context.game)
    if authored_awc.multi_channel_flag:
        authored_awc.flags = profile.multichannel_flags
    streams = _stream_durations(authored_awc)
    if not streams:
        raise ValueError("AWC contains no playable stream for CUT audio")
    stream_hashes = [stream_hash & 0xFFFFFFFF for stream_hash, _ in streams]
    if len(stream_hashes) != len(set(stream_hashes)):
        raise ValueError("AWC playable stream hashes must be unique")
    bank_name = f"{pack_name}/{PurePosixPath(physical_name).stem}"
    root_name = f"CUTSCENES_{base}_MASTERED_ONLY"
    child_names = [
        f"{root_name}_STREAM_{index + 1}_{stream_hash:08X}"
        for index, stream_hash in enumerate(stream_hashes)
    ]
    child_hashes = [rel_hash(name) for name in child_names]
    all_hashes = [rel_hash(root_name), *child_hashes]
    if len(all_hashes) != len(set(all_hashes)):
        raise ValueError("Derived DAT54 sound names contain a hash collision")
    channel_layout = (
        default_awc_speakers(len(streams))
        if channels is None
        else tuple(AwcSpeaker(channel) for channel in channels)
    )
    if len(channel_layout) != len(streams):
        raise ValueError("CUT audio channel layout must match the AWC channel count")
    routes = profile.routes(channel_layout)
    sounds = RelFile(
        RelDatFileType.DAT54_DATA_ENTRIES,
        items=[
            Dat54StreamingSound(
                name_hash=all_hashes[0],
                header=profile.streaming_header(),
                child_sounds=child_hashes,
                duration=_duration_ms(streams),
            ),
            *(
                Dat54SimpleSound(
                    name_hash=child_hash,
                    header=route.header(),
                    container_name=bank_name,
                    file_name=stream_hash,
                    wave_slot_index=0,
                )
                for child_hash, stream_hash, route in zip(
                    child_hashes, stream_hashes, routes, strict=True
                )
            ),
        ],
        name_table=[bank_name],
        path=sounds_name,
    )
    assets = CutsceneAudioAssets(
        reference=logical_reference,
        awc=authored_awc,
        sounds=sounds,
        awc_name=physical_name,
        sounds_name=sounds_name,
        wavepack_name=pack_name,
        game=context.game,
        channels=channel_layout,
    )
    assets.validate(context=context).raise_for_errors()
    return assets


__all__ = ["CutsceneAudioAssets", "build_cutscene_audio_assets"]
