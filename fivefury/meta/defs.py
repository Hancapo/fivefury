from __future__ import annotations

import dataclasses
from enum import IntEnum

from ..hashing import jenk_hash


class MetaDataType(IntEnum):
    BOOLEAN = 0x01
    STRUCTURE_POINTER = 0x07
    SIGNED_BYTE = 0x10
    UNSIGNED_BYTE = 0x11
    SIGNED_SHORT = 0x12
    UNSIGNED_SHORT = 0x13
    SIGNED_INT = 0x14
    UNSIGNED_INT = 0x15
    FLOAT = 0x21
    FLOAT_XYZ = 0x33
    FLOAT_XYZW = 0x34
    ARRAY_OF_CHARS = 0x40
    CHAR_POINTER = 0x44
    HASH = 0x4A
    ARRAY_OF_BYTES = 0x50
    ARRAY = 0x52
    DATA_BLOCK_POINTER = 0x59
    BYTE_ENUM = 0x60
    INT_ENUM = 0x62
    INT_FLAGS_1 = 0x63
    SHORT_FLAGS = 0x64
    INT_FLAGS_2 = 0x65
    STRUCTURE = 0x05


META_TYPE_NAME_POINTER = 0x07
META_TYPE_NAME_STRING = 0x10
META_TYPE_NAME_BYTE = 0x11
META_TYPE_NAME_USHORT = 0x13
META_TYPE_NAME_UINT = 0x15
META_TYPE_NAME_FLOAT = 0x21
META_TYPE_NAME_VECTOR4 = 0x33
META_TYPE_NAME_HASH = 0x4A
META_TYPE_NAME_ARRAYINFO = 0x100

SYSTEM_BASE = 0x50000000
GRAPHICS_BASE = 0x60000000

