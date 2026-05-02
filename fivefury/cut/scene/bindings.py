from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ...common import hash_value
from ...hashing import jenk_partial_hash
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
    metadata: dict[str, Any] = field(default_factory=dict)

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
                    node.fields[field_name] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) and current.hash else hash_value(self.name), text=self.name)
        return node


class CutPropAnimationPreset(Enum):
    NONE = "none"
    COMMON_PROP = "common_prop"
    COMMON_PROP_ALT_COMPRESSION = "common_prop_alt_compression"
    ALT_EXPORT_A = "alt_export_a"
    ALT_EXPORT_B = "alt_export_b"


class CutTypeFileStrategy(Enum):
    AUTO = "auto"
    YTYP = "ytyp"
    CONTAINER = "container"
    NONE = "none"


_CUT_PROP_ANIMATION_PRESETS: dict[CutPropAnimationPreset, dict[str, Any | None]] = {
    CutPropAnimationPreset.NONE: {
        "cAnimExportCtrlSpecFile": None,
        "cFaceExportCtrlSpecFile": None,
        "cAnimCompressionFile": None,
    },
    CutPropAnimationPreset.COMMON_PROP: {
        # Observed repeatedly in real cutscene props from maude_mcs_1, lamar_1_int and xm4_yard_ext.
        "cAnimExportCtrlSpecFile": CutHashedString(hash=1888971086),
        "cFaceExportCtrlSpecFile": CutHashedString(hash=0),
        "cAnimCompressionFile": CutHashedString(hash=1207668038),
    },
    CutPropAnimationPreset.COMMON_PROP_ALT_COMPRESSION: {
        # Observed in gen9_mig_int, gen9_mig_int_p1_t00 and sum25_cayo_surv_ext.
        "cAnimExportCtrlSpecFile": CutHashedString(hash=1888971086),
        "cFaceExportCtrlSpecFile": CutHashedString(hash=0),
        "cAnimCompressionFile": CutHashedString(hash=4002728289),
    },
    CutPropAnimationPreset.ALT_EXPORT_A: {
        # Observed in sum24_bty6_escape_mcs4 and xm4_yard_int.
        "cAnimExportCtrlSpecFile": CutHashedString(hash=2678174446),
        "cFaceExportCtrlSpecFile": CutHashedString(hash=0),
        "cAnimCompressionFile": CutHashedString(hash=1207668038),
    },
    CutPropAnimationPreset.ALT_EXPORT_B: {
        # Observed in sum24_office_int and xm3_drg1_bmx_int.
        "cAnimExportCtrlSpecFile": CutHashedString(hash=2700143237),
        "cFaceExportCtrlSpecFile": CutHashedString(hash=0),
        "cAnimCompressionFile": CutHashedString(hash=1207668038),
    },
}


def _coerce_cut_prop_animation_preset(value: "CutPropAnimationPreset | str | None") -> "CutPropAnimationPreset | None":
    if value is None or isinstance(value, CutPropAnimationPreset):
        return value
    return CutPropAnimationPreset(str(value).strip().lower())


def _coerce_cut_type_file_strategy(value: "CutTypeFileStrategy | str | None") -> "CutTypeFileStrategy":
    if value is None:
        return CutTypeFileStrategy.AUTO
    if isinstance(value, CutTypeFileStrategy):
        return value
    return CutTypeFileStrategy(str(value).strip().lower())


def _extract_source_stem(value: Any) -> str | None:
    if value in (None, "", 0):
        return None
    stem = getattr(value, "stem", None)
    if isinstance(stem, str) and stem:
        return stem
    path_value = getattr(value, "path", None)
    if isinstance(path_value, str) and path_value:
        return Path(path_value).stem or None
    if isinstance(value, Path):
        return value.stem or None
    if isinstance(value, str):
        text = value.replace("\\", "/").strip()
        if not text:
            return None
        if "/" in text or "." in Path(text).name:
            return Path(text).stem or None
        return text
    return None


