from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Self

from ...common import hash_value
from ...hashing import jenk_partial_hash
from ...vector import Vector3
from ..model import CutHashedString, CutNode
from .shared import (
    _clone_value,
    _coerce_name,
    _hashed_string,
    _node_type_hash,
    _object_name_field,
    _object_role,
    _parse_hex_hash,
)


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
    ) -> CutBinding:
        role_name = role or _object_role(type_name)
        field_values = dict(fields or {})
        name_field = _object_name_field(type_name)
        if name is not None and name_field not in field_values:
            if type_name == "rage__cutfAudioObject":
                field_values[name_field] = name
            else:
                field_values[name_field] = _hashed_string(name)
        raw = CutNode(
            type_name=type_name, type_hash=_node_type_hash(type_name), fields={}
        )
        return cls(
            object_id=object_id,
            type_name=type_name,
            role=role_name,
            name=name,
            fields=field_values,
            raw=raw,
        )

    def to_node(self) -> CutNode:
        node = (
            _clone_value(self.raw)
            if self.raw is not None
            else CutNode(type_name=self.type_name)
        )
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
                    node.fields[field_name] = CutHashedString(
                        hash=current.hash
                        if isinstance(current, CutHashedString) and current.hash
                        else hash_value(self.name),
                        text=self.name,
                    )
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


class CutFacialAnimationMode(Enum):
    NONE = "none"
    MERGED = "merged"
    OVERRIDE_MERGED = "override_merged"


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


def _coerce_cut_prop_animation_preset(
    value: CutPropAnimationPreset | str | None,
) -> CutPropAnimationPreset | None:
    if value is None or isinstance(value, CutPropAnimationPreset):
        return value
    return CutPropAnimationPreset(str(value).strip().lower())


def _coerce_cut_type_file_strategy(
    value: CutTypeFileStrategy | str | None,
) -> CutTypeFileStrategy:
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
                field_values[name_field] = (
                    name
                    if type_name == "rage__cutfAudioObject"
                    else _hashed_string(name)
                )
        super().__init__(
            object_id=object_id,
            type_name=type_name,
            role=role,
            name=name,
            fields=field_values,
            raw=raw
            if raw is not None
            else CutNode(
                type_name=type_name, type_hash=_node_type_hash(type_name), fields={}
            ),
        )

    def _get_hashed_text_field(self, field_name: str) -> str | None:
        return _coerce_name(self.fields.get(field_name))

    def _set_hashed_text_field(self, field_name: str, value: str | None) -> None:
        if value is None:
            self.fields.pop(field_name, None)
        else:
            self.fields[field_name] = _hashed_string(value)

    def _get_int_field(self, field_name: str) -> int | None:
        value = self.fields.get(field_name)
        return None if value is None else int(value)

    def _set_int_field(self, field_name: str, value: int | None) -> None:
        if value is None:
            self.fields.pop(field_name, None)
        else:
            self.fields[field_name] = int(value)

    def _get_float_field(self, field_name: str) -> float | None:
        value = self.fields.get(field_name)
        return None if value is None else float(value)

    def _set_float_field(self, field_name: str, value: float | None) -> None:
        if value is None:
            self.fields.pop(field_name, None)
        else:
            self.fields[field_name] = float(value)


class _CutNamedStreamedBinding(_TypedCutBinding):
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


class _CutNamedAnimatedStreamedBinding(_CutNamedStreamedBinding):
    @property
    def anim_streaming_base(self) -> int | None:
        return self._get_int_field("AnimStreamingBase")

    @anim_streaming_base.setter
    def anim_streaming_base(self, value: int | None) -> None:
        self._set_int_field("AnimStreamingBase", value)