META_NAME_MAP: dict[str, int] = {
    "ASSET_TYPE_ASSETLESS": 4161085041,
    "ASSET_TYPE_DRAWABLE": 130075505,
    "ASSET_TYPE_DRAWABLEDICTIONARY": 1580165652,
    "ASSET_TYPE_FRAGMENT": 571047911,
    "ASSET_TYPE_UNINITIALIZED": 189734893,
    "Animations": 212063203,
    "Ao": 2996378564,
    "AvailabilityInMpSp": 2932681318,
    "BatchAABB": 1859041902,
    "BoxOccluder": 975711773,
    "CBaseArchetypeDef": 2195127427,
    "CBlockDesc": 3072355914,
    "CCarGen": 1860713439,
    "CCompositeEntityType": 1185771007,
    "CDistantLODLight": 2033467892,
    "CEntityDef": 3461354627,
    "CExtensionDef": 2226571238,
    "CExtensionDefAudioCollisionSettings": 366926375,
    "CExtensionDefAudioEmitter": 637823035,
    "CExtensionDefBuoyancy": 749982947,
    "CExtensionDefClimbHandHold": 3846820479,
    "CExtensionDefDecal": 1603354667,
    "CExtensionDefDoor": 1965932561,
    "CExtensionDefExplosionEffect": 104349545,
    "CExtensionDefExpression": 3870521079,
    "CExtensionDefLadder": 2182960161,
    "CExtensionDefLadderMaterialType": 1294270217,
    "CExtensionDefLight": 3847218957,
    "CExtensionDefLightEffect": 663891011,
    "CExtensionDefLightShaft": 2718997053,
    "CExtensionDefLightShaftDensityType": 1931949281,
    "CExtensionDefLightShaftVolumeType": 2266515059,
    "CExtensionDefParticleEffect": 975627745,
    "CExtensionDefProcObject": 2565191912,
    "CExtensionDefScript": 2837988111,
    "CExtensionDefScriptChild": 2626018860,
    "CExtensionDefScrollbars": 153722093,
    "CExtensionDefSpawnPoint": 3300062776,
    "CExtensionDefSpawnPointOverride": 2716862120,
    "CExtensionDefSwayableEffect": 4270197178,
    "CExtensionDefWalkDontWalk": 1989609596,
    "CExtensionDefWindDisturbance": 569228403,
    "CLODLight": 2276214072,
    "CLightAttrDef": 4115341947,
    "CMapData": 3545841574,
    "CMapTypes": 3649811809,
    "CMloArchetypeDef": 273704021,
    "CMloEntitySet": 3601308153,
    "CMloInstanceDef": 164374718,
    "CMloPortalDef": 2572186314,
    "CMloRoomDef": 186126833,
    "CMloTimeCycleModifier": 807246248,
    "CScenarioPointFlags__Flags": 700327466,
    "CSpawnPoint__AvailabilityMpSp": 3573596290,
    "CTimeArchetypeDef": 1991296364,
    "CTimeCycleModifier": 1733268304,
    "CapsuleHalfHeight": 2163883074,
    "CapsuleHalfWidth": 629093761,
    "CapsuleLen": 3235184882,
    "CapsuleRadius": 1996975203,
    "CollisionData": 3547055785,
    "Color": 1308845671,
    "DistantLODLightsSOA": 2954466641,
    "EndImapFile": 2059586669,
    "EndModel": 3041118144,
    "Flags": 1264718594,
    "FloatXYZ": 3805007828,
    "GrassInstanceList": 255292381,
    "Group": 1713610519,
    "ImapLink": 2142127586,
    "InstanceList": 470289337,
    "LODLightsSOA": 1774371066,
    "LODTYPES_DEPTH_HD": 3259521980,
    "LODTYPES_DEPTH_LOD": 2384644182,
    "LODTYPES_DEPTH_ORPHANHD": 2106806081,
    "LODTYPES_DEPTH_SLOD1": 2554074988,
    "LODTYPES_DEPTH_SLOD2": 315427988,
    "LODTYPES_DEPTH_SLOD3": 2164549889,
    "LODTYPES_DEPTH_SLOD4": 1868383667,
    "LodFadeStartDist": 2216273066,
    "LodInstFadeRange": 1405992723,
    "MLOInstflags": 3761966250,
    "ModelSet": 1518141539,
    "Name": 2901156542,
    "Normal": 3599348095,
    "NormalX": 3138065392,
    "NormalY": 273792636,
    "OccludeModel": 2741784237,
    "OrientToTerrain": 3341475578,
    "OwnerName": 1481791743,
    "PRI_OPTIONAL_HIGH": 3993616791,
    "PRI_OPTIONAL_LOW": 329627604,
    "PRI_OPTIONAL_MEDIUM": 515598709,
    "PRI_REQUIRED": 1943361227,
    "Pad": 1592782806,
    "Position": 210930065,
    "PropInstanceList": 3551474528,
    "PtFxAssetName": 2497993358,
    "RGBI": 194542898,
    "Radius": 3144350114,
    "Rotation": 2371198895,
    "Scale": 1018839014,
    "ScaleRange": 2691059430,
    "ScenarioType": 191322199,
    "StartImapFile": 2462971690,
    "StartModel": 226559569,
    "TimeTillPedLeaves": 4073598194,
    "aabb": 293662904,
    "ambientOcclusionMultiplier": 415356295,
    "archetypeName": 2686689324,
    "archetypes": 25836315,
    "artificialAmbientOcclusion": 599844163,
    "assetName": 2591541189,
    "assetType": 110101682,
    "attachedObjects": 2382704940,
    "audioHash": 224069936,
    "audioOcclusion": 1093790004,
    "availableInMpSp": 286077157,
    "bbMax": 3884623384,
    "bbMin": 3656352310,
    "blend": 3933447691,
    "block": 3828602749,
    "bmax": 3220565995,
    "bmin": 2028577215,
    "bodyColorRemap1": 1429703670,
    "bodyColorRemap2": 1254848286,
    "bodyColorRemap3": 1880965569,
    "bodyColorRemap4": 1719152247,
    "boneTag": 702019504,
    "bottom": 4007699126,
    "boxOccluders": 3983590932,
    "bsCentre": 3591926527,
    "bsRadius": 2196293086,
    "canBreak": 2756786344,
    "canGetOffAtBottom": 923729576,
    "canGetOffAtTop": 564839673,
    "carGenerators": 3254823756,
    "carModel": 3176005905,
    "category": 2052871693,
    "childLodDist": 3398912973,
    "clipDictionary": 424089489,
    "color": 3914595625,
    "colour": 1541149667,
    "compositeEntityTypes": 1709823211,
    "coneInnerAngle": 1163671864,
    "coneOuterAngle": 4175029060,
    "coneOuterAngleOrCapExt": 3161894080,
    "containerLods": 2935983381,
    "contentFlags": 1785155637,
    "cornerA": 3302595027,
    "cornerB": 2393877884,
    "cornerC": 2692731164,
    "cornerD": 4250372814,
    "corners": 1329770163,
    "coronaIntensity": 2292363771,
    "coronaSize": 1705000075,
    "coronaZBias": 2520359283,
    "creatureMetadataName": 2766477159,
    "cullingPlane": 1689591312,
    "dataSize": 2442753371,
    "defaultEntitySets": 1407157833,
    "densityType": 235100599,
    "dependencies": 1013942340,
    "direction": 887068712,
    "directionAmount": 1441249296,
    "disturbanceType": 3802708370,
    "doorTargetRatio": 770433283,
    "drawableDictionary": 4229936891,
    "effectHash": 2982223448,
    "enableLimitAngle": 1979299226,
    "end": 2965669335,
    "endHour": 380604338,
    "entities": 3433796359,
    "entitiesExtentsMax": 1829192759,
    "entitiesExtentsMin": 477478129,
    "entitySets": 1169996080,
    "explosionName": 3301388915,
    "explosionTag": 2653034051,
    "explosionType": 3379115010,
    "exportedBy": 1983184981,
    "expressionDictionaryName": 1095612811,
    "expressionName": 1573835099,
    "extendedRange": 3534580187,
    "extensions": 4051599144,
    "exteriorVisibiltyDepth": 552849982,
    "extents": 759134656,
    "fadeDistanceEnd": 475013030,
    "fadeDistanceStart": 40301253,
    "fadeInTimeEnd": 120454521,
    "fadeInTimeStart": 1616789093,
    "fadeOutTimeEnd": 75548206,
    "fadeOutTimeStart": 1297365553,
    "falloff": 3429369576,
    "falloffExponent": 733168314,
    "flags": 1741842546,
    "flashiness": 3829693202,
    "floorId": 2187650609,
    "fxName": 1920790105,
    "fxType": 529104057,
    "group": 3391120809,
    "groupId": 2501631252,
    "guid": 2591780461,
    "hash": 1048674328,
    "hdTextureDist": 2908576588,
    "highPri": 1331010150,
    "iCenterX": 2400909403,
    "iCenterY": 2102896237,
    "iCenterZ": 3678777723,
    "iCosZ": 1451079098,
    "iHeight": 4278674996,
    "iLength": 1021259786,
    "iSinZ": 1444301435,
    "iTimeEndOverride": 2688038523,
    "iTimeStartOverride": 591476992,
    "iWidth": 620990253,
    "initialiseOnCollision": 1562817888,
    "instancedData": 2569067561,
    "instances": 274177522,
    "intensity": 4023228733,
    "interior": 560567274,
    "length": 2508072249,
    "lightFadeDistance": 1307926275,
    "lightHash": 643049222,
    "lightType": 482065968,
    "limitAngle": 2100360280,
    "livery": 2153615120,
    "locations": 3724288529,
    "lodDist": 3212107687,
    "lodLevel": 1821316885,
    "materialType": 932754174,
    "max": 1616931012,
    "maxExtents": 2554806840,
    "maxScale": 803384552,
    "maxScaleZ": 147400493,
    "maxZOffset": 3889902555,
    "min": 4264617715,
    "minExtents": 1731020657,
    "minScale": 3662913353,
    "minScaleZ": 3913056845,
    "minZOffset": 2591582364,
    "mirrorPriority": 1185490713,
    "mloFlags": 3590839912,
    "name": 3873537812,
    "normal": 1330140418,
    "numChildren": 2793909385,
    "numExitPortals": 528711607,
    "numStreetLights": 3708891211,
    "numTris": 2337695078,
    "numVertsInBytes": 853977995,
    "objectHash": 1951307499,
    "occludeModels": 2132383965,
    "offsetPosition": 3633645315,
    "offsetRotation": 1389511464,
    "opacity": 3644411688,
    "orientX": 735213009,
    "orientY": 979440342,
    "owner": 2349203824,
    "padding1": 3180641850,
    "padding2": 2346113727,
    "padding3": 3521603295,
    "parent": 2845591121,
    "parentIndex": 3633459645,
    "pedType": 2747160189,
    "percentage": 2947557653,
    "perpendicularLength": 124715667,
    "physicsDictionaries": 949589348,
    "physicsDictionary": 3553040380,
    "popGroup": 911358791,
    "portalCount": 1105339827,
    "portals": 2314725778,
    "position": 18243940,
    "posn": 967189988,
    "priorityLevel": 647098393,
    "probability": 3698534260,
    "projectedTextureKey": 1076718994,
    "radius": 1337695475,
    "radiusInner": 406390660,
    "radiusOuter": 1814053978,
    "rage__eLodType": 1264241711,
    "rage__ePriorityLevel": 648413703,
    "rage__fwArchetypeDef": 1828301650,
    "rage__fwArchetypeDef__eAssetType": 1991964615,
    "rage__fwContainerLodDef": 372253349,
    "rage__fwEntityDef": 1161480445,
    "rage__fwExtensionDef": 2516794929,
    "rage__fwExtraTextFiles": 620994190,
    "rage__fwExtraTextPackage": 1455890208,
    "rage__fwGrassInstanceListDef": 2085051229,
    "rage__fwGrassInstanceListDef__InstanceData": 3985044770,
    "rage__fwInstancedMapData": 4048164286,
    "rage__fwMapData": 3006493421,
    "rage__fwMapTypes": 2501015278,
    "rage__fwPropInstanceListDef": 3120863088,
    "rage__fwPropInstanceListDef__InstanceData": 3932895894,
    "rage__fwTextDatabaseEntry": 2207119242,
    "rage__fwTextDatabaseSource": 2977389460,
    "rage__phBound": 285763780,
    "rage__phBoundCapsule": 3036484496,
    "rage__phBoundComposite": 3639080237,
    "rage__phCapsuleBoundDef": 1701774085,
    "rage__phCapsuleBoundDef__enCollisionBoundDef": 3044470860,
    "rage__phClothData": 3444108840,
    "rage__phClothDataDebug": 4216915179,
    "rage__phEdgeData": 3242434333,
    "rage__phVec3V": 668988190,
    "rage__phVerletCloth": 4082189131,
    "rage__phVerletClothCustomBounds": 847348117,
    "rage__spdAABB": 4084721864,
    "range": 332484516,
    "requiredImap": 2090738474,
    "roomFrom": 4101034749,
    "roomTo": 2607060513,
    "rooms": 3441481640,
    "rotation": 2010988560,
    "scale": 1342385372,
    "scaleBySunIntensity": 59101696,
    "scaleXY": 2627937847,
    "scaleZ": 284916802,
    "secondaryTimecycleName": 3255324828,
    "settings": 2768156407,
    "shadowBlur": 3672716153,
    "shadowFadeDistance": 1944267876,
    "shadowNearClip": 954647178,
    "shortRange": 178074428,
    "size": 3226656423,
    "softness": 187712958,
    "spacing": 370899326,
    "spawnType": 4261247615,
    "specialAttribute": 1813324772,
    "specularFadeDistance": 4150887048,
    "sphere": 953812642,
    "start": 2229020447,
    "startHour": 625204231,
    "startsLocked": 3204572347,
    "streamingExtentsMax": 2720965429,
    "streamingExtentsMin": 3710026271,
    "strength": 4280043047,
    "tangent": 2389642153,
    "template": 3202639186,
    "textureDictionary": 1976702369,
    "time": 258444835,
    "timeAndStateFlags": 3112418278,
    "timeCycleModifiers": 2946251737,
    "timeFlags": 2248791340,
    "timeTillPedLeaves": 213640539,
    "timecycleName": 2724323497,
    "tintValue": 1015358759,
    "top": 1281216666,
    "version": 1757576755,
    "verts": 120498671,
    "volIntensity": 689780512,
    "volOuterColour": 2283994062,
    "volOuterExponent": 2758849250,
    "volOuterIntensity": 3008198647,
    "volSizeScale": 2029533327,
    "volumeType": 4021175589,
    "volumetricFadeDistance": 2066998816,
    "x": 2466489829,
    "y": 2157248776,
    "z": 3059772574,
    # Extension enum value names
    "METAL_SOLID_LADDER": 1101797524,
    "METAL_LIGHT_LADDER": 846330484,
    "WOODEN_LADDER": 3202617440,
    "LIGHTSHAFT_DENSITYTYPE_CONSTANT": 676250331,
    "LIGHTSHAFT_DENSITYTYPE_SOFT": 2399586564,
    "LIGHTSHAFT_DENSITYTYPE_SOFT_SHADOW": 2057886646,
    "LIGHTSHAFT_DENSITYTYPE_SOFT_SHADOW_HD": 1816804348,
    "LIGHTSHAFT_DENSITYTYPE_LINEAR": 152140774,
    "LIGHTSHAFT_DENSITYTYPE_LINEAR_GRADIENT": 2088805984,
    "LIGHTSHAFT_DENSITYTYPE_QUADRATIC": 1098824079,
    "LIGHTSHAFT_DENSITYTYPE_QUADRATIC_GRADIENT": 1492299290,
    "LIGHTSHAFT_VOLUMETYPE_SHAFT": 665241531,
    "LIGHTSHAFT_VOLUMETYPE_CYLINDER": 462992848,
}