def _extract_container_stem(value: Any) -> str | None:
    if value in (None, "", 0):
        return None
    path_value = getattr(value, "path", None)
    if isinstance(path_value, str) and path_value:
        parts = path_value.replace("\\", "/").split("/")
        if len(parts) >= 2:
            return Path(parts[-2]).stem or None
    if isinstance(value, Path):
        parent_name = value.parent.name
        return Path(parent_name).stem or None
    if isinstance(value, str):
        text = value.replace("\\", "/").strip()
        parts = text.split("/")
        if len(parts) >= 2 and parts[-2]:
            return Path(parts[-2]).stem or None
    return None


def _extract_model_name(value: Any) -> str | None:
    if value in (None, "", 0):
        return None
    asset_name = getattr(value, "asset_name", None)
    if asset_name not in (None, "", 0):
        resolved = _coerce_name(asset_name)
        if resolved:
            return resolved
    name = getattr(value, "name", None)
    if name not in (None, "", 0):
        resolved = _coerce_name(name)
        if resolved:
            return resolved
    return _extract_source_stem(value)


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


class _CutStreamedModelBinding(_TypedCutBinding):
    def _get_hashed_text_field(self, field_name: str) -> str | None:
        return _coerce_name(self.fields.get(field_name))

    def _set_hashed_text_field(self, field_name: str, value: str | None) -> None:
        if value is None:
            self.fields.pop(field_name, None)
            return
        self.fields[field_name] = _hashed_string(value)

    def _get_int_field(self, field_name: str) -> int | None:
        value = self.fields.get(field_name)
        return None if value is None else int(value)

    def _set_int_field(self, field_name: str, value: int | None) -> None:
        if value is None:
            self.fields.pop(field_name, None)
            return
        self.fields[field_name] = int(value)

    @property
    def cutscene_name(self) -> str | None:
        return self._get_hashed_text_field("cName")

    @cutscene_name.setter
    def cutscene_name(self, value: str | None) -> None:
        self._set_hashed_text_field("cName", value)

    @property
    def streaming_name(self) -> str | None:
        return self._get_hashed_text_field("StreamingName")

    @streaming_name.setter
    def streaming_name(self, value: str | None) -> None:
        previous = self.streaming_name
        self._set_hashed_text_field("StreamingName", value)
        if value is not None:
            self.name = value
        elif self.name == previous:
            self.name = None

    @property
    def anim_streaming_base(self) -> int | None:
        return self._get_int_field("AnimStreamingBase")

    @anim_streaming_base.setter
    def anim_streaming_base(self, value: int | None) -> None:
        self._set_int_field("AnimStreamingBase", value)

    @property
    def anim_export_ctrl_spec_file(self) -> str | None:
        return self._get_hashed_text_field("cAnimExportCtrlSpecFile")

    @anim_export_ctrl_spec_file.setter
    def anim_export_ctrl_spec_file(self, value: str | None) -> None:
        self._set_hashed_text_field("cAnimExportCtrlSpecFile", value)

    @property
    def face_export_ctrl_spec_file(self) -> str | None:
        return self._get_hashed_text_field("cFaceExportCtrlSpecFile")

    @face_export_ctrl_spec_file.setter
    def face_export_ctrl_spec_file(self, value: str | None) -> None:
        self._set_hashed_text_field("cFaceExportCtrlSpecFile", value)

    @property
    def anim_compression_file(self) -> str | None:
        return self._get_hashed_text_field("cAnimCompressionFile")

    @anim_compression_file.setter
    def anim_compression_file(self, value: str | None) -> None:
        self._set_hashed_text_field("cAnimCompressionFile", value)

    @property
    def handle(self) -> str | None:
        return self._get_hashed_text_field("cHandle")

    @handle.setter
    def handle(self, value: str | None) -> None:
        self._set_hashed_text_field("cHandle", value)

    @property
    def type_file(self) -> str | None:
        return self._get_hashed_text_field("typeFile")

    @type_file.setter
    def type_file(self, value: str | None) -> None:
        self._set_hashed_text_field("typeFile", value)

    def configure_model_asset(
        self,
        *,
        cutscene_name: str | None = None,
        streaming_name: str | None = None,
        animation_clip_base: str | None = None,
        anim_streaming_base: int | None = None,
        anim_export_ctrl_spec_file: str | None = None,
        face_export_ctrl_spec_file: str | None = None,
        anim_compression_file: str | None = None,
        handle: str | None = None,
        type_file: str | None = None,
    ) -> "_CutStreamedModelBinding":
        if cutscene_name is not None:
            self.cutscene_name = cutscene_name
        if streaming_name is not None:
            self.streaming_name = streaming_name
        if animation_clip_base is not None:
            self.animation_clip_base = animation_clip_base
        if anim_streaming_base is not None:
            self.anim_streaming_base = anim_streaming_base
        if anim_export_ctrl_spec_file is not None:
            self.anim_export_ctrl_spec_file = anim_export_ctrl_spec_file
        if face_export_ctrl_spec_file is not None:
            self.face_export_ctrl_spec_file = face_export_ctrl_spec_file
        if anim_compression_file is not None:
            self.anim_compression_file = anim_compression_file
        if handle is not None:
            self.handle = handle
        if type_file is not None:
            self.type_file = type_file
        return self

    def configure_runtime_source(
        self,
        *,
        model: Any | None = None,
        archetype: Any | None = None,
        ytyp: Any | None = None,
        type_source: Any | None = None,
        type_file_strategy: "CutTypeFileStrategy | str | None" = None,
    ) -> "_CutStreamedModelBinding":
        strategy = _coerce_cut_type_file_strategy(type_file_strategy)
        resolved_model = model if model not in (None, "", 0) else archetype
        model_name = _extract_model_name(resolved_model)
        if model_name is not None:
            self.model_name = model_name

        if type_source in (None, "", 0):
            type_source = ytyp

        resolved_type_file: str | None = None
        if strategy is CutTypeFileStrategy.NONE:
            resolved_type_file = None
        elif strategy is CutTypeFileStrategy.YTYP:
            resolved_type_file = _extract_source_stem(type_source)
        elif strategy is CutTypeFileStrategy.CONTAINER:
            resolved_type_file = _extract_container_stem(model)
        else:
            resolved_type_file = _extract_source_stem(type_source) or _extract_container_stem(model)

        if resolved_type_file is None:
            if strategy is CutTypeFileStrategy.NONE:
                self.type_file = None
            return self

        self.type_file = resolved_type_file
        return self

    def apply_animation_preset(self, preset: "CutPropAnimationPreset | str") -> "_CutStreamedModelBinding":
        resolved = _coerce_cut_prop_animation_preset(preset)
        assert resolved is not None
        values = _CUT_PROP_ANIMATION_PRESETS[resolved]
        for field_name, value in values.items():
            if value is None:
                self.fields.pop(field_name, None)
            else:
                self.fields[field_name] = _clone_value(value)
        return self

    @property
    def scene_name(self) -> str | None:
        return self.cutscene_name

    @scene_name.setter
    def scene_name(self, value: str | None) -> None:
        self.cutscene_name = value

    @property
    def model_name(self) -> str | None:
        return self.streaming_name

    @model_name.setter
    def model_name(self, value: str | None) -> None:
        self.streaming_name = value

    @property
    def animation_streaming_base(self) -> int | None:
        return self.anim_streaming_base

    @animation_streaming_base.setter
    def animation_streaming_base(self, value: int | None) -> None:
        self.anim_streaming_base = value

    @property
    def animation_clip_base(self) -> str | None:
        value = self.metadata.get("animation_clip_base")
        if isinstance(value, str) and value:
            return value
        return self.model_name

    @animation_clip_base.setter
    def animation_clip_base(self, value: str | None) -> None:
        if value in (None, ""):
            self.metadata.pop("animation_clip_base", None)
            return
        base = str(value)
        self.metadata["animation_clip_base"] = base
        self.anim_streaming_base = jenk_partial_hash(base)

    @property
    def animation_export_spec_file(self) -> str | None:
        return self.anim_export_ctrl_spec_file

    @animation_export_spec_file.setter
    def animation_export_spec_file(self, value: str | None) -> None:
        self.anim_export_ctrl_spec_file = value

    @property
    def face_animation_export_spec_file(self) -> str | None:
        return self.face_export_ctrl_spec_file

    @face_animation_export_spec_file.setter
    def face_animation_export_spec_file(self, value: str | None) -> None:
        self.face_export_ctrl_spec_file = value

    @property
    def animation_compression_filename(self) -> str | None:
        return self.anim_compression_file

    @animation_compression_filename.setter
    def animation_compression_filename(self, value: str | None) -> None:
        self.anim_compression_file = value

    @property
    def object_handle(self) -> str | None:
        return self.handle

    @object_handle.setter
    def object_handle(self, value: str | None) -> None:
        self.handle = value

    @property
    def ytyp_name(self) -> str | None:
        return self.type_file

    @ytyp_name.setter
    def ytyp_name(self, value: str | None) -> None:
        self.type_file = value


