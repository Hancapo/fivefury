from __future__ import annotations

import enum


class YmtFormat(enum.Enum):
    UNKNOWN = "unknown"
    RSC = "rsc"
    RBF = "rbf"
    PSO = "pso"


class YmtContentType(enum.Enum):
    NONE = "none"
    MAP_PARENT_TXDS = "CMapParentTxds"
    SCENARIO_POINT_MANIFEST = "CScenarioPointManifest"
    SCENARIO_POINT_REGION = "CScenarioPointRegion"
    PED_VARIATION = "CPedVariationInfo"
    PED_METADATA = "CPedModelInfo__InitDataList"
    STREAMING_REQUEST_RECORD = "CStreamingRequestRecord"
    AUDIO_OCCLUSION = "naOcclusionInteriorMetadata"
    TASK_TUNING = "CTuningFile"
    CREATURE_METADATA = "CCreatureMetaData"
    DATA_FILE_CONTENTS = "CDataFileMgr__ContentsOfDataFileXml"
    CREDITS = "CCreditArray"
    POP_GROUPS = "CPopGroupList"
    CLIP_SETS = "fwClipSetManager"
    VEHICLE_COLORS = "CVehicleModelInfoVarGlobal"
    VEHICLE_MOD_COLORS = "CVehicleModColors"
    VEHICLE_VARIATIONS = "CVehicleModelInfoVariation"
    ANIM_POST_FX = "AnimPostFXManager"
    VFX_INTERIORS = "CVfxInteriorInfoMgr"
    VFX_PEDS = "CVfxPedInfoMgr"
    VFX_VEHICLES = "CVfxVehicleInfoMgr"
    IPL_CULL_BOXES = "CIplCullBoxFile"
    FIRING_PATTERNS = "CFiringPatternInfoManager"
    CAMERA_METADATA = "camMetadataStore"
    EXPLOSIONS = "CExplosionInfoManager"
    PED_PERSONALITIES = "CPedModelInfo__PersonalityDataList"
    STATS_TUNING = "sStatsMetadataTuning"
    PLAYER_SPECIAL_ABILITIES = "CPlayerSpecialAbilityManager"
    DOOR_TUNING = "CDoorTuningFile"
    COVER_TUNING = "CCoverTuningFile"
    POP_ZONES = "CPopZoneData"
    LENS_ARTEFACTS = "LensArtefacts"
    PARTICLE_ASSETS = "CPtFxAssetInfoMgr"
    VFX_FOG_VOLUMES = "CVfxFogVolumeInfoMgr"
    VFX_REGIONS = "CVfxRegionInfoMgr"
    VFX_WEAPONS = "CVfxWeaponInfoMgr"
    LEVEL_DATA = "CLevelData"
    PROCEDURAL_OBJECTS = "CProceduralInfo"
    SLOWNESS_ZONES = "CSlownessZoneManager"
    REQUEST_RECORDING = "strRequestRecording"
    PROFANITY_FILTER = "fwProfanityFilter"
    MOVIE_SUBTITLES = "CMovieSubtitleContainer"
    MAP_TYPES = "CMapTypes"
    CRIMINAL_CAREER_CATALOG = "CCriminalCareerCatalog"
    CRIMINAL_CAREER_CART = "CCriminalCareerShoppingCartValidator"
    PAGE_PROVIDER = "CPageProvider"


C_SCENARIO_POINT_MANIFEST = 0x54FA14DF
C_SCENARIO_POINT_REGION_DEF = 0x4A9FA5CC
C_SCENARIO_POINT_GROUP = 0xC9AEDC3F
C_SCENARIO_POINT_REGION = 0x58FCEA50
C_PED_VARIATION_INFO = 0x16760659
C_PED_MODEL_INFO_INIT_DATA_LIST = 0xDD77771E
C_PED_MODEL_INFO_INIT_DATA = 0xEB66D086
C_STREAMING_REQUEST_RECORD = 0x0819E70E
C_STREAMING_REQUEST_FRAME = 0x3B8EFC0B
C_STREAMING_REQUEST_COMMON_SET = 0x50F454F4
C_MAP_PARENT_TXDS = 0xAEF45801
RAGE_SPD_AABB = 0xF377E8C8