class _CutStreamedModelBinding(_CutNamedAnimatedStreamedBinding):
    @property
    def type_file_strategy(self) -> CutTypeFileStrategy:
        value = self.metadata.get("type_file_strategy", CutTypeFileStrategy.AUTO)
        return _coerce_cut_type_file_strategy(value)

    @type_file_strategy.setter
    def type_file_strategy(self, value: CutTypeFileStrategy | str) -> None:
        self.metadata["type_file_strategy"] = _coerce_cut_type_file_strategy(value)

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
        value = self.fields.get("typeFile")
        if isinstance(value, CutHashedString) and value.hash == 0:
            return None
        return _coerce_name(value)

    @type_file.setter
    def type_file(self, value: str | None) -> None:
        self._set_hashed_text_field("typeFile", value)
        if (
            value is not None
            and self.type_file_strategy is CutTypeFileStrategy.NONE
        ):
            self.type_file_strategy = CutTypeFileStrategy.AUTO

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
        type_file_strategy: CutTypeFileStrategy | str | None = None,
    ) -> Self:
        binding = cls(name=name, object_id=object_id, fields=fields)
        binding.configure_runtime_source(
            model=model,
            archetype=archetype,
            ytyp=ytyp,
            type_source=type_source,
            type_file_strategy=type_file_strategy,
        )
        return binding

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
    ) -> _CutStreamedModelBinding:
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
        type_file_strategy: CutTypeFileStrategy | str | None = None,
    ) -> _CutStreamedModelBinding:
        strategy = _coerce_cut_type_file_strategy(type_file_strategy)
        self.type_file_strategy = strategy
        resolved_model = model if model not in (None, "", 0) else archetype
        model_name = _extract_model_name(resolved_model)
        if model_name is not None:
            self.model_name = model_name

        if type_source in (None, "", 0):
            type_source = ytyp

        resolved_type_file: str | None = None
        match strategy:
            case CutTypeFileStrategy.NONE:
                resolved_type_file = None
            case CutTypeFileStrategy.YTYP:
                resolved_type_file = _extract_source_stem(type_source)
            case CutTypeFileStrategy.CONTAINER:
                resolved_type_file = _extract_container_stem(model)
            case _:
                resolved_type_file = _extract_source_stem(
                    type_source
                ) or _extract_container_stem(model)

        if resolved_type_file is None:
            if strategy is CutTypeFileStrategy.NONE:
                self.type_file = None
            return self

        self.type_file = resolved_type_file
        return self

    def apply_animation_preset(
        self, preset: CutPropAnimationPreset | str
    ) -> _CutStreamedModelBinding:
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
        model_name = self.model_name
        if not model_name or _parse_hex_hash(model_name) is not None:
            return None
        streaming_base = self.anim_streaming_base
        if streaming_base not in (None, 0) and streaming_base != jenk_partial_hash(
            model_name
        ):
            return None
        return model_name

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

    @property
    def animation_streaming_base(self) -> int | None:
        return self._get_int_field("AnimStreamingBase")

    @animation_streaming_base.setter
    def animation_streaming_base(self, value: int | None) -> None:
        self._set_int_field("AnimStreamingBase", value)

    @property
    def near_draw_distance(self) -> float | None:
        return self._get_float_field("fNearDrawDistance")

    @near_draw_distance.setter
    def near_draw_distance(self, value: float | None) -> None:
        self._set_float_field("fNearDrawDistance", value)

    @property
    def far_draw_distance(self) -> float | None:
        return self._get_float_field("fFarDrawDistance")

    @far_draw_distance.setter
    def far_draw_distance(self, value: float | None) -> None:
        self._set_float_field("fFarDrawDistance", value)


class CutPed(_CutStreamedModelBinding):
    TYPE_NAME = "rage__cutfPedModelObject"
    ROLE = "ped"

    @property
    def found_face_animation(self) -> bool:
        return bool(self.fields.get("bFoundFaceAnimation", False))

    @found_face_animation.setter
    def found_face_animation(self, value: bool) -> None:
        self.fields["bFoundFaceAnimation"] = bool(value)

    @property
    def face_and_body_are_merged(self) -> bool:
        return bool(self.fields.get("bFaceAndBodyAreMerged", False))

    @face_and_body_are_merged.setter
    def face_and_body_are_merged(self, value: bool) -> None:
        self.fields["bFaceAndBodyAreMerged"] = bool(value)

    @property
    def override_face_animation(self) -> bool:
        return bool(self.fields.get("bOverrideFaceAnimation", False))

    @override_face_animation.setter
    def override_face_animation(self, value: bool) -> None:
        self.fields["bOverrideFaceAnimation"] = bool(value)

    @property
    def override_face_animation_filename(self) -> str | None:
        return self._get_hashed_text_field("overrideFaceAnimationFilename")

    @override_face_animation_filename.setter
    def override_face_animation_filename(self, value: str | None) -> None:
        self._set_hashed_text_field("overrideFaceAnimationFilename", value)

    @property
    def face_animation_node_name(self) -> str | None:
        return self._get_hashed_text_field("faceAnimationNodeName")

    @face_animation_node_name.setter
    def face_animation_node_name(self, value: str | None) -> None:
        self._set_hashed_text_field("faceAnimationNodeName", value)

    @property
    def face_attributes_filename(self) -> str | None:
        return self._get_hashed_text_field("faceAttributesFilename")

    @face_attributes_filename.setter
    def face_attributes_filename(self, value: str | None) -> None:
        self._set_hashed_text_field("faceAttributesFilename", value)

    @property
    def has_face_animation(self) -> bool:
        return self.found_face_animation or (
            self.override_face_animation
            and bool(self.override_face_animation_filename)
        )

    @property
    def facial_animation_mode(self) -> CutFacialAnimationMode | None:
        if not self.has_face_animation and not self.face_and_body_are_merged:
            return CutFacialAnimationMode.NONE
        if not self.face_and_body_are_merged:
            return None
        if self.override_face_animation:
            return CutFacialAnimationMode.OVERRIDE_MERGED
        return CutFacialAnimationMode.MERGED

    @property
    def runtime_animation_clip_base(self) -> str | None:
        base = self.animation_clip_base
        if base and self.has_face_animation and self.face_and_body_are_merged:
            return base if base.endswith("_dual") else f"{base}_dual"
        return base

    def configure_facial_animation(
        self,
        mode: CutFacialAnimationMode | str,
        *,
        override_filename: str | None = None,
        node_name: str | None = None,
        attributes_filename: str | None = None,
    ) -> CutPed:
        resolved = (
            mode
            if isinstance(mode, CutFacialAnimationMode)
            else CutFacialAnimationMode(str(mode).strip().lower())
        )
        self.face_animation_node_name = node_name
        self.face_attributes_filename = attributes_filename
        if resolved is CutFacialAnimationMode.NONE:
            self.found_face_animation = False
            self.face_and_body_are_merged = False
            self.override_face_animation = False
            self.override_face_animation_filename = None
        elif resolved is CutFacialAnimationMode.MERGED:
            self.found_face_animation = True
            self.face_and_body_are_merged = True
            self.override_face_animation = False
            self.override_face_animation_filename = None
        else:
            if not override_filename:
                raise ValueError(
                    "override_filename is required for override_merged facial animation"
                )
            self.found_face_animation = False
            self.face_and_body_are_merged = True
            self.override_face_animation = True
            self.override_face_animation_filename = override_filename
        return self