class CutAssetManager(_TypedCutBinding):
    TYPE_NAME = "rage__cutfAssetManagerObject"
    ROLE = "asset_manager"


class CutAnimationManager(_TypedCutBinding):
    TYPE_NAME = "rage__cutfAnimationManagerObject"
    ROLE = "animation_manager"


class CutCamera(_TypedCutBinding):
    TYPE_NAME = "rage__cutfCameraObject"
    ROLE = "camera"


class CutPed(_CutStreamedModelBinding):
    TYPE_NAME = "rage__cutfPedModelObject"
    ROLE = "ped"


class CutProp(_CutStreamedModelBinding):
    TYPE_NAME = "rage__cutfPropModelObject"
    ROLE = "prop"

    @classmethod
    def from_runtime_asset(
        cls,
        *,
        name: str | None = None,
        object_id: int = -1,
        fields: dict[str, Any] | None = None,
        model: Any | None = None,
        archetype: Any | None = None,
        ytyp: Any | None = None,
        type_source: Any | None = None,
        type_file_strategy: "CutTypeFileStrategy | str | None" = None,
    ) -> "CutProp":
        binding = cls(name=name, object_id=object_id, fields=fields)
        binding.configure_runtime_source(
            model=model,
            archetype=archetype,
            ytyp=ytyp,
            type_source=type_source,
            type_file_strategy=type_file_strategy,
        )
        return binding


