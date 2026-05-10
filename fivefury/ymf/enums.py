from __future__ import annotations

import dataclasses
from enum import IntEnum, IntFlag
from typing import Any

from ..metahash import MetaHash


class PackFileMetaDataAssetType(IntEnum):
    AT_TXD = 0
    AT_DRB = 1
    AT_DWD = 2
    AT_FRG = 3


class PackFileMetaDataImapGroupType(IntFlag):
    NONE = 0
    TIME_DEPENDENT = 1
    WEATHER_DEPENDENT = 2


class ManifestFlags(IntFlag):
    NONE = 0
    INTERIOR_DATA = 1


class YmfRelationshipType(IntEnum):
    IMAP_TO_ITYP = 1
    ITYP_TO_ITYP = 2
    IMAP_GROUP_TO_BOUND = 3
    INTERIOR_TO_BOUND = 4
    HD_TXD_BINDING = 5
    LEGACY_IMAP_TO_ITYP = 6


@dataclasses.dataclass(slots=True, frozen=True)
class YmfRelationship:
    kind: YmfRelationshipType
    source: MetaHash
    target: MetaHash
    flags: ManifestFlags = ManifestFlags.NONE
    source_index: int = -1
    target_index: int = -1
    data: Any = None
