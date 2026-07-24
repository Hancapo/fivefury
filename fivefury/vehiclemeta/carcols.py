from __future__ import annotations

import dataclasses
from typing import Any

from ..metahash import MetaHash
from .common import boolean, enum_value, field, items, meta_hash, number, text, vector
from .enums import VehicleModCameraPosition, VehicleModKitType, VehicleModType
from .variations import LicensePlateProbability, plate_probabilities


@dataclasses.dataclass(slots=True, frozen=True)
class VehiclePlateTexture:
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    diffuse_map: MetaHash = dataclasses.field(default_factory=MetaHash)
    normal_map: MetaHash = dataclasses.field(default_factory=MetaHash)
    font_extents: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0)
    max_letters: tuple[float, ...] = (0.0, 0.0)
    font_color: int = 0x00FFFFFF
    outline_color: int = 0x00FFFFFF
    outline_enabled: bool = False
    outline_depth: tuple[float, ...] = (0.0, 0.0)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehiclePlateTexture:
        return cls(
            name=meta_hash(field(value, "m_TextureSetName", "TextureSetName")),
            diffuse_map=meta_hash(field(value, "m_DiffuseMapName", "DiffuseMapName")),
            normal_map=meta_hash(field(value, "m_NormalMapName", "NormalMapName")),
            font_extents=vector(field(value, "m_FontExtents", "FontExtents"), 4),
            max_letters=vector(
                field(value, "m_MaxLettersOnPlate", "MaxLettersOnPlate"), 2
            ),
            font_color=number(field(value, "m_FontColor", "FontColor"), 0x00FFFFFF),
            outline_color=number(
                field(value, "m_FontOutlineColor", "FontOutlineColor"), 0x00FFFFFF
            ),
            outline_enabled=boolean(
                field(value, "m_IsFontOutlineEnabled", "IsFontOutlineEnabled")
            ),
            outline_depth=vector(
                field(value, "m_FontOutlineMinMaxDepth", "FontOutlineMinMaxDepth"), 2
            ),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehiclePlates:
    textures: list[VehiclePlateTexture] = dataclasses.field(default_factory=list)
    default_texture_index: int = -1
    numeric_offset: int = 0
    alphabetic_offset: int = 10
    space_offset: int = 63
    random_character_offset: int = 36
    random_character_count: int = 4
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehiclePlates:
        return cls(
            textures=[
                VehiclePlateTexture.from_value(item)
                for item in items(value, "m_Textures", "Textures")
            ],
            default_texture_index=number(
                field(value, "m_DefaultTexureIndex", "DefaultTexureIndex"), -1
            ),
            numeric_offset=number(field(value, "m_NumericOffset", "NumericOffset"), 0),
            alphabetic_offset=number(
                field(value, "m_AlphabeticOffset", "AlphabeticOffset"), 10
            ),
            space_offset=number(field(value, "m_SpaceOffset", "SpaceOffset"), 63),
            random_character_offset=number(
                field(value, "m_RandomCharOffset", "RandomCharOffset"), 36
            ),
            random_character_count=number(
                field(value, "m_NumRandomChar", "NumRandomChar"), 4
            ),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleLight:
    intensity: float = 0.0
    falloff_max: float = 0.0
    falloff_exponent: float = 8.0
    inner_cone_angle: float = 0.0
    outer_cone_angle: float = 0.0
    emissive_boost: bool = False
    color: int = 0
    texture_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    mirror_texture: bool = True
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleLight:
        return cls(
            intensity=number(field(value, "intensity"), 0.0),
            falloff_max=number(field(value, "falloffMax"), 0.0),
            falloff_exponent=number(field(value, "falloffExponent"), 8.0),
            inner_cone_angle=number(field(value, "innerConeAngle"), 0.0),
            outer_cone_angle=number(field(value, "outerConeAngle"), 0.0),
            emissive_boost=boolean(field(value, "emmissiveBoost", "emissiveBoost")),
            color=number(field(value, "color"), 0),
            texture_name=meta_hash(field(value, "textureName")),
            mirror_texture=boolean(field(value, "mirrorTexture"), True),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleCorona:
    size: float = 0.0
    far_size: float = 0.0
    intensity: float = 0.0
    far_intensity: float = 0.0
    color: int = 0
    count: int = 1
    spacing: int = 128
    far_spacing: int = 255
    rotation: tuple[float, ...] = (0.0, 0.0, 0.0)
    z_bias: float = 0.08
    pull_in: bool = False
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleCorona:
        return cls(
            size=number(field(value, "size"), 0.0),
            far_size=number(field(value, "size_far"), 0.0),
            intensity=number(field(value, "intensity"), 0.0),
            far_intensity=number(field(value, "intensity_far"), 0.0),
            color=number(field(value, "color"), 0),
            count=number(field(value, "numCoronas"), 1),
            spacing=number(field(value, "distBetweenCoronas"), 128),
            far_spacing=number(field(value, "distBetweenCoronas_far"), 255),
            rotation=(
                number(field(value, "xRotation"), 0.0),
                number(field(value, "yRotation"), 0.0),
                number(field(value, "zRotation"), 0.0),
            ),
            z_bias=number(field(value, "zBias"), 0.08),
            pull_in=boolean(field(value, "pullCoronaIn")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleLightSettings:
    id: int = 0xFF
    indicator: VehicleLight | None = None
    rear_indicator_corona: VehicleCorona | None = None
    front_indicator_corona: VehicleCorona | None = None
    tail_light: VehicleLight | None = None
    tail_light_corona: VehicleCorona | None = None
    tail_light_middle_corona: VehicleCorona | None = None
    head_light: VehicleLight | None = None
    head_light_corona: VehicleCorona | None = None
    reversing_light: VehicleLight | None = None
    reversing_light_corona: VehicleCorona | None = None
    name: str = ""
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleLightSettings:
        def light(name: str) -> VehicleLight | None:
            item = field(value, name)
            return VehicleLight.from_value(item) if item is not None else None

        def corona(name: str) -> VehicleCorona | None:
            item = field(value, name)
            return VehicleCorona.from_value(item) if item is not None else None

        return cls(
            id=number(field(value, "id"), 0xFF),
            indicator=light("indicator"),
            rear_indicator_corona=corona("rearIndicatorCorona"),
            front_indicator_corona=corona("frontIndicatorCorona"),
            tail_light=light("tailLight"),
            tail_light_corona=corona("tailLightCorona"),
            tail_light_middle_corona=corona("tailLightMiddleCorona"),
            head_light=light("headLight"),
            head_light_corona=corona("headLightCorona"),
            reversing_light=light("reversingLight"),
            reversing_light_corona=corona("reversingLightCorona"),
            name=text(field(value, "name")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleMod:
    model_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    label: str = ""
    linked_models: list[MetaHash] = dataclasses.field(default_factory=list)
    mod_type: VehicleModType | int = VehicleModType.SPOILER
    bone: int = -1
    collision_bone: int = -1
    camera_position: VehicleModCameraPosition | int = VehicleModCameraPosition.DEFAULT
    audio_apply: float = 1.0
    weight: int = 0
    turn_off_extra: bool = False
    disable_bonnet_camera: bool = False
    allow_bonnet_slide: bool = True
    weapon_slot: int = -1
    secondary_weapon_slot: int = -1
    disable_projectile_driveby: bool = False
    disable_driveby: bool = False
    disable_driveby_seat: int = -1
    secondary_disable_driveby_seat: int = -1
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleMod:
        return cls(
            model_name=meta_hash(field(value, "m_modelName", "modelName")),
            label=text(field(value, "m_modShopLabel", "modShopLabel")),
            linked_models=[
                meta_hash(item)
                for item in items(value, "m_linkedModels", "linkedModels")
            ],
            mod_type=enum_value(
                VehicleModType, field(value, "m_type", "type"), VehicleModType.SPOILER
            ),
            bone=number(field(value, "m_bone", "bone"), -1),
            collision_bone=number(field(value, "m_collisionBone", "collisionBone"), -1),
            camera_position=enum_value(
                VehicleModCameraPosition,
                field(value, "m_cameraPos", "cameraPos"),
                VehicleModCameraPosition.DEFAULT,
            ),
            audio_apply=number(field(value, "m_audioApply", "audioApply"), 1.0),
            weight=number(field(value, "m_weight", "weight"), 0),
            turn_off_extra=boolean(field(value, "m_turnOffExtra", "turnOffExtra")),
            disable_bonnet_camera=boolean(
                field(value, "m_disableBonnetCamera", "disableBonnetCamera")
            ),
            allow_bonnet_slide=boolean(
                field(value, "m_allowBonnetSlide", "allowBonnetSlide"), True
            ),
            weapon_slot=number(field(value, "m_weaponSlot", "weaponSlot"), -1),
            secondary_weapon_slot=number(
                field(value, "m_weaponSlotSecondary", "weaponSlotSecondary"), -1
            ),
            disable_projectile_driveby=boolean(
                field(value, "m_disableProjectileDriveby", "disableProjectileDriveby")
            ),
            disable_driveby=boolean(field(value, "m_disableDriveby", "disableDriveby")),
            disable_driveby_seat=number(
                field(value, "m_disableDrivebySeat", "disableDrivebySeat"), -1
            ),
            secondary_disable_driveby_seat=number(
                field(
                    value,
                    "m_disableDrivebySeatSecondary",
                    "disableDrivebySeatSecondary",
                ),
                -1,
            ),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleLinkedMod:
    model_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    bone: int = -1
    turn_off_extra: bool = False
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleLinkedMod:
        return cls(
            model_name=meta_hash(field(value, "m_modelName", "modelName")),
            bone=number(field(value, "m_bone", "bone"), -1),
            turn_off_extra=boolean(field(value, "m_turnOffExtra", "turnOffExtra")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleStatMod:
    identifier: MetaHash = dataclasses.field(default_factory=MetaHash)
    modifier: int = 0
    audio_apply: float = 1.0
    weight: int = 0
    mod_type: VehicleModType | int = VehicleModType.SPOILER
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleStatMod:
        return cls(
            identifier=meta_hash(field(value, "m_identifier", "identifier")),
            modifier=number(field(value, "m_modifier", "modifier"), 0),
            audio_apply=number(field(value, "m_audioApply", "audioApply"), 1.0),
            weight=number(field(value, "m_weight", "weight"), 0),
            mod_type=enum_value(
                VehicleModType, field(value, "m_type", "type"), VehicleModType.SPOILER
            ),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleModSlotName:
    slot: VehicleModType | int = VehicleModType.CHASSIS
    name: str = ""
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleModSlotName:
        return cls(
            slot=enum_value(
                VehicleModType, field(value, "slot"), VehicleModType.CHASSIS
            ),
            name=text(field(value, "name")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleWheel:
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    variation: MetaHash = dataclasses.field(default_factory=MetaHash)
    label: str = ""
    rim_radius: float = 0.0
    rear: bool = False
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleWheel:
        return cls(
            name=meta_hash(field(value, "m_wheelName", "wheelName")),
            variation=meta_hash(field(value, "m_wheelVariation", "wheelVariation")),
            label=text(field(value, "m_modShopLabel", "modShopLabel")),
            rim_radius=number(field(value, "m_rimRadius", "rimRadius"), 0.0),
            rear=boolean(field(value, "m_rear", "rear")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleModKit:
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    id: int = 0xFFFF
    kit_type: VehicleModKitType | int = VehicleModKitType.STANDARD
    visible_mods: list[VehicleMod] = dataclasses.field(default_factory=list)
    linked_mods: list[VehicleLinkedMod] = dataclasses.field(default_factory=list)
    stat_mods: list[VehicleStatMod] = dataclasses.field(default_factory=list)
    slot_names: list[VehicleModSlotName] = dataclasses.field(default_factory=list)
    livery_names: list[str] = dataclasses.field(default_factory=list)
    secondary_livery_names: list[str] = dataclasses.field(default_factory=list)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleModKit:
        return cls(
            name=meta_hash(field(value, "m_kitName", "kitName")),
            id=number(field(value, "m_id", "id"), 0xFFFF),
            kit_type=enum_value(
                VehicleModKitType,
                field(value, "m_kitType", "kitType"),
                VehicleModKitType.STANDARD,
            ),
            visible_mods=[
                VehicleMod.from_value(item)
                for item in items(value, "m_visibleMods", "visibleMods")
            ],
            linked_mods=[
                VehicleLinkedMod.from_value(item)
                for item in items(value, "m_linkMods", "linkMods")
            ],
            stat_mods=[
                VehicleStatMod.from_value(item)
                for item in items(value, "m_statMods", "statMods")
            ],
            slot_names=[
                VehicleModSlotName.from_value(item)
                for item in items(value, "m_slotNames", "slotNames")
            ],
            livery_names=[
                text(item) for item in items(value, "m_liveryNames", "liveryNames")
            ],
            secondary_livery_names=[
                text(item) for item in items(value, "m_livery2Names", "livery2Names")
            ],
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleModelColor:
    color: int = 0
    metallic_id: int = -1
    audio_color: int = 0
    audio_prefix: int = 0
    audio_color_hash: int = 0
    audio_prefix_hash: int = 0
    name: str = ""
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleModelColor:
        return cls(
            color=number(field(value, "m_color", "color"), 0),
            metallic_id=number(field(value, "m_metallicID", "metallicID"), -1),
            audio_color=number(field(value, "m_audioColor", "audioColor"), 0),
            audio_prefix=number(field(value, "m_audioPrefix", "audioPrefix"), 0),
            audio_color_hash=number(
                field(value, "m_audioColorHash", "audioColorHash"), 0
            ),
            audio_prefix_hash=number(
                field(value, "m_audioPrefixHash", "audioPrefixHash"), 0
            ),
            name=text(field(value, "m_colorName", "colorName")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleMetallicSetting:
    specular_intensity: float = 0.0
    specular_falloff: float = 0.0
    specular_fresnel: float = 0.0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleMetallicSetting:
        return cls(
            specular_intensity=number(field(value, "m_specInt", "specInt"), 0.0),
            specular_falloff=number(field(value, "m_specFalloff", "specFalloff"), 0.0),
            specular_fresnel=number(field(value, "m_specFresnel", "specFresnel"), 0.0),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleWindowColor:
    color: int = 0
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleWindowColor:
        return cls(
            color=number(field(value, "m_color", "color"), 0),
            name=meta_hash(field(value, "m_name", "name")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleVariationGlobalData:
    xenon_light_color: int = 0
    xenon_corona_color: int = 0
    light_intensity_multiplier: float = 0.0
    corona_intensity_multiplier: float = 0.0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleVariationGlobalData:
        return cls(
            xenon_light_color=number(
                field(value, "m_xenonLightColor", "xenonLightColor"), 0
            ),
            xenon_corona_color=number(
                field(value, "m_xenonCoronaColor", "xenonCoronaColor"), 0
            ),
            light_intensity_multiplier=number(
                field(
                    value,
                    "m_xenonLightIntensityModifier",
                    "xenonLightIntensityModifier",
                ),
                0.0,
            ),
            corona_intensity_multiplier=number(
                field(
                    value,
                    "m_xenonCoronaIntensityModifier",
                    "xenonCoronaIntensityModifier",
                ),
                0.0,
            ),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleXenonLightColor:
    light_color: int = 0
    corona_color: int = 0
    light_intensity_multiplier: float = 0.0
    corona_intensity_multiplier: float = 0.0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleXenonLightColor:
        return cls(
            light_color=number(field(value, "m_lightColor", "lightColor"), 0),
            corona_color=number(field(value, "m_coronaColor", "coronaColor"), 0),
            light_intensity_multiplier=number(
                field(value, "m_lightIntensityModifier", "lightIntensityModifier"), 0.0
            ),
            corona_intensity_multiplier=number(
                field(value, "m_coronaIntensityModifier", "coronaIntensityModifier"),
                0.0,
            ),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleSirenRotation:
    delta: float = 0.0
    start: float = 0.0
    speed: float = 0.0
    sequencer: int = 0
    multiples: int = 0
    direction: bool = False
    sync_to_bpm: bool = False
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleSirenRotation:
        return cls(
            delta=number(field(value, "delta"), 0.0),
            start=number(field(value, "start"), 0.0),
            speed=number(field(value, "speed"), 0.0),
            sequencer=number(field(value, "sequencer"), 0),
            multiples=number(field(value, "multiples"), 0),
            direction=boolean(field(value, "direction")),
            sync_to_bpm=boolean(field(value, "syncToBpm")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleSirenLight:
    rotation: VehicleSirenRotation | None = None
    flashiness: VehicleSirenRotation | None = None
    corona: Any = None
    color: int = 0
    intensity: float = 1.0
    light_group: int = 0
    rotate: bool = False
    scale: bool = False
    scale_factor: int = 0
    flash: bool = False
    light: bool = False
    spotlight: bool = False
    cast_shadows: bool = False
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleSirenLight:
        rotation = field(value, "rotation")
        flashiness = field(value, "flashiness")
        return cls(
            rotation=VehicleSirenRotation.from_value(rotation)
            if rotation is not None
            else None,
            flashiness=VehicleSirenRotation.from_value(flashiness)
            if flashiness is not None
            else None,
            corona=field(value, "corona"),
            color=number(field(value, "color"), 0),
            intensity=number(field(value, "intensity"), 1.0),
            light_group=number(field(value, "lightGroup"), 0),
            rotate=boolean(field(value, "rotate")),
            scale=boolean(field(value, "scale")),
            scale_factor=number(field(value, "scaleFactor"), 0),
            flash=boolean(field(value, "flash")),
            light=boolean(field(value, "light")),
            spotlight=boolean(field(value, "spotLight")),
            cast_shadows=boolean(field(value, "castShadows")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleSirenSettings:
    id: int = 0xFF
    name: str = ""
    time_multiplier: float = 0.0
    light_falloff_max: float = 0.0
    light_falloff_exponent: float = 0.0
    light_inner_cone_angle: float = 0.0
    light_outer_cone_angle: float = 0.0
    light_offset: float = 0.0
    texture_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    sequencer_bpm: int = 0
    use_real_lights: bool = False
    sirens: list[VehicleSirenLight] = dataclasses.field(default_factory=list)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleSirenSettings:
        return cls(
            id=number(field(value, "id"), 0xFF),
            name=text(field(value, "name")),
            time_multiplier=number(field(value, "timeMultiplier"), 0.0),
            light_falloff_max=number(field(value, "lightFalloffMax"), 0.0),
            light_falloff_exponent=number(field(value, "lightFalloffExponent"), 0.0),
            light_inner_cone_angle=number(field(value, "lightInnerConeAngle"), 0.0),
            light_outer_cone_angle=number(field(value, "lightOuterConeAngle"), 0.0),
            light_offset=number(field(value, "lightOffset"), 0.0),
            texture_name=meta_hash(field(value, "textureName")),
            sequencer_bpm=number(field(value, "sequencerBpm"), 0),
            use_real_lights=boolean(field(value, "useRealLights")),
            sirens=[
                VehicleSirenLight.from_value(item) for item in items(value, "sirens")
            ],
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleCarCols:
    plates: VehiclePlates | None = None
    colors: list[VehicleModelColor] = dataclasses.field(default_factory=list)
    metallic_settings: list[VehicleMetallicSetting] = dataclasses.field(
        default_factory=list
    )
    window_colors: list[VehicleWindowColor] = dataclasses.field(default_factory=list)
    lights: list[VehicleLightSettings] = dataclasses.field(default_factory=list)
    sirens: list[VehicleSirenSettings] = dataclasses.field(default_factory=list)
    kits: list[VehicleModKit] = dataclasses.field(default_factory=list)
    wheels: list[list[VehicleWheel]] = dataclasses.field(default_factory=list)
    global_variation_data: VehicleVariationGlobalData | None = None
    xenon_light_colors: list[VehicleXenonLightColor] = dataclasses.field(
        default_factory=list
    )
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleCarCols:
        plates = field(value, "m_VehiclePlates", "VehiclePlates")
        wheel_groups = items(value, "m_Wheels", "Wheels")
        return cls(
            plates=VehiclePlates.from_value(plates) if plates is not None else None,
            colors=[
                VehicleModelColor.from_value(item)
                for item in items(value, "m_Colors", "Colors")
            ],
            metallic_settings=[
                VehicleMetallicSetting.from_value(item)
                for item in items(value, "m_MetallicSettings", "MetallicSettings")
            ],
            window_colors=[
                VehicleWindowColor.from_value(item)
                for item in items(value, "m_WindowColors", "WindowColors")
            ],
            lights=[
                VehicleLightSettings.from_value(item)
                for item in items(value, "m_Lights", "Lights")
            ],
            sirens=[
                VehicleSirenSettings.from_value(item)
                for item in items(value, "m_Sirens", "Sirens")
            ],
            kits=[
                VehicleModKit.from_value(item)
                for item in items(value, "m_Kits", "Kits")
            ],
            wheels=[
                [VehicleWheel.from_value(wheel) for wheel in group]
                for group in wheel_groups
                if isinstance(group, (list, tuple))
            ],
            global_variation_data=VehicleVariationGlobalData.from_value(
                field(value, "m_GlobalVariationData", "GlobalVariationData")
            )
            if field(value, "m_GlobalVariationData", "GlobalVariationData") is not None
            else None,
            xenon_light_colors=[
                VehicleXenonLightColor.from_value(item)
                for item in items(value, "m_XenonLightColors", "XenonLightColors")
            ],
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleModColor:
    name: str = ""
    color: int = 0
    specular: int = 0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleModColor:
        return cls(
            name=text(field(value, "name")),
            color=number(field(value, "col"), 0),
            specular=number(field(value, "spec"), 0),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleModColors:
    metallic: list[VehicleModColor] = dataclasses.field(default_factory=list)
    classic: list[VehicleModColor] = dataclasses.field(default_factory=list)
    matte: list[VehicleModColor] = dataclasses.field(default_factory=list)
    metals: list[VehicleModColor] = dataclasses.field(default_factory=list)
    chrome: list[VehicleModColor] = dataclasses.field(default_factory=list)
    pearlescent: Any = None
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleModColors:
        def colors(name: str, alias: str) -> list[VehicleModColor]:
            return [
                VehicleModColor.from_value(item) for item in items(value, name, alias)
            ]

        return cls(
            metallic=colors("m_metallic", "metallic"),
            classic=colors("m_classic", "classic"),
            matte=colors("m_matte", "matte"),
            metals=colors("m_metals", "metals"),
            chrome=colors("m_chrome", "chrome"),
            pearlescent=field(value, "m_pearlescent", "pearlescent"),
            raw=value,
        )


__all__ = [
    "LicensePlateProbability",
    "VehicleCarCols",
    "VehicleCorona",
    "VehicleLight",
    "VehicleLightSettings",
    "VehicleLinkedMod",
    "VehicleMetallicSetting",
    "VehicleMod",
    "VehicleModColor",
    "VehicleModColors",
    "VehicleModKit",
    "VehicleModSlotName",
    "VehicleModelColor",
    "VehiclePlateTexture",
    "VehiclePlates",
    "VehicleSirenLight",
    "VehicleSirenRotation",
    "VehicleSirenSettings",
    "VehicleStatMod",
    "VehicleVariationGlobalData",
    "VehicleWheel",
    "VehicleWindowColor",
    "VehicleXenonLightColor",
    "plate_probabilities",
]
