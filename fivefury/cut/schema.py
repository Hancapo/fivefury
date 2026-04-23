from __future__ import annotations

from typing import Any

from ..hashing import jenk_hash
from .names import ARRAY_INFO_HASH, CUT_NAME_VALUES
from .pso import (
    PSCH,
    PsoDataTypeArray,
    PsoDataTypeBool,
    PsoDataTypeFloat,
    PsoDataTypeFloat3,
    PsoDataTypeFloat4,
    PsoDataTypeString,
    PsoDataTypeStructure,
    PsoDataTypeUByte,
    PsoDataTypeUInt,
    PsoDataTypeSInt,
    _PsoEntry,
    _PsoStruct,
)


def _entry(name: str | int, type_id: int, subtype: int, data_offset: int, reference_key: int = 0) -> _PsoEntry:
    name_hash = ARRAY_INFO_HASH if name == "ARRAYINFO" else int(name if isinstance(name, int) else CUT_NAME_VALUES.get(name, jenk_hash(name)))
    return _PsoEntry(
        name_hash=name_hash,
        type_id=type_id,
        subtype=subtype,
        data_offset=data_offset,
        reference_key=reference_key,
    )


def _struct(type_name: str, length: int, *entries: _PsoEntry) -> tuple[int, _PsoStruct]:
    type_hash = CUT_NAME_VALUES.get(type_name, jenk_hash(type_name))
    return type_hash, _PsoStruct(name_hash=type_hash, length=length, entries=list(entries))


def _struct_hash(type_hash: int, length: int, *entries: _PsoEntry) -> tuple[int, _PsoStruct]:
    return type_hash, _PsoStruct(name_hash=type_hash, length=length, entries=list(entries))