YMT_ROOT_NAMES = {
    C_SCENARIO_POINT_MANIFEST: YmtContentType.SCENARIO_POINT_MANIFEST.value,
    C_SCENARIO_POINT_REGION_DEF: "CScenarioPointRegionDef",
    C_SCENARIO_POINT_GROUP: "CScenarioPointGroup",
    C_SCENARIO_POINT_REGION: YmtContentType.SCENARIO_POINT_REGION.value,
    C_PED_VARIATION_INFO: YmtContentType.PED_VARIATION.value,
    C_PED_MODEL_INFO_INIT_DATA_LIST: YmtContentType.PED_METADATA.value,
    C_PED_MODEL_INFO_INIT_DATA: "CPedModelInfo__InitData",
    C_STREAMING_REQUEST_RECORD: YmtContentType.STREAMING_REQUEST_RECORD.value,
    C_STREAMING_REQUEST_FRAME: "CStreamingRequestFrame",
    C_STREAMING_REQUEST_COMMON_SET: "CStreamingRequestCommonSet",
    C_MAP_PARENT_TXDS: YmtContentType.MAP_PARENT_TXDS.value,
    RAGE_SPD_AABB: "rage__spdAABB",
    0xDE5DB4C2: YmtContentType.AUDIO_OCCLUSION.value,
    0xA89B70F0: YmtContentType.TASK_TUNING.value,
    0x79B7DCE5: YmtContentType.CREATURE_METADATA.value,
    0x6783FAF6: YmtContentType.DATA_FILE_CONTENTS.value,
    0x771AE97C: YmtContentType.CREDITS.value,
    0x2C0AE035: YmtContentType.POP_GROUPS.value,
    0xF0613E4B: YmtContentType.CLIP_SETS.value,
    0xBDD20BCF: YmtContentType.VEHICLE_COLORS.value,
    0xAA5E7A9A: YmtContentType.VEHICLE_MOD_COLORS.value,
    0x2C7C954B: YmtContentType.VEHICLE_VARIATIONS.value,
    0xFAE1A86A: YmtContentType.ANIM_POST_FX.value,
    0xF5FC6658: YmtContentType.VFX_INTERIORS.value,
    0x9F9C8B64: YmtContentType.VFX_PEDS.value,
    0x00C79A03: YmtContentType.VFX_VEHICLES.value,
    0x3EFCBE5D: YmtContentType.IPL_CULL_BOXES.value,
    0xDC716590: YmtContentType.FIRING_PATTERNS.value,
    0x6172064B: YmtContentType.CAMERA_METADATA.value,
    0x0F271702: YmtContentType.EXPLOSIONS.value,
    0x90BA59AF: YmtContentType.PED_PERSONALITIES.value,
    0xCE32C59B: YmtContentType.STATS_TUNING.value,
    0xA042ED3C: YmtContentType.PLAYER_SPECIAL_ABILITIES.value,
    0x8FB9AE81: YmtContentType.DOOR_TUNING.value,
    0xB3CF04B4: YmtContentType.COVER_TUNING.value,
    0x03BA8D5A: YmtContentType.POP_ZONES.value,
    0x4D7F7488: YmtContentType.LENS_ARTEFACTS.value,
    0xD68BFD46: YmtContentType.PARTICLE_ASSETS.value,
    0x61580F34: YmtContentType.VFX_FOG_VOLUMES.value,
    0xD65D6396: YmtContentType.VFX_REGIONS.value,
    0x252DDD9D: YmtContentType.VFX_WEAPONS.value,
    0x047A1DE0: YmtContentType.LEVEL_DATA.value,
    0xFF50DF45: YmtContentType.PROCEDURAL_OBJECTS.value,
    0xDDCCB56D: YmtContentType.SLOWNESS_ZONES.value,
    0x50B2EA08: YmtContentType.REQUEST_RECORDING.value,
    0x3796F001: YmtContentType.PROFANITY_FILTER.value,
}

YMT_CONTENT_TYPES_BY_NAME = {
    member.value: member
    for member in YmtContentType
    if member is not YmtContentType.NONE
}
YMT_CONTENT_TYPES_BY_HASH = {
    root_hash: YMT_CONTENT_TYPES_BY_NAME[name]
    for root_hash, name in YMT_ROOT_NAMES.items()
    if name in YMT_CONTENT_TYPES_BY_NAME
}


def ymt_content_type(root_hash: int = 0, root_name: str = "") -> YmtContentType:
    return YMT_CONTENT_TYPES_BY_HASH.get(
        int(root_hash), YMT_CONTENT_TYPES_BY_NAME.get(root_name, YmtContentType.NONE)
    )


__all__ = [
    "C_MAP_PARENT_TXDS",
    "C_PED_MODEL_INFO_INIT_DATA",
    "C_PED_MODEL_INFO_INIT_DATA_LIST",
    "C_PED_VARIATION_INFO",
    "C_SCENARIO_POINT_GROUP",
    "C_SCENARIO_POINT_MANIFEST",
    "C_SCENARIO_POINT_REGION",
    "C_SCENARIO_POINT_REGION_DEF",
    "C_STREAMING_REQUEST_COMMON_SET",
    "C_STREAMING_REQUEST_FRAME",
    "C_STREAMING_REQUEST_RECORD",
    "RAGE_SPD_AABB",
    "YMT_ROOT_NAMES",
    "YmtContentType",
    "YmtFormat",
    "ymt_content_type",
]
