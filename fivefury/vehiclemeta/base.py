from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ..common import atomic_write_bytes

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from ..authoring import BuildContext, ValidationReport


class VehicleMetaModel:
    __slots__ = ()

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        from .validation import validate_vehicle_meta_model

        return validate_vehicle_meta_model(self, context=context)


class VehicleMetaDocument(VehicleMetaModel):
    __slots__ = ()

    ROOT_TAG: ClassVar[str]

    def to_xml_element(self) -> ET.Element:
        from .xml_authoring import vehicle_meta_xml_element

        return vehicle_meta_xml_element(self)

    def to_bytes(
        self,
        *,
        context: BuildContext | None = None,
        validate: bool = True,
    ) -> bytes:
        from ..xml import xml_bytes

        if validate:
            self.validate(context=context).raise_for_errors()
        return xml_bytes(self.to_xml_element())

    def save(
        self,
        path: str | Path,
        *,
        context: BuildContext | None = None,
        validate: bool = True,
    ) -> Path:
        return atomic_write_bytes(
            path,
            self.to_bytes(context=context, validate=validate),
        )


def without_raw(model: Any, **changes: Any) -> Any:
    import dataclasses

    return dataclasses.replace(model, raw=None, **changes)


__all__ = ["VehicleMetaDocument", "VehicleMetaModel", "without_raw"]