_BUILTIN_STRUCT_ITEMS = [
    _struct(
        "rage__parAttributeList",
        12,
        _entry("UserData1", PsoDataTypeUByte, 0, 8),
        _entry("UserData2", PsoDataTypeUByte, 0, 9),
    ),
    _struct(
        "rage__cutfCutsceneFile2",
        3360,
        _entry("fTotalDuration", PsoDataTypeFloat, 0, 268),
        _entry("cFaceDir", PsoDataTypeString, 0, 272, 0x01000000),
        _entry("ARRAYINFO", PsoDataTypeUInt, 0, 0),
        _entry("iCutsceneFlags", PsoDataTypeArray, 4, 528, 0x00040002),
        _entry("vOffset", PsoDataTypeFloat3, 0, 544),
        _entry("fRotation", PsoDataTypeFloat, 0, 560),
        _entry("vTriggerOffset", PsoDataTypeFloat3, 0, 576),
        _entry("ARRAYINFO", PsoDataTypeStructure, 3, 0),
        _entry("pCutsceneObjects", PsoDataTypeArray, 0, 592, 7),
        _entry("ARRAYINFO", PsoDataTypeStructure, 3, 0),
        _entry("pCutsceneLoadEventList", PsoDataTypeArray, 0, 608, 9),
        _entry("ARRAYINFO", PsoDataTypeStructure, 3, 0),
        _entry("pCutsceneEventList", PsoDataTypeArray, 0, 624, 11),
        _entry("ARRAYINFO", PsoDataTypeStructure, 3, 0),
        _entry("pCutsceneEventArgsList", PsoDataTypeArray, 0, 640, 13),
        _entry("attributes", PsoDataTypeStructure, 0, 656, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 672),
        _entry("iRangeStart", PsoDataTypeSInt, 0, 680),
        _entry("iRangeEnd", PsoDataTypeSInt, 0, 684),
        _entry("iAltRangeEnd", PsoDataTypeSInt, 0, 688),
        _entry("fSectionByTimeSliceDuration", PsoDataTypeFloat, 0, 692),
        _entry("fFadeOutCutsceneDuration", PsoDataTypeFloat, 0, 696),
        _entry("fFadeInGameDuration", PsoDataTypeFloat, 0, 700),
        _entry("fadeInColor", PsoDataTypeUInt, 0, 704),
        _entry("iBlendOutCutsceneDuration", PsoDataTypeSInt, 0, 708),
        _entry("iBlendOutCutsceneOffset", PsoDataTypeSInt, 0, 712),
        _entry("fFadeOutGameDuration", PsoDataTypeFloat, 0, 716),
        _entry("fFadeInCutsceneDuration", PsoDataTypeFloat, 0, 720),
        _entry("fadeOutColor", PsoDataTypeUInt, 0, 724),
        _entry("DayCoCHours", PsoDataTypeUInt, 0, 728),
        _entry("ARRAYINFO", PsoDataTypeFloat, 0, 0),
        _entry("cameraCutList", PsoDataTypeArray, 0, 736, 30),
        _entry("ARRAYINFO", PsoDataTypeFloat, 0, 0),
        _entry("sectionSplitList", PsoDataTypeArray, 0, 752, 32),
        _entry("ARRAYINFO", PsoDataTypeStructure, 0, 0, 1737539928),
        _entry("concatDataList", PsoDataTypeArray, 1, 768, 0x00280002),
        _entry("ARRAYINFO", PsoDataTypeStructure, 0, 0, 220202594),
        _entry("discardFrameList", PsoDataTypeArray, 0, 3344, 36),
    ),
    _struct(
        "rage__cutfAssetManagerObject",
        40,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
    ),
    _struct(
        "rage__cutfAnimationManagerObject",
        40,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
    ),
    _struct(
        "rage__cutfCameraObject",
        64,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
        _entry("cName", PsoDataTypeString, 7, 40),
        _entry("AnimStreamingBase", PsoDataTypeUInt, 0, 48),
        _entry("fNearDrawDistance", PsoDataTypeFloat, 0, 56),
        _entry("fFarDrawDistance", PsoDataTypeFloat, 0, 60),
    ),
    _struct(
        "rage__cutfPedModelObject",
        120,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
        _entry("cName", PsoDataTypeString, 7, 40),
        _entry("StreamingName", PsoDataTypeString, 7, 48),
        _entry("AnimStreamingBase", PsoDataTypeUInt, 0, 56),
        _entry("cAnimExportCtrlSpecFile", PsoDataTypeString, 7, 64),
        _entry("cFaceExportCtrlSpecFile", PsoDataTypeString, 7, 68),
        _entry("cAnimCompressionFile", PsoDataTypeString, 7, 72),
        _entry("cHandle", PsoDataTypeString, 7, 84),
        _entry("typeFile", PsoDataTypeString, 7, 88),
        _entry("overrideFaceAnimationFilename", PsoDataTypeString, 7, 96),
        _entry("bFoundFaceAnimation", PsoDataTypeBool, 0, 104),
        _entry("bFaceAndBodyAreMerged", PsoDataTypeBool, 0, 105),
        _entry("bOverrideFaceAnimation", PsoDataTypeBool, 0, 106),
        _entry("faceAnimationNodeName", PsoDataTypeString, 7, 108),
        _entry("faceAttributesFilename", PsoDataTypeString, 7, 112),
    ),
    _struct(
        "rage__cutfPropModelObject",
        96,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
        _entry("cName", PsoDataTypeString, 7, 40),
        _entry("StreamingName", PsoDataTypeString, 7, 48),
        _entry("AnimStreamingBase", PsoDataTypeUInt, 0, 56),
        _entry("cAnimExportCtrlSpecFile", PsoDataTypeString, 7, 64),
        _entry("cFaceExportCtrlSpecFile", PsoDataTypeString, 7, 68),
        _entry("cAnimCompressionFile", PsoDataTypeString, 7, 72),
        _entry("cHandle", PsoDataTypeString, 7, 84),
        _entry("typeFile", PsoDataTypeString, 7, 88),
    ),
    _struct(
        "rage__cutfVehicleModelObject",
        120,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
        _entry("cName", PsoDataTypeString, 7, 40),
        _entry("StreamingName", PsoDataTypeString, 7, 48),
        _entry("AnimStreamingBase", PsoDataTypeUInt, 0, 56),
        _entry("cAnimExportCtrlSpecFile", PsoDataTypeString, 7, 64),
        _entry("cFaceExportCtrlSpecFile", PsoDataTypeString, 7, 68),
        _entry("cAnimCompressionFile", PsoDataTypeString, 7, 72),
        _entry("cHandle", PsoDataTypeString, 7, 84),
        _entry("typeFile", PsoDataTypeString, 7, 88),
        _entry("ARRAYINFO", PsoDataTypeString, 3, 0),
        _entry("cRemoveBoneNameList", PsoDataTypeArray, 0, 96, 11),
        _entry("bCanApplyRealDamage", PsoDataTypeBool, 0, 112),
    ),
    _struct(
        "rage__cutfParticleEffectObject",
        64,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
        _entry("StreamingName", PsoDataTypeString, 7, 48),
        _entry("athFxListHash", PsoDataTypeString, 7, 56),
    ),
    _struct(
        "rage__cutfAudioObject",
        64,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
        _entry("cName", PsoDataTypeString, 3, 40),
        _entry("fOffset", PsoDataTypeFloat, 0, 56),
    ),
    _struct(
        "rage__cutfSubtitleObject",
        48,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
        _entry("cName", PsoDataTypeString, 7, 40),
    ),
    _struct(
        "rage__cutfScreenFadeObject",
        48,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
        _entry("cName", PsoDataTypeString, 7, 40),
    ),
    _struct(
        "rage__cutfLightObject",
        192,
        _entry("iObjectId", PsoDataTypeSInt, 0, 8),
        _entry("attributeList", PsoDataTypeStructure, 0, 20, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 32),
        _entry("cName", PsoDataTypeString, 7, 40),
        _entry("vDirection", PsoDataTypeFloat3, 0, 64),
        _entry("vColour", PsoDataTypeFloat3, 0, 80),
        _entry("vPosition", PsoDataTypeFloat3, 0, 96),
        _entry("fIntensity", PsoDataTypeFloat, 0, 112),
        _entry("fFallOff", PsoDataTypeFloat, 0, 116),
        _entry("fConeAngle", PsoDataTypeFloat, 0, 120),
        _entry("fVolumeIntensity", PsoDataTypeFloat, 0, 124),
        _entry("fVolumeSizeScale", PsoDataTypeFloat, 0, 128),
        _entry("fCoronaSize", PsoDataTypeFloat, 0, 132),
        _entry("fCoronaIntensity", PsoDataTypeFloat, 0, 136),
        _entry("fCoronaZBias", PsoDataTypeFloat, 0, 140),
        _entry("fInnerConeAngle", PsoDataTypeFloat, 0, 144),
        _entry("fExponentialFallOff", PsoDataTypeFloat, 0, 148),
        _entry("fShadowBlur", PsoDataTypeFloat, 0, 152),
        _entry("iLightType", PsoDataTypeSInt, 0, 156),
        _entry("iLightProperty", PsoDataTypeSInt, 0, 160),
        _entry("TextureDictID", PsoDataTypeSInt, 0, 164),
        _entry("TextureKey", PsoDataTypeSInt, 0, 168),
        _entry("uLightFlags", PsoDataTypeUInt, 0, 176),
        _entry("uHourFlags", PsoDataTypeUInt, 0, 180),
        _entry("bStatic", PsoDataTypeBool, 0, 186),
    ),
    _struct(
        "rage__cutfObjectIdEvent",
        56,
        _entry("fTime", PsoDataTypeFloat, 0, 16),
        _entry("iEventId", PsoDataTypeSInt, 0, 20),
        _entry("iEventArgsIndex", PsoDataTypeSInt, 0, 24),
        _entry("pChildEvents", PsoDataTypeStructure, 3, 32),
        _entry("StickyId", PsoDataTypeUInt, 0, 40),
        _entry("IsChild", PsoDataTypeBool, 0, 44),
        _entry("iObjectId", PsoDataTypeSInt, 0, 48),
    ),
    _struct(
        "rage__cutfEventArgs",
        32,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
    ),
    _struct(
        "rage__cutfNameEventArgs",
        40,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("cName", PsoDataTypeString, 7, 32),
    ),
    _struct(
        "rage__cutfFinalNameEventArgs",
        48,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("cName", PsoDataTypeString, 3, 32),
    ),
    _struct(
        "rage__cutfObjectIdEventArgs",
        40,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("iObjectId", PsoDataTypeSInt, 0, 32),
    ),
    _struct(
        "rage__cutfObjectIdNameEventArgs",
        48,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("iObjectId", PsoDataTypeSInt, 0, 32),
        _entry("cName", PsoDataTypeString, 7, 40),
    ),
    _struct(
        "rage__cutfObjectIdListEventArgs",
        48,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("ARRAYINFO", PsoDataTypeSInt, 0, 0),
        _entry("iObjectIdList", PsoDataTypeArray, 0, 32, 2),
    ),
    _struct(
        "rage__cutfFloatValueEventArgs",
        40,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("fValue", PsoDataTypeFloat, 0, 32),
    ),
    _struct(
        "rage__cutfBoolValueEventArgs",
        40,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("bValue", PsoDataTypeBool, 0, 32),
    ),
    _struct(
        "rage__cutfLoadSceneEventArgs",
        80,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("cName", PsoDataTypeString, 7, 32),
        _entry("vOffset", PsoDataTypeFloat3, 0, 48),
        _entry("fRotation", PsoDataTypeFloat, 0, 64),
        _entry("fPitch", PsoDataTypeFloat, 0, 68),
        _entry("fRoll", PsoDataTypeFloat, 0, 72),
    ),
    _struct(
        "rage__cutfSubtitleEventArgs",
        64,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("cName", PsoDataTypeString, 7, 32),
        _entry("iLanguageID", PsoDataTypeSInt, 0, 40),
        _entry("iTransitionIn", PsoDataTypeSInt, 0, 44),
        _entry("fTransitionInDuration", PsoDataTypeFloat, 0, 48),
        _entry("iTransitionOut", PsoDataTypeSInt, 0, 52),
        _entry("fTransitionOutDuration", PsoDataTypeFloat, 0, 56),
        _entry("fSubtitleDuration", PsoDataTypeFloat, 0, 60),
    ),
    _struct(
        "rage__cutfScreenFadeEventArgs",
        48,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("fValue", PsoDataTypeFloat, 0, 32),
        _entry("color", PsoDataTypeUInt, 0, 40),
    ),
    _struct(
        "rage__cutfCameraCutCharacterLightParams",
        64,
        _entry("bUseTimeCycleValues", PsoDataTypeBool, 0, 8),
        _entry("vDirection", PsoDataTypeFloat3, 0, 16),
        _entry("vColour", PsoDataTypeFloat3, 0, 32),
        _entry("fIntensity", PsoDataTypeFloat, 0, 48),
    ),
    _struct(
        "rage__cutfCameraCutEventArgs",
        272,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("cName", PsoDataTypeString, 7, 32),
        _entry("vPosition", PsoDataTypeFloat3, 0, 48),
        _entry("vRotationQuaternion", PsoDataTypeFloat4, 0, 64),
        _entry("fNearDrawDistance", PsoDataTypeFloat, 0, 80),
        _entry("fFarDrawDistance", PsoDataTypeFloat, 0, 84),
        _entry("fMapLodScale", PsoDataTypeFloat, 0, 88),
        _entry("ReflectionLodRangeStart", PsoDataTypeFloat, 0, 92),
        _entry("ReflectionLodRangeEnd", PsoDataTypeFloat, 0, 96),
        _entry("ReflectionSLodRangeStart", PsoDataTypeFloat, 0, 100),
        _entry("ReflectionSLodRangeEnd", PsoDataTypeFloat, 0, 104),
        _entry("LodMultHD", PsoDataTypeFloat, 0, 108),
        _entry("LodMultOrphanedHD", PsoDataTypeFloat, 0, 112),
        _entry("LodMultLod", PsoDataTypeFloat, 0, 116),
        _entry("LodMultSLod1", PsoDataTypeFloat, 0, 120),
        _entry("LodMultSLod2", PsoDataTypeFloat, 0, 124),
        _entry("LodMultSLod3", PsoDataTypeFloat, 0, 128),
        _entry("LodMultSLod4", PsoDataTypeFloat, 0, 132),
        _entry("WaterReflectionFarClip", PsoDataTypeFloat, 0, 136),
        _entry("SSAOLightInten", PsoDataTypeFloat, 0, 140),
        _entry("ExposurePush", PsoDataTypeFloat, 0, 144),
        _entry("LightFadeDistanceMult", PsoDataTypeFloat, 0, 148),
        _entry("LightShadowFadeDistanceMult", PsoDataTypeFloat, 0, 152),
        _entry("LightSpecularFadeDistMult", PsoDataTypeFloat, 0, 156),
        _entry("LightVolumetricFadeDistanceMult", PsoDataTypeFloat, 0, 160),
        _entry("DirectionalLightMultiplier", PsoDataTypeFloat, 0, 164),
        _entry("LensArtefactMultiplier", PsoDataTypeFloat, 0, 168),
        _entry("BloomMax", PsoDataTypeFloat, 0, 172),
        _entry("DisableHighQualityDof", PsoDataTypeBool, 0, 176),
        _entry("FreezeReflectionMap", PsoDataTypeBool, 0, 177),
        _entry("DisableDirectionalLighting", PsoDataTypeBool, 0, 178),
        _entry("AbsoluteIntensityEnabled", PsoDataTypeBool, 0, 179),
        _entry("CharacterLight", PsoDataTypeStructure, 0, 192, CUT_NAME_VALUES["rage__cutfCameraCutCharacterLightParams"]),
        _entry("ARRAYINFO", PsoDataTypeStructure, 0, 0, 1378659296),
        _entry("TimeOfDayDofModifers", PsoDataTypeArray, 0, 256, 34),
    ),
    _struct(
        "rage__cutfCascadeShadowEventArgs",
        80,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("cameraCutHashTag", PsoDataTypeString, 7, 32),
        _entry("position", PsoDataTypeFloat3, 0, 48),
        _entry("radius", PsoDataTypeFloat, 0, 64),
        _entry("interpTimeTag", PsoDataTypeFloat, 0, 68),
        _entry("cascadeIndexTag", PsoDataTypeSInt, 0, 72),
        _entry("enabled", PsoDataTypeBool, 0, 76),
        _entry("interpolateToDisabledTag", PsoDataTypeBool, 0, 77),
    ),
    _struct_hash(
        CUT_NAME_VALUES["hash_5FF00EA5"],
        40,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("hash_0BD8B46C", PsoDataTypeFloat, 0, 32),
    ),
    _struct_hash(
        CUT_NAME_VALUES["hash_94061376"],
        40,
        _entry("attributeList", PsoDataTypeStructure, 0, 12, CUT_NAME_VALUES["rage__parAttributeList"]),
        _entry("cutfAttributes", PsoDataTypeStructure, 4, 24),
        _entry("hash_0C74B449", PsoDataTypeBool, 0, 32),
    ),
    _struct_hash(
        1737539928,
        64,
        _entry("cSceneName", PsoDataTypeString, 7, 0),
        _entry("vOffset", PsoDataTypeFloat3, 0, 16),
        _entry("fStartTime", PsoDataTypeFloat, 0, 32),
        _entry("fRotation", PsoDataTypeFloat, 0, 36),
        _entry("fPitch", PsoDataTypeFloat, 0, 40),
        _entry("fRoll", PsoDataTypeFloat, 0, 44),
        _entry("iRangeStart", PsoDataTypeSInt, 0, 48),
        _entry("iRangeEnd", PsoDataTypeSInt, 0, 52),
        _entry("bValidForPlayBack", PsoDataTypeBool, 0, 56),
    ),
    _struct_hash(
        220202594,
        24,
        _entry("cSceneName", PsoDataTypeString, 7, 0),
        _entry("ARRAYINFO", PsoDataTypeSInt, 0, 0),
        _entry("frames", PsoDataTypeArray, 0, 8, 1),
    ),
]