class CutProp(_CutStreamedModelBinding):
    TYPE_NAME = "rage__cutfPropModelObject"
    ROLE = "prop"


class CutVehicle(_CutStreamedModelBinding):
    TYPE_NAME = "rage__cutfVehicleModelObject"
    ROLE = "vehicle"


class CutWeapon(_CutStreamedModelBinding):
    TYPE_NAME = "rage__cutfWeaponModelObject"
    ROLE = "weapon"

    @property
    def generic_weapon_type(self) -> int | None:
        return self._get_int_field("GenericWeaponType")

    @generic_weapon_type.setter
    def generic_weapon_type(self, value: int | None) -> None:
        self._set_int_field("GenericWeaponType", value)


class CutLight(_TypedCutBinding):
    TYPE_NAME = "rage__cutfLightObject"
    ROLE = "light"


class CutAnimatedLight(CutLight):
    TYPE_NAME = "rage__cutfAnimatedLightObject"

    @property
    def anim_streaming_base(self) -> int | None:
        return self._get_int_field("AnimStreamingBase")

    @anim_streaming_base.setter
    def anim_streaming_base(self, value: int | None) -> None:
        self._set_int_field("AnimStreamingBase", value)


class CutParticleEffect(_CutNamedStreamedBinding):
    TYPE_NAME = "rage__cutfParticleEffectObject"
    ROLE = "particle_fx"

    @property
    def effect_list(self) -> str | None:
        return self._get_hashed_text_field("athFxListHash")

    @effect_list.setter
    def effect_list(self, value: str | None) -> None:
        self._set_hashed_text_field("athFxListHash", value)


class CutAnimatedParticleEffect(_CutNamedAnimatedStreamedBinding):
    TYPE_NAME = "rage__cutfAnimatedParticleEffectObject"
    ROLE = "particle_fx"

    @property
    def effect_list(self) -> str | None:
        return self._get_hashed_text_field("athFxListHash")

    @effect_list.setter
    def effect_list(self, value: str | None) -> None:
        self._set_hashed_text_field("athFxListHash", value)


class CutAudio(_TypedCutBinding):
    TYPE_NAME = "rage__cutfAudioObject"
    ROLE = "audio"

    @property
    def offset(self) -> float:
        return self._get_float_field("fOffset") or 0.0

    @offset.setter
    def offset(self, value: float) -> None:
        self._set_float_field("fOffset", value)


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

    @property
    def corners(self) -> tuple[Vector3, ...]:
        return tuple(self.fields.get("vCorners", ()))

    @corners.setter
    def corners(self, value: tuple[Vector3, Vector3, Vector3, Vector3]) -> None:
        if not all(isinstance(corner, Vector3) for corner in value):
            raise TypeError("blocking bounds corners must be Vector3 instances")
        self.fields["vCorners"] = list(value)

    @property
    def height(self) -> float:
        return float(self.fields.get("fHeight", 0.0))

    @height.setter
    def height(self, value: float) -> None:
        self.fields["fHeight"] = float(value)


class CutRemovalBounds(CutBlockingBounds):
    TYPE_NAME = "rage__cutfRemovalBoundsObject"
    ROLE = "removal_bounds"


