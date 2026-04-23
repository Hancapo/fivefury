from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...hashing import jenk_hash
from ..model import CutHashedString, CutNode
from .shared import _clone_value, _coerce_name, _hashed_string, _node_type_hash, _object_name_field, _object_role


@dataclass(slots=True)
class CutBinding:
    object_id: int
    type_name: str
    role: str
    name: str | None
    fields: dict[str, Any] = field(default_factory=dict)
    raw: CutNode | None = None

    @property
    def display_name(self) -> str:
        return self.name or f"{self.role}:{self.object_id}"

    @classmethod
    def new(
        cls,
        *,
        object_id: int,
        type_name: str,
        name: str | None = None,
        role: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> "CutBinding":
        role_name = role or _object_role(type_name)
        field_values = dict(fields or {})
        name_field = _object_name_field(type_name)
        if name is not None and name_field not in field_values:
            if type_name == "rage__cutfAudioObject":
                field_values[name_field] = name
            else:
                field_values[name_field] = _hashed_string(name)
        raw = CutNode(type_name=type_name, type_hash=_node_type_hash(type_name), fields={})
        return cls(object_id=object_id, type_name=type_name, role=role_name, name=name, fields=field_values, raw=raw)

    def to_node(self) -> CutNode:
        node = _clone_value(self.raw) if self.raw is not None else CutNode(type_name=self.type_name)
        node.type_name = self.type_name
        node.type_hash = _node_type_hash(self.type_name, node.type_hash)
        node.fields["iObjectId"] = self.object_id
        for key, value in self.fields.items():
            node.fields[key] = _clone_value(value)
        if self.name is not None:
            field_name = _object_name_field(self.type_name)
            if field_name in node.fields:
                if self.type_name == "rage__cutfAudioObject":
                    node.fields[field_name] = self.name
                else:
                    current = node.fields[field_name]
                    node.fields[field_name] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) and current.hash else jenk_hash(self.name), text=self.name)
        return node


class _TypedCutBinding(CutBinding):
    TYPE_NAME = ""
    ROLE = ""

    def __init__(
        self,
        name: str | None = None,
        *,
        object_id: int = -1,
        fields: dict[str, Any] | None = None,
        raw: CutNode | None = None,
    ) -> None:
        type_name = self.TYPE_NAME
        role = self.ROLE or _object_role(type_name)
        field_values = dict(fields or {})
        if name is not None:
            name_field = _object_name_field(type_name)
            if name_field not in field_values:
                field_values[name_field] = name if type_name == "rage__cutfAudioObject" else _hashed_string(name)
        super().__init__(
            object_id=object_id,
            type_name=type_name,
            role=role,
            name=name,
            fields=field_values,
            raw=raw if raw is not None else CutNode(type_name=type_name, type_hash=_node_type_hash(type_name), fields={}),
        )


class CutAssetManager(_TypedCutBinding):
    TYPE_NAME = "rage__cutfAssetManagerObject"
    ROLE = "asset_manager"


class CutAnimationManager(_TypedCutBinding):
    TYPE_NAME = "rage__cutfAnimationManagerObject"
    ROLE = "animation_manager"


class CutCamera(_TypedCutBinding):
    TYPE_NAME = "rage__cutfCameraObject"
    ROLE = "camera"


class CutPed(_TypedCutBinding):
    TYPE_NAME = "rage__cutfPedModelObject"
    ROLE = "ped"


class CutProp(_TypedCutBinding):
    TYPE_NAME = "rage__cutfPropModelObject"
    ROLE = "prop"


class CutVehicle(_TypedCutBinding):
    TYPE_NAME = "rage__cutfVehicleModelObject"
    ROLE = "vehicle"


class CutLight(_TypedCutBinding):
    TYPE_NAME = "rage__cutfLightObject"
    ROLE = "light"


class CutAudio(_TypedCutBinding):
    TYPE_NAME = "rage__cutfAudioObject"
    ROLE = "audio"


class CutSubtitle(_TypedCutBinding):
    TYPE_NAME = "rage__cutfSubtitleObject"
    ROLE = "subtitle"


class CutFade(_TypedCutBinding):
    TYPE_NAME = "rage__cutfScreenFadeObject"
    ROLE = "fade"


class CutOverlay(_TypedCutBinding):
    TYPE_NAME = "rage__cutfOverlayObject"
    ROLE = "overlay"


class CutHiddenObject(_TypedCutBinding):
    TYPE_NAME = "rage__cutfHiddenModelObject"
    ROLE = "hidden_object"


class CutBlockingBounds(_TypedCutBinding):
    TYPE_NAME = "rage__cutfBlockingBoundsObject"
    ROLE = "blocking_bounds"


_BINDING_CLASS_BY_TYPE = {
    CutAssetManager.TYPE_NAME: CutAssetManager,
    CutAnimationManager.TYPE_NAME: CutAnimationManager,
    CutCamera.TYPE_NAME: CutCamera,
    CutPed.TYPE_NAME: CutPed,
    CutProp.TYPE_NAME: CutProp,
    CutVehicle.TYPE_NAME: CutVehicle,
    CutLight.TYPE_NAME: CutLight,
    CutAudio.TYPE_NAME: CutAudio,
    CutSubtitle.TYPE_NAME: CutSubtitle,
    CutFade.TYPE_NAME: CutFade,
    CutOverlay.TYPE_NAME: CutOverlay,
    CutHiddenObject.TYPE_NAME: CutHiddenObject,
    CutBlockingBounds.TYPE_NAME: CutBlockingBounds,
}

_ROLE_PROPERTY_NAMES = {
    "camera": "cameras",
    "ped": "peds",
    "prop": "props",
    "vehicle": "vehicles",
    "light": "lights",
    "audio": "audio",
    "subtitle": "subtitles",
    "fade": "fades",
    "overlay": "overlays",
    "particle_fx": "particle_effects",
    "blocking_bounds": "blocking_bounds",
    "animation_manager": "animation_managers",
    "asset_manager": "asset_managers",
}

_BINDING_ADDERS = {
    "asset_manager": CutAssetManager,
    "animation_manager": CutAnimationManager,
    "camera": CutCamera,
    "ped": CutPed,
    "prop": CutProp,
    "vehicle": CutVehicle,
    "light": CutLight,
    "audio": CutAudio,
    "subtitle": CutSubtitle,
    "fade": CutFade,
}


def _binding_from_node(node: CutNode) -> CutBinding:
    fields = {key: _clone_value(value) for key, value in node.fields.items() if key != "iObjectId"}
    name = _coerce_name(node.fields.get("cName")) or _coerce_name(node.fields.get("StreamingName"))
    binding_class = _BINDING_CLASS_BY_TYPE.get(node.type_name)
    if binding_class is not None:
        return binding_class(
            name=name,
            object_id=int(node.fields.get("iObjectId", -1)),
            fields=fields,
            raw=_clone_value(node),
        )
    return CutBinding(
        object_id=int(node.fields.get("iObjectId", -1)),
        type_name=node.type_name,
        role=_object_role(node.type_name),
        name=name,
        fields=fields,
        raw=_clone_value(node),
    )