META_NAME_REVERSE = {value: key for key, value in META_NAME_MAP.items()}


def meta_name(name: str) -> int:
    if name in META_NAME_MAP:
        return META_NAME_MAP[name]
    value = jenk_hash(name)
    META_NAME_MAP[name] = value
    META_NAME_REVERSE.setdefault(value, name)
    return value


@dataclasses.dataclass(slots=True, frozen=True)
class FieldDef:
    name: str
    offset: int
    data_type: MetaDataType
    unknown_9h: int = 0
    reference_type_index: int = 0
    reference_key: int = 0

    @property
    def name_hash(self) -> int:
        return meta_name(self.name)


@dataclasses.dataclass(slots=True, frozen=True)
class StructDef:
    name: str
    key: int
    unknown: int
    size: int
    fields: tuple[FieldDef, ...] = ()
    opaque: bool = False

    @property
    def name_hash(self) -> int:
        return meta_name(self.name)


@dataclasses.dataclass(slots=True, frozen=True)
class EnumDef:
    name: str
    key: int
    items: tuple[tuple[str, int], ...]

    @property
    def name_hash(self) -> int:
        return meta_name(self.name)


KNOWN_ENUMS: dict[str, EnumDef] = {
    "rage__fwArchetypeDef__eAssetType": EnumDef(
        name="rage__fwArchetypeDef__eAssetType",
        key=1866031916,
        items=(
            ("ASSET_TYPE_UNINITIALIZED", 0),
            ("ASSET_TYPE_FRAGMENT", 1),
            ("ASSET_TYPE_DRAWABLE", 2),
            ("ASSET_TYPE_DRAWABLEDICTIONARY", 3),
            ("ASSET_TYPE_ASSETLESS", 4),
        ),
    ),
    "rage__eLodType": EnumDef(
        name="rage__eLodType",
        key=1856311430,
        items=(
            ("LODTYPES_DEPTH_HD", 0),
            ("LODTYPES_DEPTH_LOD", 1),
            ("LODTYPES_DEPTH_SLOD1", 2),
            ("LODTYPES_DEPTH_SLOD2", 3),
            ("LODTYPES_DEPTH_SLOD3", 4),
            ("LODTYPES_DEPTH_ORPHANHD", 5),
            ("LODTYPES_DEPTH_SLOD4", 6),
        ),
    ),
    "rage__ePriorityLevel": EnumDef(
        name="rage__ePriorityLevel",
        key=2200357711,
        items=(
            ("PRI_REQUIRED", 0),
            ("PRI_OPTIONAL_HIGH", 1),
            ("PRI_OPTIONAL_MEDIUM", 2),
            ("PRI_OPTIONAL_LOW", 3),
        ),
    ),
    "CExtensionDefLadderMaterialType": EnumDef(
        name="CExtensionDefLadderMaterialType",
        key=3514570158,
        items=(
            ("METAL_SOLID_LADDER", 0),
            ("METAL_LIGHT_LADDER", 1),
            ("WOODEN_LADDER", 2),
        ),
    ),
    "CExtensionDefLightShaftDensityType": EnumDef(
        name="CExtensionDefLightShaftDensityType",
        key=3539601182,
        items=(
            ("LIGHTSHAFT_DENSITYTYPE_CONSTANT", 0),
            ("LIGHTSHAFT_DENSITYTYPE_SOFT", 1),
            ("LIGHTSHAFT_DENSITYTYPE_SOFT_SHADOW", 2),
            ("LIGHTSHAFT_DENSITYTYPE_SOFT_SHADOW_HD", 3),
            ("LIGHTSHAFT_DENSITYTYPE_LINEAR", 4),
            ("LIGHTSHAFT_DENSITYTYPE_LINEAR_GRADIENT", 5),
            ("LIGHTSHAFT_DENSITYTYPE_QUADRATIC", 6),
            ("LIGHTSHAFT_DENSITYTYPE_QUADRATIC_GRADIENT", 7),
        ),
    ),
    "CExtensionDefLightShaftVolumeType": EnumDef(
        name="CExtensionDefLightShaftVolumeType",
        key=4287472345,
        items=(
            ("LIGHTSHAFT_VOLUMETYPE_SHAFT", 0),
            ("LIGHTSHAFT_VOLUMETYPE_CYLINDER", 1),
        ),
    ),
}


