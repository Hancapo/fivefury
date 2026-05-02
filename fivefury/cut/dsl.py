from __future__ import annotations

import math
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .flags import CutSceneFlags, DEFAULT_PLAYABLE_CUTSCENE_FLAGS
from .lights import CutLightFlag, CutLightProperty, CutLightType
from .payloads import CutCameraCutPayload, CutLoadScenePayload, CutScreenFadePayload, CutSubtitlePayload
from .scene import (
    CutBinding,
    CutLight,
    CutPed,
    CutPropAnimationPreset,
    CutScene,
    CutVehicle,
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


_ROOT_COMMANDS = {"CUTSCENE", "DURATION", "OFFSET", "ROTATION", "FLAGS", "ASSETS", "TRACK", "SAVE"}
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
        if char in {"#", ";"}:
            return line[:index]
        if char == "/" and index + 1 < len(line) and line[index + 1] == "/":
            return line[:index]
    return line


def _tokenize(line: str, line_no: int) -> list[str]:
    lexer = shlex.shlex(_strip_line_comment(line), posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as exc:
        raise CutScriptError(line_no, str(exc)) from exc


def _expect_count(tokens: list[str], line_no: int, count: int, usage: str) -> None:
    if len(tokens) < count:
        raise CutScriptError(line_no, f"expected {usage}")


def _float(value: str, line_no: int, name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise CutScriptError(line_no, f"{name} must be a number, got {value!r}") from exc


def _int(value: str, line_no: int, name: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise CutScriptError(line_no, f"{name} must be an integer, got {value!r}") from exc


def _vec(tokens: list[str], line_no: int, name: str, size: int) -> tuple[float, ...]:
    if len(tokens) < size:
        raise CutScriptError(line_no, f"{name} expects {size} numeric values")
    return tuple(_float(tokens[index], line_no, f"{name}[{index}]") for index in range(size))


def _euler_xyz_degrees_to_quaternion(x_degrees: float, y_degrees: float, z_degrees: float) -> tuple[float, float, float, float]:
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

    def parse(self) -> CutScriptResult:
        for line_no, raw_line in enumerate(self.lines, start=1):
            tokens = _tokenize(raw_line, line_no)
            if not tokens:
                continue
            command = tokens[0].upper()
            if command in _ROOT_COMMANDS:
                self._parse_root(tokens, line_no)
                continue
            if self.section == "ASSETS":
                self._parse_asset(tokens, line_no)
                continue
            if self.section == "TRACK":
                self._parse_track(tokens, line_no)
                continue
            raise CutScriptError(line_no, f"unexpected command {tokens[0]!r}")
        if self.scene is None:
            raise CutScriptError(1, "script must start with CUTSCENE", code="cutscene.missing")
        self.scene.build()
        return CutScriptResult(scene=self.scene, save_path=self.save_path)

    def _require_scene(self, line_no: int) -> CutScene:
        if self.scene is None:
            raise CutScriptError(line_no, "CUTSCENE must be declared before this command", code="cutscene.missing")
        return self.scene

    def _binding(self, name: str, line_no: int) -> CutBinding:
        binding = self.bindings.get(name)
        if binding is None:
            raise CutScriptError(line_no, f"unknown asset {name!r}", code="asset.unknown")
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
            self.save_path = path if self.base_path is None or path.is_absolute() else self.base_path / path

    def _parse_asset(self, tokens: list[str], line_no: int) -> None:
        command = tokens[0].upper()
        scene = self._require_scene(line_no)
        if command in _LIGHT_PROPERTY_COMMANDS:
            if not isinstance(self.last_asset, CutLight):
                raise CutScriptError(line_no, f"{command} must follow a LIGHT declaration")
            self._apply_light_property(self.last_asset, tokens, line_no)
            return
        self.last_asset = None
        if command == "ASSET_MANAGER":
            _expect_count(tokens, line_no, 2, "ASSET_MANAGER name")
            self._register(tokens[1], scene.add_asset_manager(tokens[1]), line_no)
        elif command == "ANIM_MANAGER":
            _expect_count(tokens, line_no, 2, "ANIM_MANAGER name")
            self._register(tokens[1], scene.add_animation_manager(tokens[1]), line_no)
        elif command == "CAMERA":
            _expect_count(tokens, line_no, 2, "CAMERA name")
            self._register(tokens[1], scene.add_camera(tokens[1]), line_no)
        elif command in {"PROP", "PED", "VEHICLE"}:
            self._parse_streamed_model(tokens, line_no)
        elif command == "LIGHT":
            _expect_count(tokens, line_no, 2, "LIGHT name")
            light = scene.add_light(tokens[1], fields=self._default_light_fields())
            self._register(tokens[1], light, line_no)
            self.last_asset = light
        elif command == "AUDIO":
            _expect_count(tokens, line_no, 2, "AUDIO name")
            self._register(tokens[1], scene.add_audio(tokens[1]), line_no)
        elif command == "SUBTITLE":
            _expect_count(tokens, line_no, 2, "SUBTITLE name")
            self._register(tokens[1], scene.add_subtitle(tokens[1]), line_no)
        elif command == "FADE":
            _expect_count(tokens, line_no, 2, "FADE name")
            self._register(tokens[1], scene.add_fade(tokens[1]), line_no)
        elif command == "OVERLAY":
            _expect_count(tokens, line_no, 2, "OVERLAY name")
            self._register(tokens[1], scene.add_overlay(tokens[1]), line_no)
        elif command == "DECAL":
            _expect_count(tokens, line_no, 2, "DECAL name")
            self._register(tokens[1], scene.add_decal(tokens[1]), line_no)
        else:
            raise CutScriptError(line_no, f"unknown ASSETS command {tokens[0]!r}")

    def _register(self, name: str, binding: CutBinding, line_no: int) -> None:
        if name in self.bindings:
            raise CutScriptError(line_no, f"duplicate asset name {name!r}", code="asset.duplicate")
        self.bindings[name] = binding

    def _parse_streamed_model(self, tokens: list[str], line_no: int) -> None:
        _expect_count(tokens, line_no, 2, f"{tokens[0].upper()} name")
        command = tokens[0].upper()
        name = tokens[1]
        options = self._key_values(tokens[2:], line_no)
        model_name = options.get("MODEL", name)
        ytyp_name = options.get("YTYP")
        anim_base = options.get("ANIM_BASE")
        preset_name = options.get("PRESET")
        preset = _enum_value(CutPropAnimationPreset, preset_name, line_no, "animation preset") if preset_name else None
        scene = self._require_scene(line_no)
        if command == "PROP":
            binding = scene.add_prop(name, model_name=model_name, ytyp_name=ytyp_name, animation_clip_base=anim_base, animation_preset=preset)
        else:
            binding_cls = CutPed if command == "PED" else CutVehicle
            binding = scene.add_typed_binding(binding_cls, name)
            assert isinstance(binding, (CutPed, CutVehicle))
            binding.configure_model_asset(streaming_name=model_name, type_file=ytyp_name, animation_clip_base=anim_base)
            if preset is not None:
                binding.apply_animation_preset(preset)
        self._register(name, binding, line_no)

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

    def _apply_light_property(self, light: CutLight, tokens: list[str], line_no: int) -> None:
        command = tokens[0].upper()
        if command == "TYPE":
            _expect_count(tokens, line_no, 2, "TYPE POINT|SPOT|DIRECTIONAL")
            light.fields["iLightType"] = int(_enum_value(CutLightType, tokens[1], line_no, "light type"))
        elif command in {"POSITION", "POS"}:
            light.fields["vPosition"] = _vec(tokens[1:], line_no, "position", 3)
        elif command in {"DIRECTION", "DIR"}:
            light.fields["vDirection"] = _vec(tokens[1:], line_no, "direction", 3)
        elif command in {"COLOR", "COLOUR"}:
            light.fields["vColour"] = _vec(tokens[1:], line_no, "color", 3)
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
            light.fields["fCoronaIntensity"] = _float(tokens[2], line_no, "corona intensity")
        elif command == "FLAGS":
            light.fields["uLightFlags"] = int(_light_flags(tokens[1:], line_no))
        elif command == "PROPERTY":
            _expect_count(tokens, line_no, 2, "PROPERTY name")
            light.fields["iLightProperty"] = int(_enum_value(CutLightProperty, tokens[1], line_no, "light property"))
        elif command == "STATIC":
            _expect_count(tokens, line_no, 2, "STATIC true|false")
            light.fields["bStatic"] = tokens[1].lower() in {"1", "true", "yes", "on"}

    def _parse_track(self, tokens: list[str], line_no: int) -> None:
        if self.track is None:
            raise CutScriptError(line_no, "TRACK command missing before timeline event")
        _expect_count(tokens, line_no, 2, "time command")
        time = _float(tokens[0], line_no, "time")
        command = tokens[1].upper()
        args = tokens[2:]
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
            self._camera_cut(time, args, line_no)
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
        elif command in {"LOAD", "UNLOAD"} and self.track == "AUDIO":
            self._audio_event(time, args, line_no, action=command.lower())
        elif command in {"SUBTITLES", "UNLOAD_SUBTITLES"}:
            self._subtitles_dict(time, args, line_no, unload=command.startswith("UNLOAD"))
        else:
            raise CutScriptError(line_no, f"unknown TRACK {self.track} command {command!r}")

    def _load_scene(self, time: float, args: list[str], line_no: int, *, unload: bool) -> None:
        _expect_count(args, line_no, 1, "SCENE name")
        scene = self._require_scene(line_no)
        target = self._asset_manager(line_no)
        payload = CutLoadScenePayload(args[0])
        if unload:
            scene.unload_scene(time, payload, target=target)
        else:
            scene.load_scene(time, payload, target=target)

    def _models(self, time: float, args: list[str], line_no: int, *, unload: bool) -> None:
        bindings = self._bindings(args, line_no)
        scene = self._require_scene(line_no)
        target = self._asset_manager(line_no)
        ids = [binding.object_id for binding in bindings]
        if unload:
            scene.unload_models(time, ids, target=target)
        else:
            scene.load_models(time, ids, target=target)

    def _anim_dict(self, time: float, args: list[str], line_no: int, *, unload: bool) -> None:
        _expect_count(args, line_no, 1, "ANIM_DICT name")
        scene = self._require_scene(line_no)
        target = self._animation_manager(line_no)
        if unload:
            scene.unload_anim_dict(time, args[0], target=target)
        else:
            scene.load_anim_dict(time, args[0], target=target)

    def _camera_cut(self, time: float, args: list[str], line_no: int) -> None:
        _expect_count(args, line_no, 1, "CUT camera")
        camera = self._binding(args[0], line_no)
        if camera.role != "camera":
            raise CutScriptError(line_no, f"{args[0]!r} is not a CAMERA asset")
        values = args[1:]
        name = args[0]
        position = (0.0, 0.0, 0.0)
        rotation = (0.0, 0.0, 0.0, 1.0)
        near = 0.05
        far = 1000.0
        map_lod = 0.0
        index = 0
        while index < len(values):
            key = values[index].upper()
            if key == "NAME":
                name = _option_value(values, index, line_no, "NAME")
                index += 2
            elif key in {"POS", "POSITION"}:
                position = _vec(values[index + 1 :], line_no, "camera position", 3)  # type: ignore[assignment]
                index += 4
            elif key in {"ROT", "ROTATION"}:
                euler = _vec(values[index + 1 :], line_no, "camera Euler XYZ rotation", 3)
                rotation = _euler_xyz_degrees_to_quaternion(euler[0], euler[1], euler[2])
                index += 4
            elif key == "NEAR":
                near = _float(_option_value(values, index, line_no, "NEAR"), line_no, "near")
                index += 2
            elif key == "FAR":
                far = _float(_option_value(values, index, line_no, "FAR"), line_no, "far")
                index += 2
            elif key == "MAP_LOD":
                map_lod = _float(_option_value(values, index, line_no, "MAP_LOD"), line_no, "map_lod")
                index += 2
            else:
                raise CutScriptError(line_no, f"unknown CAMERA CUT option {values[index]!r}")
        self._require_scene(line_no).camera_cut(
            time,
            camera,
            CutCameraCutPayload(name, position=position, rotation_quaternion=rotation, near_draw_distance=near, far_draw_distance=far, map_lod_scale=map_lod),
        )

    def _draw_distance(self, time: float, args: list[str], line_no: int) -> None:
        _expect_count(args, line_no, 2, "DRAW_DISTANCE camera value")
        camera = self._binding(args[0], line_no)
        if camera.role != "camera":
            raise CutScriptError(line_no, f"{args[0]!r} is not a CAMERA asset")
        self._require_scene(line_no).set_draw_distance(time, camera, _float(args[1], line_no, "draw distance"))

    def _play_anim(self, time: float, args: list[str], line_no: int, *, stop: bool) -> None:
        _expect_count(args, line_no, 1, "PLAY object")
        binding = self._binding(args[0], line_no)
        manager = self._animation_manager(line_no)
        scene = self._require_scene(line_no)
        if stop:
            scene.clear_anim(time, binding, target=manager)
        else:
            scene.set_anim(time, binding, target=manager)

    def _visibility(self, time: float, args: list[str], line_no: int, *, show: bool) -> None:
        scene = self._require_scene(line_no)
        for binding in self._bindings(args, line_no):
            if show:
                scene.show_objects(time, binding)
            else:
                scene.hide_objects(time, binding)

    def _light(self, time: float, args: list[str], line_no: int, *, enabled: bool) -> None:
        _expect_count(args, line_no, 1, "ENABLE light")
        light = self._binding(args[0], line_no)
        if light.role != "light":
            raise CutScriptError(line_no, f"{args[0]!r} is not a LIGHT asset")
        scene = self._require_scene(line_no)
        if enabled:
            scene.set_light(time, light)
        else:
            scene.clear_light(time, light)

    def _subtitle_event(self, time: float, args: list[str], line_no: int, *, show: bool) -> None:
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
                duration = _float(_option_value(args, index, line_no, "FOR"), line_no, "subtitle duration")
                index += 2
            elif key in {"LANG", "LANGUAGE"}:
                language = _int(_option_value(args, index, line_no, key), line_no, "language")
                index += 2
            else:
                raise CutScriptError(line_no, f"unknown SUBTITLE option {args[index]!r}")
        scene.show_subtitle(time, subtitle, CutSubtitlePayload(args[0], duration=duration, language_id=language))

    def _subtitles_dict(self, time: float, args: list[str], line_no: int, *, unload: bool) -> None:
        _expect_count(args, line_no, 1, "SUBTITLES name")
        scene = self._require_scene(line_no)
        target = self._asset_manager(line_no)
        if unload:
            scene.unload_subtitles(time, args[0], target=target)
        else:
            scene.load_subtitles(time, args[0], target=target)

    def _overlays(self, time: float, args: list[str], line_no: int, *, unload: bool) -> None:
        overlays = self._bindings(args, line_no)
        for overlay in overlays:
            if overlay.role != "overlay":
                raise CutScriptError(line_no, f"{overlay.name!r} is not an OVERLAY asset")
        scene = self._require_scene(line_no)
        target = self._asset_manager(line_no)
        if unload:
            scene.unload_overlays(time, overlays, target=target)
        else:
            scene.load_overlays(time, overlays, target=target)

    def _overlay_event(self, time: float, args: list[str], line_no: int, *, show: bool) -> None:
        _expect_count(args, line_no, 1, "SHOW overlay")
        scene = self._require_scene(line_no)
        for overlay in self._bindings(args, line_no):
            if overlay.role != "overlay":
                raise CutScriptError(line_no, f"{overlay.name!r} is not an OVERLAY asset")
            if show:
                scene.show_overlay(time, overlay)
            else:
                scene.hide_overlay(time, overlay)

    def _audio_event(self, time: float, args: list[str], line_no: int, *, action: str) -> None:
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
            raise CutScriptError(line_no, "ATTACH expects: ATTACH object TO attachment_name")
        self._require_scene(line_no).set_attachment(time, binding, args[2])

    def _fade(self, time: float, args: list[str], line_no: int, *, fade_in: bool) -> None:
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
                value = _float(_option_value(args, index, line_no, "VALUE"), line_no, "fade value")
                index += 2
            elif key in {"COLOR", "COLOUR"}:
                color = _int(_option_value(args, index, line_no, key), line_no, "fade color")
                index += 2
            else:
                raise CutScriptError(line_no, f"unknown FADE option {args[index]!r}")
        payload = CutScreenFadePayload(value=value, color=color)
        scene = self._require_scene(line_no)
        if fade_in:
            scene.fade_in(time, fade, payload)
        else:
            scene.fade_out(time, fade, payload)


def parse_cutscript(text: str, *, base_path: str | Path | None = None) -> CutScriptResult:
    return _CutScriptParser(text, base_path=base_path).parse()


def cutscene_from_cutscript(text: str, *, base_path: str | Path | None = None) -> CutScene:
    return parse_cutscript(text, base_path=base_path).scene


def read_cutscript(path: str | Path) -> CutScriptResult:
    source = Path(path)
    return parse_cutscript(source.read_text(encoding="utf-8"), base_path=source.parent)


def save_cutscript(path: str | Path, *, destination: str | Path | None = None, validate: bool = True) -> Path:
    result = read_cutscript(path)
    target = Path(destination) if destination is not None else result.save_path
    if target is None:
        raise ValueError("CUT script has no SAVE path and no destination was provided")
    result.scene.save(target, validate=validate)
    return target


__all__ = [
    "CutScriptError",
    "CutScriptResult",
    "cutscene_from_cutscript",
    "parse_cutscript",
    "read_cutscript",
    "save_cutscript",
]
