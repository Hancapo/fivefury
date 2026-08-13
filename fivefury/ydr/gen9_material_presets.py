from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType

from ..hashing import jenk_hash

_ZERO = (0.0, 0.0, 0.0, 0.0)
_ONE = (1.0, 0.0, 0.0, 0.0)
_WHITE = (1.0, 1.0, 1.0, 1.0)


@dataclasses.dataclass(frozen=True, slots=True)
class Gen9MaterialPreset:
    name: str
    shaders: frozenset[str]
    parameters: tuple[tuple[str, tuple[float, ...]], ...]


def _preset(
    name: str,
    shaders: str,
    **parameters: tuple[float, ...],
) -> Gen9MaterialPreset:
    return Gen9MaterialPreset(
        name=name,
        shaders=frozenset(shaders.split()),
        parameters=tuple(parameters.items()),
    )


GEN9_MATERIAL_PRESETS = (
    _preset(
        "ped_damage_zones",
        "ped ped_cloth ped_cloth_enveff ped_decal ped_decal_decoration "
        "ped_decal_exp ped_default_mp ped_emissive ped_enveff "
        "ped_nopeddamagedecals ped_palette ped_wrinkle ped_wrinkle_cloth "
        "ped_wrinkle_cloth_enveff ped_wrinkle_cs ped_wrinkle_enveff",
        BloodZoneAdjust=(
            0.4,
            0.0,
            1.0,
            1.0,
            0.2,
            0.4,
            1.0,
            1.0,
            0.1,
            0.6,
            -1.0,
            1.0,
            0.1,
            0.7,
            1.0,
            -1.0,
            0.1,
            0.8,
            1.0,
            1.0,
            0.1,
            0.9,
            1.0,
            1.0,
        ),
    ),
    _preset(
        "vehicle_surface",
        "vehicle_badges vehicle_basic vehicle_blurredrotor "
        "vehicle_blurredrotor_emissive vehicle_cloth vehicle_cutout "
        "vehicle_dash_emissive vehicle_dash_emissive_opaque vehicle_decal "
        "vehicle_decal2 vehicle_detail vehicle_detail2 vehicle_emissive_alpha "
        "vehicle_emissive_opaque vehicle_generic vehicle_interior "
        "vehicle_interior2 vehicle_licenseplate vehicle_lightsemissive "
        "vehicle_lightsemissive_siren vehicle_mesh vehicle_mesh2_enveff "
        "vehicle_mesh_enveff vehicle_paint1 vehicle_paint1_enveff vehicle_paint2 "
        "vehicle_paint2_enveff vehicle_shuts vehicle_tire vehicle_tire_emissive "
        "vehicle_track vehicle_track2 vehicle_track2_emissive vehicle_track_ammo "
        "vehicle_track_emissive vehicle_track_siren vehicle_vehglass "
        "vehicle_vehglass_inner",
        DiffuseColor2=_WHITE,
    ),
    _preset(
        "vehicle_interior",
        "vehicle_interior vehicle_interior2",
        DirtLevelMod=_WHITE,
    ),
    _preset(
        "vehicle_badges",
        "vehicle_badges",
        matDiffuseSpecularRampEnabled=(-1.0, 0.0, 0.0, 0.0),
    ),
    _preset(
        "vehicle_tire_motion",
        "vehicle_tire vehicle_tire_emissive",
        matWheelPrevWorldViewProj0=(0.0,) * 16,
    ),
    _preset(
        "vehicle_license_plate",
        "vehicle_licenseplate",
        FontOutlineMinMaxDepthEnabled=(0.475, 0.5, 0.0, 0.0),
        FontOutlineColor=_ZERO,
    ),
    _preset(
        "hard_alpha",
        "emissive_additive_alpha emissive_additive_uv_alpha glass "
        "glass_breakable glass_displacement glass_emissive glass_emissivenight "
        "glass_env glass_normal_spec_reflect glass_pv glass_pv_env glass_reflect "
        "glass_spec grass_fur grass_fur_mask mirror_crack mirror_decal "
        "mirror_default normal_um_tnt parallax parallax_specmap ptfx_model "
        "reflect weapon_emissivestrong_alpha weapon_normal_spec_alpha",
        HardAlphaBlend=_ONE,
    ),
    _preset(
        "mirror_surface",
        "mirror_crack mirror_default",
        Fresnel=(0.97, 0.0, 0.0, 0.0),
        Reflectivity=(0.45, 0.0, 0.0, 0.0),
        Specular=(100.0, 0.0, 0.0, 0.0),
    ),
    _preset(
        "mirror_debug",
        "mirror_crack mirror_decal mirror_default",
        MirrorDebugParams=_ZERO,
    ),
    _preset(
        "glass_pv",
        "glass_pv glass_pv_env",
        SpecularMapIntensityMask=_ONE,
    ),
    _preset(
        "cloud_environment",
        "clouds_altitude clouds_anim clouds_animsoft clouds_fast clouds_fog clouds_soft",
        EnvMapAlphaScale=(0.75, 0.0, 0.0, 0.0),
    ),
    _preset(
        "cloud_animation",
        "clouds_fast clouds_fog clouds_soft",
        AnimCombine=(1.0, 1.0, 1.0, 0.0),
        AnimBlendWeights=_ONE,
        AnimSculpt=_ZERO,
    ),
    _preset(
        "cloud_depth",
        "clouds_fast",
        NearFarQMult=_ZERO,
        SoftParticleRange=(175.0, 0.0, 0.0, 0.0),
    ),
    _preset(
        "cloud_scattering",
        "clouds_fog",
        ScatterG_GSquared_PhaseMult_Scale=(-0.75, 0.5625, 2.1, 1.0),
    ),
    _preset(
        "tree_surface",
        "trees trees_lod trees_lod2 trees_lod_tnt trees_normal "
        "trees_normal_diffspec trees_normal_diffspec_tnt trees_normal_spec "
        "trees_normal_spec_tnt trees_shadow_proxy trees_tnt",
        AlphaClampNormal=_ONE,
        AlphaScaleNormal=_ONE,
    ),
    _preset(
        "tree_lod",
        "trees_lod trees_lod2 trees_lod_tnt",
        umGlobalParams0=(0.025, 0.02, 1.0, 0.5),
    ),
    _preset(
        "tree_self_shadowing",
        "trees_lod2",
        SelfShadowing=(0.8, 0.0, 0.0, 0.0),
    ),
    _preset(
        "indirect_batch",
        "grass_batch normal_spec_batch",
        gLodFadeInstRange=(0.0, 0.0, 1.0, 0.0),
        gIndirectCountPerLod=_ZERO,
    ),
    _preset(
        "grass_batch_debug",
        "grass_batch",
        bDebugSwitches0=_ZERO,
    ),
    _preset(
        "normal_diffspec",
        "normal_diffspec normal_diffspec_detail normal_diffspec_detail_dpm "
        "normal_diffspec_detail_dpm_tnt normal_diffspec_detail_tnt "
        "normal_diffspec_tnt",
        Specular=(100.0, 0.0, 0.0, 0.0),
    ),
    _preset(
        "water_parallax",
        "water_fountain water_poolenv water_river water_riverfoam "
        "water_riverlod water_riverocean water_rivershallow water_shallow",
        ParallaxIntensity=(0.3, 0.0, 0.0, 0.0),
    ),
    _preset(
        "water_ripple_motion",
        "water_fountain water_poolenv water_riverocean",
        RippleSpeed=_ZERO,
    ),
    _preset(
        "water_river_foam",
        "water_riverfoam",
        RippleBumpiness=(0.356, 0.0, 0.0, 0.0),
        RippleScale=(0.04, 0.0, 0.0, 0.0),
        SpecularFalloff=(1118.0, 0.0, 0.0, 0.0),
        SpecularIntensity=_ONE,
    ),
)


def _build_material_parameters() -> Mapping[str, Mapping[int, tuple[float, ...]]]:
    parameters_by_shader: dict[str, dict[int, tuple[float, ...]]] = {}
    for preset in GEN9_MATERIAL_PRESETS:
        for shader_name in preset.shaders:
            shader_parameters = parameters_by_shader.setdefault(shader_name, {})
            for parameter_name, value in preset.parameters:
                semantic_hash = int(jenk_hash(parameter_name))
                previous = shader_parameters.setdefault(semantic_hash, value)
                if previous != value:
                    raise ValueError(
                        f"Conflicting Gen9 presets for {shader_name}.{parameter_name}"
                    )
    return MappingProxyType(
        {
            shader_name: MappingProxyType(values)
            for shader_name, values in parameters_by_shader.items()
        }
    )


GEN9_MATERIAL_PARAMETERS: Mapping[str, Mapping[int, tuple[float, ...]]] = (
    _build_material_parameters()
)


def get_gen9_material_parameters(shader_name: str) -> Mapping[int, tuple[float, ...]]:
    normalized = shader_name.strip().lower().removesuffix(".sps")
    return GEN9_MATERIAL_PARAMETERS.get(normalized, {})