class CutRayfire(_CutNamedStreamedBinding):
    TYPE_NAME = "rage__cutfRayfireObject"
    ROLE = "rayfire"

    @property
    def start_position(self) -> Vector3:
        value = self.fields.get("vStartPosition", Vector3())
        if not isinstance(value, Vector3):
            raise TypeError("rayfire vStartPosition must be a Vector3")
        return value

    @start_position.setter
    def start_position(self, value: Vector3) -> None:
        if not isinstance(value, Vector3):
            raise TypeError("rayfire start_position must be a Vector3")
        self.fields["vStartPosition"] = value


class CutEventObject(_TypedCutBinding):
    TYPE_NAME = "rage__cutfEventObject"
    ROLE = "event_object"


_BINDING_CLASS_BY_TYPE = {
    CutAssetManager.TYPE_NAME: CutAssetManager,
    CutAnimationManager.TYPE_NAME: CutAnimationManager,
    CutCamera.TYPE_NAME: CutCamera,
    CutPed.TYPE_NAME: CutPed,
    CutProp.TYPE_NAME: CutProp,
    CutVehicle.TYPE_NAME: CutVehicle,
    CutWeapon.TYPE_NAME: CutWeapon,
    CutLight.TYPE_NAME: CutLight,
    CutAnimatedLight.TYPE_NAME: CutAnimatedLight,
    CutParticleEffect.TYPE_NAME: CutParticleEffect,
    CutAnimatedParticleEffect.TYPE_NAME: CutAnimatedParticleEffect,
    CutAudio.TYPE_NAME: CutAudio,
    CutSubtitle.TYPE_NAME: CutSubtitle,
    CutFade.TYPE_NAME: CutFade,
    CutOverlay.TYPE_NAME: CutOverlay,
    CutDecal.TYPE_NAME: CutDecal,
    CutHiddenObject.TYPE_NAME: CutHiddenObject,
    CutFixupObject.TYPE_NAME: CutFixupObject,
    CutBlockingBounds.TYPE_NAME: CutBlockingBounds,
    CutRemovalBounds.TYPE_NAME: CutRemovalBounds,
    CutRayfire.TYPE_NAME: CutRayfire,
    CutEventObject.TYPE_NAME: CutEventObject,
}

_ROLE_PROPERTY_NAMES = {
    "camera": "cameras",
    "ped": "peds",
    "prop": "props",
    "vehicle": "vehicles",
    "weapon": "weapons",
    "light": "lights",
    "audio": "audio",
    "subtitle": "subtitles",
    "fade": "fades",
    "overlay": "overlays",
    "decal": "decals",
    "particle_fx": "particle_effects",
    "blocking_bounds": "blocking_bounds",
    "removal_bounds": "removal_bounds",
    "rayfire": "rayfires",
    "event_object": "event_objects",
    "fixup_object": "fixup_objects",
    "animation_manager": "animation_managers",
    "asset_manager": "asset_managers",
}

_BINDING_ADDERS = {
    "asset_manager": CutAssetManager,
    "animation_manager": CutAnimationManager,
    "ped": CutPed,
    "prop": CutProp,
    "vehicle": CutVehicle,
    "weapon": CutWeapon,
    "light": CutLight,
    "audio": CutAudio,
    "subtitle": CutSubtitle,
    "fade": CutFade,
    "overlay": CutOverlay,
    "decal": CutDecal,
    "rayfire": CutRayfire,
    "event_object": CutEventObject,
}


def _binding_from_node(node: CutNode) -> CutBinding:
    raw = _clone_value(node)
    fields = {
        key: value
        for key, value in raw.fields.items()
        if key != "iObjectId"
    }
    if node.type_name in {
        CutPed.TYPE_NAME,
        CutProp.TYPE_NAME,
        CutVehicle.TYPE_NAME,
        CutWeapon.TYPE_NAME,
        CutParticleEffect.TYPE_NAME,
        CutAnimatedParticleEffect.TYPE_NAME,
        CutRayfire.TYPE_NAME,
    }:
        name = _coerce_name(node.fields.get("StreamingName")) or _coerce_name(
            node.fields.get("cName")
        )
    else:
        name = _coerce_name(node.fields.get("cName")) or _coerce_name(
            node.fields.get("StreamingName")
        )
    binding_class = _BINDING_CLASS_BY_TYPE.get(node.type_name)
    if binding_class is not None:
        binding = binding_class(
            name=name,
            object_id=int(node.fields.get("iObjectId", -1)),
            fields=fields,
            raw=raw,
        )
        if isinstance(binding, CutVehicle) and binding.type_file is None:
            binding.type_file_strategy = CutTypeFileStrategy.NONE
        return binding
    return CutBinding(
        object_id=int(node.fields.get("iObjectId", -1)),
        type_name=node.type_name,
        role=_object_role(node.type_name),
        name=name,
        fields=fields,
        raw=raw,
    )