class CutVehicle(_CutStreamedModelBinding):
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


class CutDecal(_TypedCutBinding):
    TYPE_NAME = "rage__cutfDecalObject"
    ROLE = "decal"


class CutHiddenObject(_TypedCutBinding):
    TYPE_NAME = "rage__cutfHiddenModelObject"
    ROLE = "hidden_object"


class CutFixupObject(_TypedCutBinding):
    TYPE_NAME = "rage__cutfFixupModelObject"
    ROLE = "fixup_object"


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
    CutDecal.TYPE_NAME: CutDecal,
    CutHiddenObject.TYPE_NAME: CutHiddenObject,
    CutFixupObject.TYPE_NAME: CutFixupObject,
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
    "decal": "decals",
    "particle_fx": "particle_effects",
    "blocking_bounds": "blocking_bounds",
    "fixup_object": "fixup_objects",
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
    "overlay": CutOverlay,
    "decal": CutDecal,
}


def _binding_from_node(node: CutNode) -> CutBinding:
    fields = {key: _clone_value(value) for key, value in node.fields.items() if key != "iObjectId"}
    if node.type_name in {
        CutPed.TYPE_NAME,
        CutProp.TYPE_NAME,
        CutVehicle.TYPE_NAME,
    }:
        name = _coerce_name(node.fields.get("StreamingName")) or _coerce_name(node.fields.get("cName"))
    else:
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