def _field(
    name: str,
    offset: int,
    data_type: MetaDataType,
    unknown_9h: int = 0,
    reference_type_index: int = 0,
    reference_key: str | int = 0,
) -> FieldDef:
    ref_key = meta_name(reference_key) if isinstance(reference_key, str) else reference_key
    return FieldDef(name, offset, data_type, unknown_9h, reference_type_index, ref_key)


KNOWN_STRUCTS: dict[str, StructDef] = {
    "CBlockDesc": StructDef(
        "CBlockDesc",
        2015795449,
        768,
        72,
        (
            _field("version", 0, MetaDataType.UNSIGNED_INT),
            _field("flags", 4, MetaDataType.UNSIGNED_INT),
            _field("name", 8, MetaDataType.CHAR_POINTER),
            _field("exportedBy", 24, MetaDataType.CHAR_POINTER),
            _field("owner", 40, MetaDataType.CHAR_POINTER),
            _field("time", 56, MetaDataType.CHAR_POINTER),
        ),
    ),
    "CTimeCycleModifier": StructDef(
        "CTimeCycleModifier",
        2683420777,
        1024,
        64,
        (
            _field("name", 8, MetaDataType.HASH),
            _field("minExtents", 16, MetaDataType.FLOAT_XYZ),
            _field("maxExtents", 32, MetaDataType.FLOAT_XYZ),
            _field("percentage", 48, MetaDataType.FLOAT),
            _field("range", 52, MetaDataType.FLOAT),
            _field("startHour", 56, MetaDataType.UNSIGNED_INT),
            _field("endHour", 60, MetaDataType.UNSIGNED_INT),
        ),
    ),
    "CCarGen": StructDef(
        "CCarGen",
        2345238261,
        1024,
        80,
        (
            _field("position", 16, MetaDataType.FLOAT_XYZ),
            _field("orientX", 32, MetaDataType.FLOAT),
            _field("orientY", 36, MetaDataType.FLOAT),
            _field("perpendicularLength", 40, MetaDataType.FLOAT),
            _field("carModel", 44, MetaDataType.HASH),
            _field("flags", 48, MetaDataType.UNSIGNED_INT),
            _field("bodyColorRemap1", 52, MetaDataType.SIGNED_INT),
            _field("bodyColorRemap2", 56, MetaDataType.SIGNED_INT),
            _field("bodyColorRemap3", 60, MetaDataType.SIGNED_INT),
            _field("bodyColorRemap4", 64, MetaDataType.SIGNED_INT),
            _field("popGroup", 68, MetaDataType.HASH),
            _field("livery", 72, MetaDataType.SIGNED_BYTE),
        ),
    ),
    "CEntityDef": StructDef(
        "CEntityDef",
        1825799514,
        1024,
        128,
        (
            _field("archetypeName", 8, MetaDataType.HASH),
            _field("flags", 12, MetaDataType.UNSIGNED_INT),
            _field("guid", 16, MetaDataType.UNSIGNED_INT),
            _field("position", 32, MetaDataType.FLOAT_XYZ),
            _field("rotation", 48, MetaDataType.FLOAT_XYZW),
            _field("scaleXY", 64, MetaDataType.FLOAT),
            _field("scaleZ", 68, MetaDataType.FLOAT),
            _field("parentIndex", 72, MetaDataType.SIGNED_INT),
            _field("lodDist", 76, MetaDataType.FLOAT),
            _field("childLodDist", 80, MetaDataType.FLOAT),
            _field("lodLevel", 84, MetaDataType.INT_ENUM, reference_key="rage__eLodType"),
            _field("numChildren", 88, MetaDataType.UNSIGNED_INT),
            _field("priorityLevel", 92, MetaDataType.INT_ENUM, reference_key="rage__ePriorityLevel"),
            FieldDef("extensions", 96, MetaDataType.ARRAY, 0, 13, 0),
            _field("ambientOcclusionMultiplier", 112, MetaDataType.SIGNED_INT),
            _field("artificialAmbientOcclusion", 116, MetaDataType.SIGNED_INT),
            _field("tintValue", 120, MetaDataType.UNSIGNED_INT),
        ),
    ),
    "CMloInstanceDef": StructDef(
        "CMloInstanceDef",
        2151576752,
        1024,
        160,
        (
            _field("archetypeName", 8, MetaDataType.HASH),
            _field("flags", 12, MetaDataType.UNSIGNED_INT),
            _field("guid", 16, MetaDataType.UNSIGNED_INT),
            _field("position", 32, MetaDataType.FLOAT_XYZ),
            _field("rotation", 48, MetaDataType.FLOAT_XYZW),
            _field("scaleXY", 64, MetaDataType.FLOAT),
            _field("scaleZ", 68, MetaDataType.FLOAT),
            _field("parentIndex", 72, MetaDataType.SIGNED_INT),
            _field("lodDist", 76, MetaDataType.FLOAT),
            _field("childLodDist", 80, MetaDataType.FLOAT),
            _field("lodLevel", 84, MetaDataType.INT_ENUM, reference_key="rage__eLodType"),
            _field("numChildren", 88, MetaDataType.UNSIGNED_INT),
            _field("priorityLevel", 92, MetaDataType.INT_ENUM, reference_key="rage__ePriorityLevel"),
            FieldDef("extensions", 96, MetaDataType.ARRAY, 0, 13, 0),
            _field("ambientOcclusionMultiplier", 112, MetaDataType.SIGNED_INT),
            _field("artificialAmbientOcclusion", 116, MetaDataType.SIGNED_INT),
            _field("tintValue", 120, MetaDataType.UNSIGNED_INT),
            _field("groupId", 128, MetaDataType.UNSIGNED_INT),
            _field("floorId", 132, MetaDataType.UNSIGNED_INT),
            FieldDef("defaultEntitySets", 136, MetaDataType.ARRAY, 0, 20, 0),
            _field("numExitPortals", 152, MetaDataType.UNSIGNED_INT),
            _field("MLOInstflags", 156, MetaDataType.UNSIGNED_INT),
        ),
    ),
    "BoxOccluder": StructDef(
        "BoxOccluder",
        1831736438,
        256,
        16,
        (
            _field("iCenterX", 0, MetaDataType.SIGNED_SHORT),
            _field("iCenterY", 2, MetaDataType.SIGNED_SHORT),
            _field("iCenterZ", 4, MetaDataType.SIGNED_SHORT),
            _field("iCosZ", 6, MetaDataType.SIGNED_SHORT),
            _field("iLength", 8, MetaDataType.SIGNED_SHORT),
            _field("iWidth", 10, MetaDataType.SIGNED_SHORT),
            _field("iHeight", 12, MetaDataType.SIGNED_SHORT),
            _field("iSinZ", 14, MetaDataType.SIGNED_SHORT),
        ),
    ),
    "OccludeModel": StructDef(
        "OccludeModel",
        1172796107,
        1024,
        64,
        (
            _field("bmin", 0, MetaDataType.FLOAT_XYZ),
            _field("bmax", 16, MetaDataType.FLOAT_XYZ),
            _field("dataSize", 32, MetaDataType.UNSIGNED_INT),
            FieldDef("verts", 40, MetaDataType.DATA_BLOCK_POINTER, 4, 3, 2),
            _field("numVertsInBytes", 48, MetaDataType.UNSIGNED_SHORT),
            _field("numTris", 50, MetaDataType.UNSIGNED_SHORT),
            _field("flags", 52, MetaDataType.UNSIGNED_INT),
        ),
    ),
    "CLODLight": StructDef("CLODLight", 2325189228, 768, 136),
    "CDistantLODLight": StructDef("CDistantLODLight", 2820908419, 768, 48),
    "rage__fwInstancedMapData": StructDef("rage__fwInstancedMapData", 1836780118, 768, 48, opaque=True),
    "CMapData": StructDef("CMapData", 3448101671, 1024, 512),
    "CMapTypes": StructDef("CMapTypes", 2608875220, 768, 80),
    "CBaseArchetypeDef": StructDef("CBaseArchetypeDef", 2411387556, 1024, 144),
    "CTimeArchetypeDef": StructDef("CTimeArchetypeDef", 2520619910, 1024, 160),
    "CMloArchetypeDef": StructDef("CMloArchetypeDef", 937664754, 1024, 240),
    "CMloRoomDef": StructDef("CMloRoomDef", 3885428245, 1024, 112),
    "CMloPortalDef": StructDef("CMloPortalDef", 1110221513, 768, 64),
    "CMloEntitySet": StructDef("CMloEntitySet", 4180211587, 768, 48),
    "CMloTimeCycleModifier": StructDef("CMloTimeCycleModifier", 838874674, 1024, 48),
    "CCompositeEntityType": StructDef("CCompositeEntityType", 659539004, 1024, 304, opaque=True),
}

STRUCTS_BY_HASH = {value.name_hash: value for value in KNOWN_STRUCTS.values()}
ENUMS_BY_HASH = {value.name_hash: value for value in KNOWN_ENUMS.values()}

