from __future__ import annotations

import math
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..colors import parse_css_argb, parse_css_rgb_unit
from ..resolver import HashResolver, get_hash_resolver
from .flags import CutSceneFlags, DEFAULT_PLAYABLE_CUTSCENE_FLAGS
from .lights import CutLightFlag, CutLightProperty, CutLightType
from .model import CutFile, CutHashedString, CutNode
from .payloads import (
    CutCameraCutPayload,
    CutLoadScenePayload,
    CutScreenFadePayload,
    CutSubtitlePayload,
)
from .scene import (
    CutBinding,
    CutLight,
    CutPed,
    CutPropAnimationPreset,
    CutScene,
    CutVehicle,
    read_cut_scene,
)


class CutScriptError(ValueError):
    def __init__(self, line: int, message: str, *, code: str = "syntax") -> None:
        self.line = int(line)
        self.code = code
        super().__init__(f"Line {self.line}: {message}")


@dataclass(slots=True)
class CutScriptResult:
    scene: CutScene
    save_path: Path | None = None


CutScriptHashResolver = HashResolver | Mapping[int, str]


@dataclass(slots=True)
class _PendingCameraCut:
    line: int
    time: float
    camera: CutBinding
    name: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_quaternion: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    near_draw_distance: float = 0.05
    far_draw_distance: float = 1000.0
    map_lod_scale: float = 0.0


_ROOT_COMMANDS = {
    "CUTSCENE",
    "DURATION",
    "OFFSET",
    "ROTATION",
    "FLAGS",
    "ASSETS",
    "TRACK",
    "SAVE",
}
_MODEL_PROPERTY_COMMANDS = {
    "MODEL",
    "YTYP",
    "TYPE_FILE",
    "ANIM_BASE",
    "ANIM_STREAMING_BASE",
    "ANIM_EXPORT",
    "FACE_EXPORT",
    "CNAME",
    "PRESET",
}
_STREAMED_MODEL_COMMANDS = {
    "PROP",
    "STATIC_PROP",
    "ANIMATED_PROP",
    "PED",
    "ANIMATED_PED",
    "VEHICLE",
    "ANIMATED_VEHICLE",
}
_CAMERA_CUT_PROPERTY_COMMANDS = {
    "NAME",
    "POSITION",
    "POS",
    "ROTATION",
    "ROT",
    "QUAT",
    "NEAR",
    "FAR",
    "MAP_LOD",
}
_LIGHT_PROPERTY_COMMANDS = {
    "TYPE",
    "POSITION",
    "POS",
    "DIRECTION",
    "DIR",
    "COLOR",
    "COLOUR",
    "INTENSITY",
    "FALLOFF",
    "CONE",
    "INNER_CONE",
    "CORONA",
    "FLAGS",
    "PROPERTY",
    "STATIC",
}


def _strip_line_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#" and _looks_like_css_hex_color(line[index:]):
            continue
        if char in {"#", ";"}:
            return line[:index]
        if char == "/" and index + 1 < len(line) and line[index + 1] == "/":
            return line[:index]
    return line


def _looks_like_css_hex_color(value: str) -> bool:
    digits = ""
    for char in value[1:]:
        if char.isalnum():
            digits += char
            continue
        break
    return len(digits) in {3, 4, 6, 8} and all(
        char in "0123456789abcdefABCDEF" for char in digits
    )


