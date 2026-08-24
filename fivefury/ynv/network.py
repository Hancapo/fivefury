from __future__ import annotations

import dataclasses

from ..authoring.context import BuildContext
from ..authoring.diagnostics import ValidationReport
from .model import Ynv, YnvPoly

_NULL_AREA_ID = 0x3FFF
_NULL_POLY_ID = 0x7FFF


def _asset_label(cell: Ynv) -> str:
    return cell.path or f"ynv[area_id={int(cell.area_id)}]"


def _poly_edge_span(cell: Ynv, poly: YnvPoly) -> tuple[int, int] | None:
    start = int(poly.index_id)
    count = int(poly.index_count)
    end = start + count
    if start < 0 or count < 0 or end > len(cell.edges):
        return None
    return start, end


def _edge_label(
    source_area: int,
    source_poly: int,
    target_area: int,
    target_poly: int,
) -> str:
    return (
        f"({source_area}, {source_poly}) -> "
        f"({target_area}, {target_poly})"
    )


@dataclasses.dataclass(slots=True)
class YnvNetwork:
    cells: list[Ynv] = dataclasses.field(default_factory=list)

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        report = ValidationReport()
        cells_by_area: dict[int, list[Ynv]] = {}

        for cell in self.cells:
            asset = _asset_label(cell)
            report.extend(cell.validate(context=context), asset=asset)
            cells_by_area.setdefault(int(cell.area_id), []).append(cell)

        duplicate_areas = {
            area_id for area_id, cells in cells_by_area.items() if len(cells) > 1
        }
        for area_id in sorted(duplicate_areas):
            cells = cells_by_area[area_id]
            declarations = ", ".join(_asset_label(cell) for cell in cells)
            for cell in cells:
                report.issue(
                    "ynv.network.area_id.duplicate",
                    f"Area {area_id} is declared by multiple YNV cells: {declarations}",
                    asset=_asset_label(cell),
                    path="area_id",
                )

        area_index = {
            area_id: cells[0]
            for area_id, cells in cells_by_area.items()
            if area_id not in duplicate_areas
        }
        for source in self.cells:
            source_area = int(source.area_id)
            if source_area in duplicate_areas:
                continue
            asset = _asset_label(source)
            for source_poly_id, source_poly in enumerate(source.polys):
                source_span = _poly_edge_span(source, source_poly)
                if source_span is None:
                    continue
                for edge_index in range(*source_span):
                    edge = source.edges[edge_index]
                    target_area = int(edge.poly1.area_id)
                    target_poly_id = int(edge.poly1.poly_id)
                    if (
                        target_area == _NULL_AREA_ID
                        and target_poly_id == _NULL_POLY_ID
                    ):
                        continue

                    edge_offset = edge_index - source_span[0]
                    path = f"polys[{source_poly_id}].edges[{edge_offset}]"
                    target = area_index.get(target_area)
                    if target is None:
                        if target_area not in duplicate_areas:
                            label = _edge_label(
                                source_area,
                                source_poly_id,
                                target_area,
                                target_poly_id,
                            )
                            report.issue(
                                "ynv.network.edge.target_area.missing",
                                f"Edge {label} references an area absent from the network",
                                asset=asset,
                                path=path,
                            )
                        continue
                    if not 0 <= target_poly_id < len(target.polys):
                        label = _edge_label(
                            source_area,
                            source_poly_id,
                            target_area,
                            target_poly_id,
                        )
                        report.issue(
                            "ynv.network.edge.target_poly_id.range",
                            f"Edge {label} references a polygon outside the target area's {len(target.polys)} polygons",
                            asset=asset,
                            path=path,
                        )
                        continue

                    target_span = _poly_edge_span(
                        target,
                        target.polys[target_poly_id],
                    )
                    reciprocal_count = (
                        0
                        if target_span is None
                        else sum(
                            int(target.edges[index].poly1.area_id) == source_area
                            and int(target.edges[index].poly1.poly_id)
                            == source_poly_id
                            for index in range(*target_span)
                        )
                    )
                    if reciprocal_count == 0:
                        label = _edge_label(
                            source_area,
                            source_poly_id,
                            target_area,
                            target_poly_id,
                        )
                        report.issue(
                            "ynv.network.edge.reciprocal.missing",
                            f"Edge {label} has no reciprocal edge in the target polygon",
                            asset=asset,
                            path=path,
                        )
                    elif reciprocal_count > 1:
                        label = _edge_label(
                            source_area,
                            source_poly_id,
                            target_area,
                            target_poly_id,
                        )
                        report.issue(
                            "ynv.network.edge.reciprocal.duplicate",
                            f"Edge {label} has {reciprocal_count} reciprocal edges in the target polygon",
                            asset=asset,
                            path=path,
                        )

        return report


__all__ = ["YnvNetwork"]
