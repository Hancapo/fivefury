from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CutEventPayload:
    def to_fields(self) -> dict[str, Any]:
        return {}

    @property
    def event_label(self) -> str | None:
        return None

    @property
    def event_duration(self) -> float | None:
        return None


@dataclass(slots=True)
class CutLoadScenePayload(CutEventPayload):
    name: str
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0

    def to_fields(self) -> dict[str, Any]:
        return {
            "cName": self.name,
            "vOffset": self.offset,
            "fRotation": self.rotation,
            "fPitch": self.pitch,
            "fRoll": self.roll,
        }


@dataclass(slots=True)
class CutObjectIdListPayload(CutEventPayload):
    object_ids: list[int]

    def to_fields(self) -> dict[str, Any]:
        return {"iObjectIdList": list(self.object_ids)}


@dataclass(slots=True)
class CutNamePayload(CutEventPayload):
    name: str

    def to_fields(self) -> dict[str, Any]:
        return {"cName": self.name}

    @property
    def event_label(self) -> str | None:
        return self.name


@dataclass(slots=True)
class CutSubtitlePayload(CutEventPayload):
    text: str
    duration: float
    language_id: int = 0
    transition_in: int = 0
    transition_in_duration: float = 0.0
    transition_out: int = 0
    transition_out_duration: float = 0.0

    def to_fields(self) -> dict[str, Any]:
        return {
            "cName": self.text,
            "iLanguageID": self.language_id,
            "iTransitionIn": self.transition_in,
            "fTransitionInDuration": self.transition_in_duration,
            "iTransitionOut": self.transition_out,
            "fTransitionOutDuration": self.transition_out_duration,
            "fSubtitleDuration": self.duration,
        }

    @property
    def event_label(self) -> str | None:
        return self.text

    @property
    def event_duration(self) -> float | None:
        return self.duration


@dataclass(slots=True)
class CutCameraCutPayload(CutEventPayload):
    name: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_quaternion: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    near_draw_distance: float = 0.0
    far_draw_distance: float = 0.0
    map_lod_scale: float = 0.0

    def to_fields(self) -> dict[str, Any]:
        return {
            "cName": self.name,
            "vPosition": self.position,
            "vRotationQuaternion": self.rotation_quaternion,
            "fNearDrawDistance": self.near_draw_distance,
            "fFarDrawDistance": self.far_draw_distance,
            "fMapLodScale": self.map_lod_scale,
        }

    @property
    def event_label(self) -> str | None:
        return self.name