def _tokenize(line: str, line_no: int) -> list[str]:
    lexer = shlex.shlex(_strip_line_comment(line), posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as exc:
        raise CutScriptError(line_no, str(exc)) from exc


def _block_name(value: str, line_no: int, label: str) -> str:
    name = value[:-1] if value.endswith(":") else value
    if not name:
        raise CutScriptError(line_no, f"{label} name cannot be empty")
    return name


def _expect_count(tokens: list[str], line_no: int, count: int, usage: str) -> None:
    if len(tokens) < count:
        raise CutScriptError(line_no, f"expected {usage}")


def _float(value: str, line_no: int, name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise CutScriptError(
            line_no, f"{name} must be a number, got {value!r}"
        ) from exc


def _is_float_token(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _int(value: str, line_no: int, name: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise CutScriptError(
            line_no, f"{name} must be an integer, got {value!r}"
        ) from exc


def _vec(tokens: list[str], line_no: int, name: str, size: int) -> tuple[float, ...]:
    if len(tokens) < size:
        raise CutScriptError(line_no, f"{name} expects {size} numeric values")
    return tuple(
        _float(tokens[index], line_no, f"{name}[{index}]") for index in range(size)
    )


def _css_rgb(tokens: list[str], line_no: int, name: str) -> tuple[float, float, float]:
    if len(tokens) == 1 or (
        tokens
        and (
            tokens[0].startswith("#") or "(" in " ".join(tokens) or tokens[0].isalpha()
        )
    ):
        try:
            return parse_css_rgb_unit(" ".join(tokens))
        except ValueError as exc:
            raise CutScriptError(
                line_no, f"{name} must be a CSS color, got {' '.join(tokens)!r}"
            ) from exc
    return _vec(tokens, line_no, name, 3)  # type: ignore[return-value]


def _css_argb(tokens: list[str], line_no: int, name: str) -> int:
    try:
        return parse_css_argb(" ".join(tokens))
    except ValueError as exc:
        raise CutScriptError(
            line_no, f"{name} must be a CSS color, got {' '.join(tokens)!r}"
        ) from exc


def _euler_xyz_degrees_to_quaternion(
    x_degrees: float, y_degrees: float, z_degrees: float
) -> tuple[float, float, float, float]:
    x = math.radians(x_degrees) * 0.5
    y = math.radians(y_degrees) * 0.5
    z = math.radians(z_degrees) * 0.5
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    return (
        (sx * cy * cz) + (cx * sy * sz),
        (cx * sy * cz) - (sx * cy * sz),
        (cx * cy * sz) + (sx * sy * cz),
        (cx * cy * cz) - (sx * sy * sz),
    )


def _option_value(tokens: list[str], index: int, line_no: int, option: str) -> str:
    if index + 1 >= len(tokens):
        raise CutScriptError(line_no, f"{option} expects a value")
    return tokens[index + 1]


def _enum_value(enum_cls: Any, value: str, line_no: int, label: str) -> Any:
    normalized = value.strip()
    try:
        return enum_cls[normalized.upper()]
    except KeyError:
        try:
            return enum_cls(normalized.lower())
        except ValueError as exc:
            raise CutScriptError(line_no, f"unknown {label} {value!r}") from exc


def _names(tokens: Iterable[str]) -> list[str]:
    result: list[str] = []
    for token in tokens:
        for value in token.split(","):
            value = value.strip()
            if value:
                result.append(value)
    return result


def _flag_value(tokens: list[str], line_no: int) -> CutSceneFlags:
    flags = CutSceneFlags.NONE
    for token in tokens:
        name = token.upper()
        if name.startswith("0X") or name.isdecimal():
            flags |= CutSceneFlags(_int(token, line_no, "cutscene flag"))
            continue
        if name == "PLAYABLE":
            flags |= DEFAULT_PLAYABLE_CUTSCENE_FLAGS
            continue
        if name == "SECTIONED":
            flags |= CutSceneFlags.IS_SECTIONED
            continue
        if name == "STORY_MODE":
            flags |= CutSceneFlags.USE_STORY_MODE
            continue
        try:
            flags |= CutSceneFlags[name]
        except KeyError as exc:
            raise CutScriptError(line_no, f"unknown cutscene flag {token!r}") from exc
    return flags


def _light_flags(tokens: list[str], line_no: int) -> CutLightFlag:
    flags = CutLightFlag.NONE
    for token in tokens:
        if token.upper().startswith("0X") or token.isdecimal():
            flags |= CutLightFlag(_int(token, line_no, "cut light flag"))
            continue
        try:
            flags |= CutLightFlag[token.upper()]
        except KeyError as exc:
            raise CutScriptError(line_no, f"unknown cut light flag {token!r}") from exc
    return flags


class _CutScriptParser:
    def __init__(self, text: str, *, base_path: str | Path | None = None) -> None:
        self.lines = text.splitlines()
        self.base_path = Path(base_path) if base_path is not None else None
        self.scene: CutScene | None = None
        self.save_path: Path | None = None
        self.section: str = "ROOT"
        self.track: str | None = None
        self.bindings: dict[str, CutBinding] = {}
        self.last_asset: CutBinding | None = None
        self.pending_camera_cut: _PendingCameraCut | None = None

    def parse(self) -> CutScriptResult:
        for line_no, raw_line in enumerate(self.lines, start=1):
            tokens = _tokenize(raw_line, line_no)
            if not tokens:
                continue
            command = tokens[0].upper()
            if command == "END":
                self._parse_end(tokens, line_no)
                continue
            if self.section == "ASSETS":
                if (
                    command in _MODEL_PROPERTY_COMMANDS
                    or command in _LIGHT_PROPERTY_COMMANDS
                ):
                    self._parse_asset(tokens, line_no)
                    continue
                if command in _ROOT_COMMANDS:
                    raise CutScriptError(
                        line_no,
                        f"ASSETS section must be closed with END before {command}",
                        code="section.end.missing",
                    )
                self._parse_asset(tokens, line_no)
                continue
            if self.section == "TRACK":
                if command in _ROOT_COMMANDS:
                    track = self.track or "TRACK"
                    raise CutScriptError(
                        line_no,
                        f"TRACK {track} section must be closed with END before {command}",
                        code="section.end.missing",
                    )
                self._parse_track(tokens, line_no)
                continue
            if command in _ROOT_COMMANDS:
                self._parse_root(tokens, line_no)
                continue
            raise CutScriptError(line_no, f"unexpected command {tokens[0]!r}")
        if self.scene is None:
            raise CutScriptError(
                1, "script must start with CUTSCENE", code="cutscene.missing"
            )
        if self.section != "ROOT":
            section = (
                f"TRACK {self.track}"
                if self.section == "TRACK" and self.track
                else self.section
            )
            raise CutScriptError(
                len(self.lines) or 1,
                f"{section} section missing END",
                code="section.end.missing",
            )
        self.scene.build()
        return CutScriptResult(scene=self.scene, save_path=self.save_path)

    def _parse_end(self, tokens: list[str], line_no: int) -> None:
        if len(tokens) != 1:
            raise CutScriptError(line_no, "END does not take arguments")
        if self.section == "ROOT":
            raise CutScriptError(
                line_no,
                "END without an open ASSETS or TRACK section",
                code="section.end.unexpected",
            )
        self._flush_pending_event(line_no)
        self.section = "ROOT"
        self.track = None
        self.last_asset = None

    def _flush_pending_event(self, line_no: int) -> None:
        pending = self.pending_camera_cut
        if pending is None:
            return
        self.pending_camera_cut = None
        self._require_scene(line_no).camera_cut(
            pending.time,
            pending.camera,
            CutCameraCutPayload(
                pending.name,
                position=pending.position,
                rotation_quaternion=pending.rotation_quaternion,
                near_draw_distance=pending.near_draw_distance,
                far_draw_distance=pending.far_draw_distance,
                map_lod_scale=pending.map_lod_scale,
            ),
        )

    def _require_scene(self, line_no: int) -> CutScene:
        if self.scene is None:
            raise CutScriptError(
                line_no,
                "CUTSCENE must be declared before this command",
                code="cutscene.missing",
            )
        return self.scene

    def _binding(self, name: str, line_no: int) -> CutBinding:
        binding = self.bindings.get(name)
        if binding is None:
            raise CutScriptError(
                line_no, f"unknown asset {name!r}", code="asset.unknown"
            )
        return binding

    def _bindings(self, tokens: Iterable[str], line_no: int) -> list[CutBinding]:
        return [self._binding(name, line_no) for name in _names(tokens)]

    def _asset_manager(self, line_no: int) -> CutBinding:
        for binding in self.bindings.values():
            if binding.role == "asset_manager":
                return binding
        scene = self._require_scene(line_no)
        binding = scene.add_asset_manager("assets")
        self.bindings["assets"] = binding
        return binding

    def _animation_manager(self, line_no: int) -> CutBinding:
        for binding in self.bindings.values():
            if binding.role == "animation_manager":
                return binding
        scene = self._require_scene(line_no)
        binding = scene.add_animation_manager("anims")
        self.bindings["anims"] = binding
        return binding

    def _audio(self, line_no: int) -> CutBinding:
        for binding in self.bindings.values():
            if binding.role == "audio":
                return binding
        scene = self._require_scene(line_no)
        binding = scene.add_audio("audio")
        self.bindings["audio"] = binding
        return binding

    def _subtitle(self, line_no: int) -> CutBinding:
        for binding in self.bindings.values():
            if binding.role == "subtitle":
                return binding
        scene = self._require_scene(line_no)
        binding = scene.add_subtitle("subtitles")
        self.bindings["subtitles"] = binding
        return binding

    def _fade_binding(self, line_no: int) -> CutBinding:
        for binding in self.bindings.values():
            if binding.role == "fade":
                return binding
        scene = self._require_scene(line_no)
        binding = scene.add_fade("fade")
        self.bindings["fade"] = binding
        return binding

    def _parse_root(self, tokens: list[str], line_no: int) -> None:
        command = tokens[0].upper()
        if command == "CUTSCENE":
            _expect_count(tokens, line_no, 2, 'CUTSCENE "name"')
            self.scene = CutScene.create(scene_name=tokens[1])
            return
        scene = self._require_scene(line_no)
        if command == "DURATION":
            _expect_count(tokens, line_no, 2, "DURATION seconds")
            scene.duration = _float(tokens[1], line_no, "duration")
        elif command == "OFFSET":
            _expect_count(tokens, line_no, 4, "OFFSET x y z")
            scene.offset = _vec(tokens[1:], line_no, "offset", 3)  # type: ignore[assignment]
        elif command == "ROTATION":
            _expect_count(tokens, line_no, 2, "ROTATION degrees")
            scene.rotation = _float(tokens[1], line_no, "rotation")
        elif command == "FLAGS":
            scene.cutscene_flags = _flag_value(tokens[1:], line_no)
        elif command == "ASSETS":
            self.section = "ASSETS"
            self.track = None
            self.last_asset = None
        elif command == "TRACK":
            _expect_count(tokens, line_no, 2, "TRACK name")
            self.section = "TRACK"
            self.track = tokens[1].upper()
            self.last_asset = None
        elif command == "SAVE":
            _expect_count(tokens, line_no, 2, 'SAVE "path.cut"')
            path = Path(tokens[1])
            self.save_path = (
                path
                if self.base_path is None or path.is_absolute()
                else self.base_path / path
            )

    def _parse_asset(self, tokens: list[str], line_no: int) -> None:
        command = tokens[0].upper()
        scene = self._require_scene(line_no)
        if command in _MODEL_PROPERTY_COMMANDS:
            if self.last_asset is None or self.last_asset.role not in {
                "prop",
                "ped",
                "vehicle",
            }:
                raise CutScriptError(
                    line_no, f"{command} must follow a PROP, PED or VEHICLE declaration"
                )
            self._apply_model_property(self.last_asset, tokens, line_no)
            return
        if command in _LIGHT_PROPERTY_COMMANDS:
            if not isinstance(self.last_asset, CutLight):
                raise CutScriptError(
                    line_no, f"{command} must follow a LIGHT declaration"
                )
            self._apply_light_property(self.last_asset, tokens, line_no)
            return
        self.last_asset = None
        if command == "ASSET_MANAGER":
            _expect_count(tokens, line_no, 2, "ASSET_MANAGER name")
            name = _block_name(tokens[1], line_no, "asset manager")
            self._register(name, scene.add_asset_manager(name), line_no)
        elif command == "ANIM_MANAGER":
            _expect_count(tokens, line_no, 2, "ANIM_MANAGER name")
            name = _block_name(tokens[1], line_no, "animation manager")
            self._register(name, scene.add_animation_manager(name), line_no)
        elif command == "CAMERA":
            _expect_count(tokens, line_no, 2, "CAMERA name")
            name = _block_name(tokens[1], line_no, "camera")
            self._register(name, scene.add_camera(name), line_no)
        elif command in _STREAMED_MODEL_COMMANDS:
            self.last_asset = self._parse_streamed_model(tokens, line_no)
        elif command == "LIGHT":
            _expect_count(tokens, line_no, 2, "LIGHT name")
            name = _block_name(tokens[1], line_no, "light")
            light = scene.add_light(name, fields=self._default_light_fields())
            self._register(name, light, line_no)
            self.last_asset = light
        elif command == "AUDIO":
            _expect_count(tokens, line_no, 2, "AUDIO name")
            name = _block_name(tokens[1], line_no, "audio")
            self._register(name, scene.add_audio(name), line_no)
        elif command == "SUBTITLE":
            _expect_count(tokens, line_no, 2, "SUBTITLE name")
            name = _block_name(tokens[1], line_no, "subtitle")
            self._register(name, scene.add_subtitle(name), line_no)
        elif command == "FADE":
            _expect_count(tokens, line_no, 2, "FADE name")
            name = _block_name(tokens[1], line_no, "fade")
            self._register(name, scene.add_fade(name), line_no)
        elif command == "OVERLAY":
            _expect_count(tokens, line_no, 2, "OVERLAY name")
            name = _block_name(tokens[1], line_no, "overlay")
            self._register(name, scene.add_overlay(name), line_no)
        elif command == "DECAL":
            _expect_count(tokens, line_no, 2, "DECAL name")
            name = _block_name(tokens[1], line_no, "decal")
            self._register(name, scene.add_decal(name), line_no)
        else:
            raise CutScriptError(line_no, f"unknown ASSETS command {tokens[0]!r}")

    def _register(self, name: str, binding: CutBinding, line_no: int) -> None:
        if name in self.bindings:
            raise CutScriptError(
                line_no, f"duplicate asset name {name!r}", code="asset.duplicate"
            )
        self.bindings[name] = binding

    def _parse_streamed_model(self, tokens: list[str], line_no: int) -> CutBinding:
        _expect_count(tokens, line_no, 2, f"{tokens[0].upper()} name")
        command = tokens[0].upper()
        base_command = command.removeprefix("STATIC_").removeprefix("ANIMATED_")
        is_explicit_animated = command.startswith("ANIMATED_")
        name = _block_name(tokens[1], line_no, command.lower())
        options = self._key_values(tokens[2:], line_no)
        model_name = options.get("MODEL", name)
        ytyp_name = options.get("YTYP") or options.get("TYPE_FILE")
        anim_base = options.get("ANIM_BASE")
        anim_streaming_base = (
            _int(options["ANIM_STREAMING_BASE"], line_no, "AnimStreamingBase")
            if "ANIM_STREAMING_BASE" in options
            else None
        )
        anim_export = options.get("ANIM_EXPORT")
        face_export = options.get("FACE_EXPORT")
        cutscene_name = options.get("CNAME")
        preset_name = options.get("PRESET")
        preset = (
            _enum_value(
                CutPropAnimationPreset, preset_name, line_no, "animation preset"
            )
            if preset_name
            else None
        )
        if is_explicit_animated:
            cutscene_name = cutscene_name or name
            anim_base = anim_base or model_name
            preset = preset or CutPropAnimationPreset.COMMON_PROP
        scene = self._require_scene(line_no)
        if base_command == "PROP":
            binding = scene.add_prop(
                name,
                model_name=model_name,
                ytyp_name=ytyp_name,
                animation_clip_base=anim_base,
                animation_preset=preset,
            )
        else:
            binding_cls = CutPed if base_command == "PED" else CutVehicle
            binding = scene.add_typed_binding(binding_cls, name)
            assert isinstance(binding, (CutPed, CutVehicle))
            binding.configure_model_asset(
                streaming_name=model_name,
                type_file=ytyp_name,
                animation_clip_base=anim_base,
            )
            if preset is not None:
                binding.apply_animation_preset(preset)
        if hasattr(binding, "configure_model_asset"):
            binding.configure_model_asset(  # type: ignore[attr-defined]
                cutscene_name=cutscene_name,
                anim_streaming_base=anim_streaming_base,
                anim_export_ctrl_spec_file=anim_export,
                face_export_ctrl_spec_file=face_export,
            )
        self._register(name, binding, line_no)
        return binding

    def _apply_model_property(
        self, binding: CutBinding, tokens: list[str], line_no: int
    ) -> None:
        command = tokens[0].upper()
        _expect_count(tokens, line_no, 2, f"{command} value")
        if command == "MODEL":
            binding.model_name = tokens[1]  # type: ignore[attr-defined]
        elif command == "YTYP":
            binding.ytyp_name = tokens[1]  # type: ignore[attr-defined]
        elif command == "TYPE_FILE":
            binding.ytyp_name = tokens[1]  # type: ignore[attr-defined]
        elif command == "ANIM_BASE":
            binding.animation_clip_base = tokens[1]  # type: ignore[attr-defined]
        elif command == "ANIM_STREAMING_BASE":
            binding.anim_streaming_base = _int(tokens[1], line_no, "AnimStreamingBase")  # type: ignore[attr-defined]
        elif command == "ANIM_EXPORT":
            binding.anim_export_ctrl_spec_file = tokens[1]  # type: ignore[attr-defined]
        elif command == "FACE_EXPORT":
            binding.face_export_ctrl_spec_file = tokens[1]  # type: ignore[attr-defined]
        elif command == "CNAME":
            binding.cutscene_name = tokens[1]  # type: ignore[attr-defined]
        elif command == "PRESET":
            binding.apply_animation_preset(
                _enum_value(
                    CutPropAnimationPreset, tokens[1], line_no, "animation preset"
                )
            )  # type: ignore[attr-defined]

    def _key_values(self, tokens: list[str], line_no: int) -> dict[str, str]:
        if len(tokens) % 2 != 0:
            raise CutScriptError(line_no, "expected KEY value pairs")
        result: dict[str, str] = {}
        for index in range(0, len(tokens), 2):
            result[tokens[index].upper()] = tokens[index + 1]
        return result

    def _default_light_fields(self) -> dict[str, Any]:
        return {
            "vDirection": (0.0, 0.0, -1.0),
            "vColour": (1.0, 1.0, 1.0),
            "vPosition": (0.0, 0.0, 0.0),
            "fIntensity": 1.0,
            "fFallOff": 10.0,
            "fConeAngle": 45.0,
            "fVolumeIntensity": 0.0,
            "fVolumeSizeScale": 0.0,
            "fCoronaSize": 0.0,
            "fCoronaIntensity": 0.0,
            "fCoronaZBias": 0.0,
            "fInnerConeAngle": 0.0,
            "fExponentialFallOff": 1.0,
            "fShadowBlur": 0.0,
            "iLightType": int(CutLightType.POINT),
            "iLightProperty": int(CutLightProperty.NONE),
            "TextureDictID": 0,
            "TextureKey": 0,
            "uLightFlags": int(CutLightFlag.NONE),
            "uHourFlags": 0xFFFFFF,
            "bStatic": False,
        }

    def _apply_light_property(
        self, light: CutLight, tokens: list[str], line_no: int
    ) -> None:
        command = tokens[0].upper()
        if command == "TYPE":
            _expect_count(tokens, line_no, 2, "TYPE POINT|SPOT|DIRECTIONAL")
            light.fields["iLightType"] = int(
                _enum_value(CutLightType, tokens[1], line_no, "light type")
            )
        elif command in {"POSITION", "POS"}:
            light.fields["vPosition"] = _vec(tokens[1:], line_no, "position", 3)
        elif command in {"DIRECTION", "DIR"}:
            light.fields["vDirection"] = _vec(tokens[1:], line_no, "direction", 3)
        elif command in {"COLOR", "COLOUR"}:
            light.fields["vColour"] = _css_rgb(tokens[1:], line_no, "color")
        elif command == "INTENSITY":
            _expect_count(tokens, line_no, 2, "INTENSITY value")
            light.fields["fIntensity"] = _float(tokens[1], line_no, "intensity")
        elif command == "FALLOFF":
            _expect_count(tokens, line_no, 2, "FALLOFF value")
            light.fields["fFallOff"] = _float(tokens[1], line_no, "falloff")
        elif command == "CONE":
            _expect_count(tokens, line_no, 2, "CONE degrees")
            light.fields["fConeAngle"] = _float(tokens[1], line_no, "cone")
        elif command == "INNER_CONE":
            _expect_count(tokens, line_no, 2, "INNER_CONE degrees")
            light.fields["fInnerConeAngle"] = _float(tokens[1], line_no, "inner cone")
        elif command == "CORONA":
            _expect_count(tokens, line_no, 3, "CORONA size intensity")
            light.fields["fCoronaSize"] = _float(tokens[1], line_no, "corona size")
            light.fields["fCoronaIntensity"] = _float(
                tokens[2], line_no, "corona intensity"
            )
        elif command == "FLAGS":
            light.fields["uLightFlags"] = int(_light_flags(tokens[1:], line_no))
        elif command == "PROPERTY":
            _expect_count(tokens, line_no, 2, "PROPERTY name")
            light.fields["iLightProperty"] = int(
                _enum_value(CutLightProperty, tokens[1], line_no, "light property")
            )
        elif command == "STATIC":
            _expect_count(tokens, line_no, 2, "STATIC true|false")
            light.fields["bStatic"] = tokens[1].lower() in {"1", "true", "yes", "on"}

    def _parse_track(self, tokens: list[str], line_no: int) -> None:
        if self.track is None:
            raise CutScriptError(line_no, "TRACK command missing before timeline event")
        _expect_count(tokens, line_no, 2, "time command")
        if not _is_float_token(tokens[0]):
            command = tokens[0].upper()
            if (
                self.track == "CAMERA"
                and self.pending_camera_cut is not None
                and command in _CAMERA_CUT_PROPERTY_COMMANDS
            ):
                self._apply_camera_cut_property(tokens, line_no)
                return
            raise CutScriptError(line_no, "expected timeline event: time command")
        time = _float(tokens[0], line_no, "time")
        command = tokens[1].upper()
        args = tokens[2:]
        self._flush_pending_event(line_no)
        if command == "SCENE":
            self._load_scene(time, args, line_no, unload=False)
        elif command == "UNLOAD_SCENE":
            self._load_scene(time, args, line_no, unload=True)
        elif command == "MODELS":
            self._models(time, args, line_no, unload=False)
        elif command == "UNLOAD_MODELS":
            self._models(time, args, line_no, unload=True)
        elif command == "ANIM_DICT":
            self._anim_dict(time, args, line_no, unload=False)
        elif command == "UNLOAD_ANIM_DICT":
            self._anim_dict(time, args, line_no, unload=True)
        elif command == "CUT":
            self._start_camera_cut(time, args, line_no)
        elif command == "DRAW_DISTANCE":
            self._draw_distance(time, args, line_no)
        elif command == "PLAY" and self.track == "AUDIO":
            self._audio_event(time, args, line_no, action="play")
        elif command == "PLAY":
            self._play_anim(time, args, line_no, stop=False)
        elif command == "STOP":
            if self.track == "AUDIO":
                self._audio_event(time, args, line_no, action="stop")
            else:
                self._play_anim(time, args, line_no, stop=True)
        elif command == "SHOW":
            if self.track == "SUBTITLES":
                self._subtitle_event(time, args, line_no, show=True)
            elif self.track in {"OVERLAY", "OVERLAYS"}:
                self._overlay_event(time, args, line_no, show=True)
            else:
                self._visibility(time, args, line_no, show=True)
        elif command == "HIDE":
            if self.track == "SUBTITLES":
                self._subtitle_event(time, args, line_no, show=False)
            elif self.track in {"OVERLAY", "OVERLAYS"}:
                self._overlay_event(time, args, line_no, show=False)
            else:
                self._visibility(time, args, line_no, show=False)
        elif command in {"LOAD_OVERLAYS", "UNLOAD_OVERLAYS"}:
            self._overlays(time, args, line_no, unload=command.startswith("UNLOAD"))
        elif command in {"LOAD", "UNLOAD"} and self.track in {"OVERLAY", "OVERLAYS"}:
            self._overlays(time, args, line_no, unload=command == "UNLOAD")
        elif command in {"ATTACH", "ATTACHMENT"}:
            self._attachment(time, args, line_no)
        elif command in {"FADE_IN", "FADE_OUT", "IN", "OUT"}:
            self._fade(time, args, line_no, fade_in=command in {"FADE_IN", "IN"})
        elif command in {"ENABLE", "ON"}:
            self._light(time, args, line_no, enabled=True)
        elif command in {"DISABLE", "OFF"}:
            self._light(time, args, line_no, enabled=False)
        elif command in {"LOAD", "UNLOAD"} and self.track in {
            "AUDIO",
            "LOAD",
            "CLEANUP",
        }:
            self._audio_event(time, args, line_no, action=command.lower())
        elif command in {"SUBTITLES", "UNLOAD_SUBTITLES"}:
            self._subtitles_dict(
                time, args, line_no, unload=command.startswith("UNLOAD")
            )
        else:
            raise CutScriptError(
                line_no, f"unknown TRACK {self.track} command {command!r}"
            )

    def _load_scene(
        self, time: float, args: list[str], line_no: int, *, unload: bool
    ) -> None:
        _expect_count(args, line_no, 1, "SCENE name")
        scene = self._require_scene(line_no)
        target = self._asset_manager(line_no)
        payload = CutLoadScenePayload(args[0])
        if unload:
            scene.unload_scene(time, payload, target=target)
        else:
            scene.load_scene(time, payload, target=target)

    def _models(
        self, time: float, args: list[str], line_no: int, *, unload: bool
    ) -> None:
        bindings = self._bindings(args, line_no)
        scene = self._require_scene(line_no)
        target = self._asset_manager(line_no)
        ids = [binding.object_id for binding in bindings]
        if unload:
            scene.unload_models(time, ids, target=target)
        else:
            scene.load_models(time, ids, target=target)

    def _anim_dict(
        self, time: float, args: list[str], line_no: int, *, unload: bool
    ) -> None:
        _expect_count(args, line_no, 1, "ANIM_DICT name")
        scene = self._require_scene(line_no)
        target = self._animation_manager(line_no)
        if unload:
            scene.unload_anim_dict(time, args[0], target=target)
        else:
            scene.load_anim_dict(time, args[0], target=target)

    def _start_camera_cut(self, time: float, args: list[str], line_no: int) -> None:
        _expect_count(args, line_no, 1, "CUT camera")
        camera_name = _block_name(args[0], line_no, "camera")
        camera = self._binding(camera_name, line_no)
        if camera.role != "camera":
            raise CutScriptError(line_no, f"{camera_name!r} is not a CAMERA asset")
        pending = _PendingCameraCut(
            line=line_no, time=time, camera=camera, name=camera_name
        )
        self.pending_camera_cut = pending
        self._apply_camera_cut_values(pending, args[1:], line_no)

    def _apply_camera_cut_property(self, tokens: list[str], line_no: int) -> None:
        if self.pending_camera_cut is None:
            raise CutScriptError(
                line_no, "camera cut property without a pending CUT event"
            )
        self._apply_camera_cut_values(self.pending_camera_cut, tokens, line_no)

    def _apply_camera_cut_values(
        self, pending: _PendingCameraCut, values: list[str], line_no: int
    ) -> None:
        index = 0
        while index < len(values):
            key = values[index].upper()
            if key == "NAME":
                pending.name = _option_value(values, index, line_no, "NAME")
                index += 2
            elif key in {"POS", "POSITION"}:
                pending.position = _vec(
                    values[index + 1 :], line_no, "camera position", 3
                )  # type: ignore[assignment]
                index += 4
            elif key in {"ROT", "ROTATION"}:
                euler = _vec(
                    values[index + 1 :], line_no, "camera Euler XYZ rotation", 3
                )
                pending.rotation_quaternion = _euler_xyz_degrees_to_quaternion(
                    euler[0], euler[1], euler[2]
                )
                index += 4
            elif key == "QUAT":
                pending.rotation_quaternion = _vec(
                    values[index + 1 :], line_no, "camera quaternion", 4
                )  # type: ignore[assignment]
                index += 5
            elif key == "NEAR":
                pending.near_draw_distance = _float(
                    _option_value(values, index, line_no, "NEAR"), line_no, "near"
                )
                index += 2
            elif key == "FAR":
                pending.far_draw_distance = _float(
                    _option_value(values, index, line_no, "FAR"), line_no, "far"
                )
                index += 2
            elif key == "MAP_LOD":
                pending.map_lod_scale = _float(
                    _option_value(values, index, line_no, "MAP_LOD"), line_no, "map_lod"
                )
                index += 2
            else:
                raise CutScriptError(
                    line_no, f"unknown CAMERA CUT option {values[index]!r}"
                )

    def _draw_distance(self, time: float, args: list[str], line_no: int) -> None:
        _expect_count(args, line_no, 2, "DRAW_DISTANCE camera value")
        camera = self._binding(args[0], line_no)
        if camera.role != "camera":
            raise CutScriptError(line_no, f"{args[0]!r} is not a CAMERA asset")
        self._require_scene(line_no).set_draw_distance(
            time, camera, _float(args[1], line_no, "draw distance")
        )

    def _play_anim(
        self, time: float, args: list[str], line_no: int, *, stop: bool
    ) -> None:
        _expect_count(args, line_no, 1, "PLAY object")
        binding = self._binding(args[0], line_no)
        manager = self._animation_manager(line_no)
        scene = self._require_scene(line_no)
        if stop:
            scene.clear_anim(time, binding, target=manager)
        else:
            scene.set_anim(time, binding, target=manager)

    def _visibility(
        self, time: float, args: list[str], line_no: int, *, show: bool
    ) -> None:
        scene = self._require_scene(line_no)
        for binding in self._bindings(args, line_no):
            if show:
                scene.show_objects(time, binding)
            else:
                scene.hide_objects(time, binding)

    def _light(
        self, time: float, args: list[str], line_no: int, *, enabled: bool
    ) -> None:
        _expect_count(args, line_no, 1, "ENABLE light")
        light = self._binding(args[0], line_no)
        if light.role != "light":
            raise CutScriptError(line_no, f"{args[0]!r} is not a LIGHT asset")
        scene = self._require_scene(line_no)
        if enabled:
            scene.set_light(time, light)
        else:
            scene.clear_light(time, light)

    def _subtitle_event(
        self, time: float, args: list[str], line_no: int, *, show: bool
    ) -> None:
        _expect_count(args, line_no, 1, "SHOW subtitle_key FOR seconds")
        scene = self._require_scene(line_no)
        subtitle = self._subtitle(line_no)
        if not show:
            scene.hide_subtitle(time, subtitle, args[0])
            return
        duration = 0.0
        language = -1
        index = 1
        while index < len(args):
            key = args[index].upper()
            if key == "FOR":
                duration = _float(
                    _option_value(args, index, line_no, "FOR"),
                    line_no,
                    "subtitle duration",
                )
                index += 2
            elif key in {"LANG", "LANGUAGE"}:
                language = _int(
                    _option_value(args, index, line_no, key), line_no, "language"
                )
                index += 2
            else:
                raise CutScriptError(
                    line_no, f"unknown SUBTITLE option {args[index]!r}"
                )
        scene.show_subtitle(
            time,
            subtitle,
            CutSubtitlePayload(args[0], duration=duration, language_id=language),
        )

    def _subtitles_dict(
        self, time: float, args: list[str], line_no: int, *, unload: bool
    ) -> None:
        _expect_count(args, line_no, 1, "SUBTITLES name")
        scene = self._require_scene(line_no)
        target = self._asset_manager(line_no)
        if unload:
            scene.unload_subtitles(time, args[0], target=target)
        else:
            scene.load_subtitles(time, args[0], target=target)

    def _overlays(
        self, time: float, args: list[str], line_no: int, *, unload: bool
    ) -> None:
        overlays = self._bindings(args, line_no)
        for overlay in overlays:
            if overlay.role != "overlay":
                raise CutScriptError(
                    line_no, f"{overlay.name!r} is not an OVERLAY asset"
                )
        scene = self._require_scene(line_no)
        target = self._asset_manager(line_no)
        if unload:
            scene.unload_overlays(time, overlays, target=target)
        else:
            scene.load_overlays(time, overlays, target=target)

    def _overlay_event(
        self, time: float, args: list[str], line_no: int, *, show: bool
    ) -> None:
        _expect_count(args, line_no, 1, "SHOW overlay")
        scene = self._require_scene(line_no)
        for overlay in self._bindings(args, line_no):
            if overlay.role != "overlay":
                raise CutScriptError(
                    line_no, f"{overlay.name!r} is not an OVERLAY asset"
                )
            if show:
                scene.show_overlay(time, overlay)
            else:
                scene.hide_overlay(time, overlay)

    def _audio_event(
        self, time: float, args: list[str], line_no: int, *, action: str
    ) -> None:
        _expect_count(args, line_no, 1, f"{action.upper()} audio_name")
        scene = self._require_scene(line_no)
        audio = self._audio(line_no)
        if action == "load":
            scene.load_audio(time, args[0], target=audio)
        elif action == "unload":
            scene.unload_audio(time, args[0], target=audio)
        elif action == "play":
            scene.play_audio(time, audio, args[0])
        elif action == "stop":
            scene.stop_audio(time, audio, args[0])

    def _attachment(self, time: float, args: list[str], line_no: int) -> None:
        _expect_count(args, line_no, 3, "ATTACH object TO attachment_name")
        binding = self._binding(args[0], line_no)
        if args[1].upper() != "TO":
            raise CutScriptError(
                line_no, "ATTACH expects: ATTACH object TO attachment_name"
            )
        self._require_scene(line_no).set_attachment(time, binding, args[2])

    def _fade(
        self, time: float, args: list[str], line_no: int, *, fade_in: bool
    ) -> None:
        fade = self._fade_binding(line_no)
        value = 1.0
        color = 0xFF000000
        index = 0
        if args and args[0].upper() not in {"VALUE", "COLOR", "COLOUR"}:
            fade = self._binding(args[0], line_no)
            if fade.role != "fade":
                raise CutScriptError(line_no, f"{args[0]!r} is not a FADE asset")
            index = 1
        while index < len(args):
            key = args[index].upper()
            if key == "VALUE":
                value = _float(
                    _option_value(args, index, line_no, "VALUE"), line_no, "fade value"
                )
                index += 2
            elif key in {"COLOR", "COLOUR"}:
                color_values: list[str] = []
                index += 1
                while index < len(args) and args[index].upper() not in {
                    "VALUE",
                    "COLOR",
                    "COLOUR",
                }:
                    color_values.append(args[index])
                    index += 1
                if not color_values:
                    raise CutScriptError(line_no, f"{key} expects a color")
                color = _css_argb(color_values, line_no, "fade color")
            else:
                raise CutScriptError(line_no, f"unknown FADE option {args[index]!r}")
        payload = CutScreenFadePayload(value=value, color=color)
        scene = self._require_scene(line_no)
        if fade_in:
            scene.fade_in(time, fade, payload)
        else:
            scene.fade_out(time, fade, payload)


def _token(value: Any, resolver: CutScriptHashResolver | None = None) -> str:
    text = _hash_token(value, resolver=resolver)
    if not text:
        return '""'
    if text.startswith("0x") or all(char.isalnum() or char in "._-/" for char in text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _resolve_known_hash(
    value: int, resolver: CutScriptHashResolver | None
) -> str | None:
    if value == 0 or resolver is None:
        return None
    if isinstance(resolver, HashResolver):
        return resolver.resolve_hash(value)
    return resolver.get(value) or resolver.get(value & 0xFFFFFFFF)


def _hash_token(value: Any, resolver: CutScriptHashResolver | None = None) -> str:
    if isinstance(value, CutHashedString):
        if value.text:
            return value.text
        resolved = _resolve_known_hash(value.hash, resolver)
        return resolved or f"0x{value.hash & 0xFFFFFFFF:08X}"
    if isinstance(value, int):
        resolved = _resolve_known_hash(value, resolver)
        return resolved or f"0x{value & 0xFFFFFFFF:08X}"
    if value is None:
        return "0x00000000"
    return str(value)


def _number(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        text = f"{value:.9f}".rstrip("0").rstrip(".")
        return text if text and text != "-0" else "0"
    return str(value)


def _vector(values: Any, size: int) -> str:
    items = tuple(values or ())
    if len(items) < size:
        items = (*items, *([0.0] * (size - len(items))))
    return " ".join(_number(float(items[index])) for index in range(size))


def _scene_name_for_export(
    scene: CutScene,
    source_name: str | None = None,
    resolver: CutScriptHashResolver | None = None,
) -> str:
    if scene.scene_name:
        return str(scene.scene_name)
    if source_name:
        return Path(source_name).stem
    for track in scene.tracks:
        for event in track.events:
            if event.event_name == "load_scene":
                raw = event.payload.get("cName")
                if isinstance(raw, CutHashedString) and raw.hash == 0 and not raw.text:
                    continue
                label = _hash_token(raw or event.label, resolver=resolver)
                if label and label != "0x00000000":
                    return label
    return "cutscene"


def _flag_tokens(value: CutSceneFlags | int | None) -> list[str]:
    if value is None:
        return ["PLAYABLE"]
    flags = CutSceneFlags(value)
    if flags == CutSceneFlags.NONE:
        return ["0x00000000"]
    tokens: list[str] = []
    remaining = int(flags)
    for flag in CutSceneFlags:
        if flag is CutSceneFlags.NONE:
            continue
        if flags & flag:
            tokens.append(flag.name)
            remaining &= ~int(flag)
    if remaining:
        tokens.append(f"0x{remaining:08X}")
    return tokens


def _asset_aliases(scene: CutScene) -> dict[int, str]:
    counts: dict[str, int] = {}
    aliases: dict[int, str] = {}
    for binding in scene.bindings:
        base = binding.role or "asset"
        if base in {
            "prop",
            "ped",
            "vehicle",
            "camera",
            "light",
            "audio",
            "subtitle",
            "fade",
            "overlay",
            "decal",
        }:
            candidate = f"{base}_{binding.object_id}"
        elif base == "asset_manager":
            candidate = "assets"
        elif base == "animation_manager":
            candidate = "anims"
        else:
            candidate = f"{base}_{binding.object_id}"
        count = counts.get(candidate, 0)
        counts[candidate] = count + 1
        aliases[binding.object_id] = (
            candidate if count == 0 else f"{candidate}_{count + 1}"
        )
    return aliases


def _binding_value(
    binding: CutBinding,
    field_name: str,
    resolver: CutScriptHashResolver | None,
) -> str | None:
    if field_name not in binding.fields:
        return None
    return _hash_token(binding.fields.get(field_name), resolver=resolver)


def _write_streamed_model(
    lines: list[str],
    binding: CutBinding,
    alias: str,
    resolver: CutScriptHashResolver | None,
) -> None:
    animated = _streamed_binding_is_animated(binding)
    if binding.role == "ped":
        command = "ANIMATED_PED" if animated else "PED"
    elif binding.role == "vehicle":
        command = "ANIMATED_VEHICLE" if animated else "VEHICLE"
    else:
        command = "ANIMATED_PROP" if animated else "STATIC_PROP"
    lines.append(f"  {command} {alias}:")
    properties = [
        ("MODEL", _binding_value(binding, "StreamingName", resolver)),
        ("YTYP", _binding_value(binding, "typeFile", resolver)),
        ("CNAME", _binding_value(binding, "cName", resolver)),
        (
            "ANIM_STREAMING_BASE",
            f"0x{int(binding.fields['AnimStreamingBase']) & 0xFFFFFFFF:08X}"
            if "AnimStreamingBase" in binding.fields
            else None,
        ),
        ("ANIM_EXPORT", _binding_value(binding, "cAnimExportCtrlSpecFile", resolver)),
        ("FACE_EXPORT", _binding_value(binding, "cFaceExportCtrlSpecFile", resolver)),
    ]
    for key, value in properties:
        if value is not None:
            lines.append(f"    {key} {_token(value, resolver=resolver)}")


def _streamed_binding_is_animated(binding: CutBinding) -> bool:
    return (
        _field_hash_nonzero(binding.fields.get("AnimStreamingBase"))
        or _field_hash_nonzero(binding.fields.get("cAnimExportCtrlSpecFile"))
        or _field_hash_nonzero(binding.fields.get("cAnimCompressionFile"))
    )


def _field_hash_nonzero(value: Any) -> bool:
    if isinstance(value, CutHashedString):
        return int(value.hash) != 0
    if value in (None, "", 0):
        return False
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return True


def _write_light(lines: list[str], binding: CutBinding, alias: str) -> None:
    fields = binding.fields
    lines.append(f"  LIGHT {alias}:")
    if "iLightType" in fields:
        try:
            lines.append(f"    TYPE {CutLightType(int(fields['iLightType'])).name}")
        except ValueError:
            lines.append(f"    TYPE {int(fields['iLightType'])}")
    if "vPosition" in fields:
        lines.append(f"    POSITION {_vector(fields['vPosition'], 3)}")
    if "vDirection" in fields:
        lines.append(f"    DIRECTION {_vector(fields['vDirection'], 3)}")
    if "vColour" in fields:
        colour = tuple(fields["vColour"])
        if len(colour) >= 3:
            lines.append(
                f"    COLOR {_number(float(colour[0]))} {_number(float(colour[1]))} {_number(float(colour[2]))}"
            )
    for source, target in (
        ("fIntensity", "INTENSITY"),
        ("fFallOff", "FALLOFF"),
        ("fConeAngle", "CONE"),
        ("fInnerConeAngle", "INNER_CONE"),
    ):
        if source in fields:
            lines.append(f"    {target} {_number(fields[source])}")
    if "fCoronaSize" in fields or "fCoronaIntensity" in fields:
        lines.append(
            f"    CORONA {_number(fields.get('fCoronaSize', 0.0))} {_number(fields.get('fCoronaIntensity', 0.0))}"
        )
    if "uLightFlags" in fields:
        lines.append(f"    FLAGS 0x{int(fields['uLightFlags']) & 0xFFFFFFFF:08X}")
    if "iLightProperty" in fields:
        try:
            lines.append(
                f"    PROPERTY {CutLightProperty(int(fields['iLightProperty'])).name}"
            )
        except ValueError:
            lines.append(f"    PROPERTY {int(fields['iLightProperty'])}")
    if "bStatic" in fields:
        lines.append(f"    STATIC {_number(fields['bStatic'])}")


def _object_alias_list(ids: Iterable[Any], aliases: dict[int, str]) -> str:
    names = [aliases.get(int(value), f"object_{int(value)}") for value in ids]
    return ", ".join(names)


def _event_object_alias(event: Any, aliases: dict[int, str]) -> str | None:
    value = event.payload.get("iObjectId", event.target_id)
    if value is None:
        return None
    return aliases.get(int(value), f"object_{int(value)}")


def _write_track_event(
    lines: list[str],
    event: Any,
    aliases: dict[int, str],
    *,
    include_comments: bool,
    resolver: CutScriptHashResolver | None,
) -> None:
    time = _number(event.start)
    name = event.event_name or event.kind
    payload = event.payload
    if name in {"load_scene", "unload_scene"}:
        command = "UNLOAD_SCENE" if name.startswith("unload") else "SCENE"
        lines.append(
            f"  {time} {command} {_token(payload.get('cName') or event.label, resolver=resolver)}"
        )
    elif name in {"load_models", "unload_models"}:
        command = "UNLOAD_MODELS" if name.startswith("unload") else "MODELS"
        lines.append(
            f"  {time} {command} {_object_alias_list(payload.get('iObjectIdList') or [], aliases)}"
        )
    elif name in {"load_overlays", "unload_overlays"}:
        command = "UNLOAD_OVERLAYS" if name.startswith("unload") else "LOAD_OVERLAYS"
        lines.append(
            f"  {time} {command} {_object_alias_list(payload.get('iObjectIdList') or [], aliases)}"
        )
    elif name in {"load_anim_dict", "unload_anim_dict"}:
        command = "UNLOAD_ANIM_DICT" if name.startswith("unload") else "ANIM_DICT"
        lines.append(
            f"  {time} {command} {_token(payload.get('cName') or event.label, resolver=resolver)}"
        )
    elif name in {"load_subtitles", "unload_subtitles"}:
        command = "UNLOAD_SUBTITLES" if name.startswith("unload") else "SUBTITLES"
        lines.append(
            f"  {time} {command} {_token(payload.get('cName') or event.label, resolver=resolver)}"
        )
    elif name in {"load_audio", "unload_audio", "play_audio", "stop_audio"}:
        command = {
            "load_audio": "LOAD",
            "unload_audio": "UNLOAD",
            "play_audio": "PLAY",
            "stop_audio": "STOP",
        }[name]
        lines.append(
            f"  {time} {command} {_token(payload.get('cName') or event.label, resolver=resolver)}"
        )
    elif name in {"set_anim", "clear_anim"}:
        alias = _event_object_alias(event, aliases)
        if alias:
            command = "STOP" if name == "clear_anim" else "PLAY"
            lines.append(f"  {time} {command} {alias}")
    elif name in {"show_objects", "hide_objects"}:
        alias = _event_object_alias(event, aliases)
        if alias:
            lines.append(
                f"  {time} {'SHOW' if name == 'show_objects' else 'HIDE'} {alias}"
            )
    elif name == "set_attachment":
        alias = _event_object_alias(event, aliases)
        if alias:
            lines.append(
                f"  {time} ATTACH {alias} TO {_token(payload.get('cName') or event.label, resolver=resolver)}"
            )
    elif name == "set_draw_distance":
        camera = (
            aliases.get(int(event.target_id), f"camera_{event.target_id}")
            if event.target_id is not None
            else "camera"
        )
        lines.append(
            f"  {time} DRAW_DISTANCE {camera} {_number(payload.get('fValue', 0.0))}"
        )
    elif name == "camera_cut":
        camera = (
            aliases.get(int(event.target_id), f"camera_{event.target_id}")
            if event.target_id is not None
            else "camera"
        )
        lines.append(f"  {time} CUT {camera}:")
        lines.append(
            f"    NAME {_token(payload.get('cName') or event.label, resolver=resolver)}"
        )
        lines.append(f"    POS {_vector(payload.get('vPosition'), 3)}")
        lines.append(f"    QUAT {_vector(payload.get('vRotationQuaternion'), 4)}")
        lines.append(f"    NEAR {_number(payload.get('fNearDrawDistance', 0.05))}")
        lines.append(f"    FAR {_number(payload.get('fFarDrawDistance', 1000.0))}")
        if "fMapLodScale" in payload:
            lines.append(f"    MAP_LOD {_number(payload['fMapLodScale'])}")
    elif name in {"show_subtitle", "hide_subtitle"}:
        command = "HIDE" if name == "hide_subtitle" else "SHOW"
        line = f"  {time} {command} {_token(payload.get('cName') or event.label, resolver=resolver)}"
        if name == "show_subtitle":
            line += f" FOR {_number(payload.get('fSubtitleDuration', event.duration or 0.0))}"
            if "iLanguageID" in payload:
                line += f" LANG {int(payload['iLanguageID'])}"
        lines.append(line)
    elif name in {"set_light", "clear_light"}:
        alias = (
            aliases.get(int(event.target_id), f"light_{event.target_id}")
            if event.target_id is not None
            else None
        )
        if alias:
            lines.append(
                f"  {time} {'ENABLE' if name == 'set_light' else 'DISABLE'} {alias}"
            )
    elif include_comments:
        lines.append(
            f"  # unsupported {time} {name} target={event.target_id} payload={payload!r}"
        )


def cutscript_from_scene(
    scene: CutScene,
    *,
    scene_name: str | None = None,
    save_path: str | Path | None = None,
    include_comments: bool = True,
    resolver: CutScriptHashResolver | None = None,
) -> str:
    scene.build()
    name = scene_name or _scene_name_for_export(scene, resolver=resolver)
    aliases = _asset_aliases(scene)
    lines = [
        f"CUTSCENE {_token(name, resolver=resolver)}",
        f"DURATION {_number(float(scene.duration or 0.0))}",
    ]
    if scene.offset is not None:
        lines.append(f"OFFSET {_vector(scene.offset, 3)}")
    if scene.rotation is not None:
        lines.append(f"ROTATION {_number(scene.rotation)}")
    lines.append(f"FLAGS {' '.join(_flag_tokens(scene.cutscene_flags))}")
    lines.append("")
    lines.append("ASSETS")
    for binding in scene.bindings:
        alias = aliases[binding.object_id]
        if binding.role in {"prop", "ped", "vehicle"}:
            _write_streamed_model(lines, binding, alias, resolver)
        elif binding.role == "light":
            _write_light(lines, binding, alias)
        else:
            command = {
                "asset_manager": "ASSET_MANAGER",
                "animation_manager": "ANIM_MANAGER",
                "camera": "CAMERA",
                "audio": "AUDIO",
                "subtitle": "SUBTITLE",
                "fade": "FADE",
                "overlay": "OVERLAY",
                "decal": "DECAL",
            }.get(binding.role)
            if command is not None:
                lines.append(f"  {command} {alias}")
            elif include_comments:
                lines.append(
                    f"  # unsupported asset {binding.object_id}: {binding.type_name}"
                )
    lines.append("END")
    for track in scene.tracks:
        lines.append("")
        track_name = (track.name or track.key or track.kind).upper().replace(" ", "_")
        if track.key == "load":
            track_name = "LOAD"
        elif track.kind == "camera_cut" or track.key == "camera":
            track_name = "CAMERA"
        elif track.kind == "subtitle" or track.key == "subtitle":
            track_name = "SUBTITLES"
        elif track.kind == "animation_binding":
            track_name = "ANIMATION"
        elif track.kind == "light_state":
            track_name = "LIGHTS"
        lines.append(f"TRACK {track_name}")
        for event in track.events:
            _write_track_event(
                lines,
                event,
                aliases,
                include_comments=include_comments,
                resolver=resolver,
            )
        lines.append("END")
    if save_path is not None:
        lines.append("")
        lines.append(f"SAVE {_token(str(save_path), resolver=resolver)}")
    return "\n".join(lines) + "\n"


def _resolver_with_path_names(
    source: str | Path | None,
    resolver: CutScriptHashResolver | None,
    *,
    register_siblings: bool,
) -> CutScriptHashResolver | None:
    if resolver is not None:
        target = resolver
    elif source is None:
        return get_hash_resolver()
    else:
        target = HashResolver(
            dict(get_hash_resolver().hash_to_name),
            dict(get_hash_resolver().name_to_hash),
        )
    if not register_siblings or source is None or not isinstance(target, HashResolver):
        return target
    path = Path(source)
    if path.is_file():
        target.register_path_name(path)
        for sibling in path.parent.iterdir():
            if sibling.is_file():
                target.register_path_name(sibling)
    return target


def cut_to_cutscript(
    source: CutScene | CutFile | CutNode | bytes | str | Path,
    *,
    save_path: str | Path | None = None,
    include_comments: bool = True,
    resolver: CutScriptHashResolver | None = None,
    register_sibling_names: bool = True,
) -> str:
    scene = read_cut_scene(source)
    scene_name = Path(source).stem if isinstance(source, (str, Path)) else None
    resolved = _resolver_with_path_names(
        source if isinstance(source, (str, Path)) else None,
        resolver,
        register_siblings=register_sibling_names,
    )
    return cutscript_from_scene(
        scene,
        scene_name=scene_name,
        save_path=save_path,
        include_comments=include_comments,
        resolver=resolved,
    )


def save_cut_as_cutscript(
    source: CutScene | CutFile | CutNode | bytes | str | Path,
    destination: str | Path | None = None,
    *,
    include_comments: bool = True,
    resolver: CutScriptHashResolver | None = None,
    register_sibling_names: bool = True,
) -> Path:
    target = (
        Path(destination)
        if destination is not None
        else Path(source).with_suffix(".cuts")
    )  # type: ignore[arg-type]
    save_path = target.with_suffix(".cut").name
    text = cut_to_cutscript(
        source,
        save_path=save_path,
        include_comments=include_comments,
        resolver=resolver,
        register_sibling_names=register_sibling_names,
    )
    target.write_text(text, encoding="utf-8")
    return target


def parse_cutscript(
    text: str, *, base_path: str | Path | None = None
) -> CutScriptResult:
    return _CutScriptParser(text, base_path=base_path).parse()


def cutscene_from_cutscript(
    text: str, *, base_path: str | Path | None = None
) -> CutScene:
    return parse_cutscript(text, base_path=base_path).scene


def read_cutscript(path: str | Path) -> CutScriptResult:
    source = Path(path)
    return parse_cutscript(source.read_text(encoding="utf-8"), base_path=source.parent)


def save_cutscript(
    path: str | Path, *, destination: str | Path | None = None, validate: bool = True
) -> Path:
    result = read_cutscript(path)
    target = Path(destination) if destination is not None else result.save_path
    if target is None:
        raise ValueError("CUT script has no SAVE path and no destination was provided")
    result.scene.save(target, validate=validate)
    return target


__all__ = [
    "CutScriptHashResolver",
    "CutScriptError",
    "CutScriptResult",
    "cut_to_cutscript",
    "cutscene_from_cutscript",
    "cutscript_from_scene",
    "parse_cutscript",
    "read_cutscript",
    "save_cut_as_cutscript",
    "save_cutscript",
]
