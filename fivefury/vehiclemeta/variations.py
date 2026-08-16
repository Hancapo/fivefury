from __future__ import annotations

import dataclasses
from typing import Any

from ..metahash import MetaHash
from ..pso_values import field, items, meta_hash, number, text
from .base import VehicleMetaDocument, VehicleMetaModel, without_raw


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleColorIndices(VehicleMetaModel):
    indices: list[int] = dataclasses.field(default_factory=list)
    liveries: list[bool] = dataclasses.field(default_factory=list)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleColorIndices:
        return cls(
            indices=[int(item) for item in items(value, "m_indices", "indices")],
            liveries=[bool(item) for item in items(value, "m_liveries", "liveries")],
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class LicensePlateProbability(VehicleMetaModel):
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    weight: int = 1
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> LicensePlateProbability:
        return cls(
            name=meta_hash(field(value, "m_Name", "Name", "name")),
            weight=number(field(value, "m_Value", "Value", "value"), 1),
            raw=value,
        )


def plate_probabilities(value: Any) -> list[LicensePlateProbability]:
    return [
        LicensePlateProbability.from_value(item)
        for item in items(value, "m_Probabilities", "Probabilities", "probabilities")
    ]


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleVariation(VehicleMetaModel):
    model_name: str = ""
    colors: list[VehicleColorIndices] = dataclasses.field(default_factory=list)
    kits: list[MetaHash] = dataclasses.field(default_factory=list)
    windows_with_exposed_edges: list[MetaHash] = dataclasses.field(default_factory=list)
    plate_probabilities: list[LicensePlateProbability] = dataclasses.field(
        default_factory=list
    )
    light_settings: int = 0xFF
    siren_settings: int = 0xFF
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleVariation:
        return cls(
            model_name=text(field(value, "m_modelName", "modelName")),
            colors=[
                VehicleColorIndices.from_value(item)
                for item in items(value, "m_colors", "colors")
            ],
            kits=[meta_hash(item) for item in items(value, "m_kits", "kits")],
            windows_with_exposed_edges=[
                meta_hash(item)
                for item in items(
                    value, "m_windowsWithExposedEdges", "windowsWithExposedEdges"
                )
            ],
            plate_probabilities=plate_probabilities(
                field(value, "m_plateProbabilities", "plateProbabilities")
            ),
            light_settings=number(
                field(value, "m_lightSettings", "lightSettings"), 0xFF
            ),
            siren_settings=number(
                field(value, "m_sirenSettings", "sirenSettings"), 0xFF
            ),
            raw=value,
        )

    def clone_as(self, model_name: str) -> VehicleVariation:
        return without_raw(self, model_name=model_name)


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleModelInfoVariation(VehicleMetaDocument):
    ROOT_TAG = "CVehicleModelInfoVariation"
    vehicles: list[VehicleVariation] = dataclasses.field(default_factory=list)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleModelInfoVariation:
        return cls(
            vehicles=[
                VehicleVariation.from_value(item)
                for item in items(value, "m_variationData", "variationData")
            ],
            raw=value,
        )

    def get(self, model_name: str) -> VehicleVariation | None:
        target = model_name.casefold()
        return next(
            (
                vehicle
                for vehicle in self.vehicles
                if vehicle.model_name.casefold() == target
            ),
            None,
        )


__all__ = [
    "LicensePlateProbability",
    "VehicleColorIndices",
    "VehicleModelInfoVariation",
    "VehicleVariation",
    "plate_probabilities",
]