BUILTIN_CUT_STRUCTS: dict[int, _PsoStruct] = {type_hash: struct_info for type_hash, struct_info in _BUILTIN_STRUCT_ITEMS}
BUILTIN_CUT_ROOT_TYPE_HASH = CUT_NAME_VALUES["rage__cutfCutsceneFile2"]


def _serialize_psch(structs: dict[int, _PsoStruct]) -> bytes:
    items = list(structs.items())
    header_size = 12 + len(items) * 8
    offset = header_size
    chunks: list[bytes] = []
    indexes: list[tuple[int, int]] = []
    for type_hash, struct_info in items:
        chunk = bytearray()
        chunk.extend(b"\x00\x00")
        chunk.extend(int(len(struct_info.entries)).to_bytes(2, "big", signed=False))
        chunk.extend(int(struct_info.length).to_bytes(4, "big", signed=True))
        chunk.extend(b"\x00\x00\x00\x00")
        for entry in struct_info.entries:
            chunk.extend(int(entry.name_hash).to_bytes(4, "big", signed=False))
            chunk.append(int(entry.type_id) & 0xFF)
            chunk.append(int(entry.subtype) & 0xFF)
            chunk.extend(int(entry.data_offset).to_bytes(2, "big", signed=False))
            chunk.extend(int(entry.reference_key & 0xFFFFFFFF).to_bytes(4, "big", signed=False))
        indexes.append((type_hash, offset))
        chunks.append(bytes(chunk))
        offset += len(chunk)

    payload = bytearray()
    payload.extend(b"PSCH")
    payload.extend((offset).to_bytes(4, "big", signed=False))
    payload.extend(len(items).to_bytes(4, "big", signed=False))
    for type_hash, rel_offset in indexes:
        payload.extend(int(type_hash).to_bytes(4, "big", signed=False))
        payload.extend(int(rel_offset).to_bytes(4, "big", signed=True))
    for chunk in chunks:
        payload.extend(chunk)
    return bytes(payload)


def builtin_cut_template() -> dict[str, Any]:
    return {
        "sections": {
            PSCH: _serialize_psch(BUILTIN_CUT_STRUCTS),
        },
        "structs": BUILTIN_CUT_STRUCTS,
        "root_type_hash": BUILTIN_CUT_ROOT_TYPE_HASH,
        "psin_prefix": b"\x70" * 8,
        "pmap_unknown": 0x7070,
        "block_order_hashes": [BUILTIN_CUT_ROOT_TYPE_HASH],
    }
