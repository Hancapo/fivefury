from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from itertools import islice
from pathlib import Path

from ..gamefile import GameFileType
from .model import Yed, YedValidationIssue, validate_yed
from .reader import read_yed


@dataclasses.dataclass(slots=True)
class YedAuditReport:
    path: str = ""
    expression_count: int = 0
    stream_count: int = 0
    instruction_count: int = 0
    unresolved_instruction_count: int = 0
    opcodes: dict[str, int] = dataclasses.field(default_factory=dict)
    issues: list[YedValidationIssue] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues and self.unresolved_instruction_count == 0


def audit_yed(yed: Yed, *, skeleton: object | None = None) -> YedAuditReport:
    report = YedAuditReport(
        path=yed.path,
        expression_count=len(yed.expressions),
        issues=validate_yed(yed, skeleton=skeleton),
    )
    for expression in yed.expressions:
        report.stream_count += len(expression.streams)
        for stream in expression.streams:
            report.instruction_count += len(stream.instructions)
            for instruction in stream.instructions:
                report.opcodes[instruction.name] = (
                    report.opcodes.get(instruction.name, 0) + 1
                )
                if not instruction.parsed:
                    report.unresolved_instruction_count += 1
    return report


def audit_yed_file(
    path: str | Path,
    *,
    skeleton: object | None = None,
) -> YedAuditReport:
    yed = read_yed(path)
    return audit_yed(yed, skeleton=skeleton)


def iter_yed_files(paths: Iterable[str | Path]) -> Iterable[Path]:
    for path in paths:
        current = Path(path)
        if current.is_dir():
            yield from current.rglob("*.yed")
        elif current.suffix.lower() == ".yed":
            yield current


def audit_yed_paths(
    paths: Iterable[str | Path],
    *,
    skeleton: object | None = None,
) -> list[YedAuditReport]:
    reports: list[YedAuditReport] = []
    for path in iter_yed_files(paths):
        try:
            reports.append(audit_yed_file(path, skeleton=skeleton))
        except Exception as exc:  # noqa: BLE001 - audits record malformed inputs.
            reports.append(
                YedAuditReport(
                    path=str(path),
                    issues=[
                        YedValidationIssue(
                            "read-error",
                            f"could not read YED: {exc}",
                        )
                    ],
                )
            )
    return reports


def audit_yed_cache(
    cache: object,
    *,
    skeleton: object | None = None,
    limit: int | None = None,
) -> list[YedAuditReport]:
    reports: list[YedAuditReport] = []
    assets = cache.iter_assets(GameFileType.YED)
    if limit is not None:
        assets = islice(assets, max(limit, 0))
    for asset in assets:
        try:
            game_file = cache.load_asset(asset)
            if game_file is None:
                raise ValueError("asset could not be loaded")
            if game_file.kind is not GameFileType.YED:
                raise ValueError(f"asset decoded as {game_file.kind.name}, not YED")
            parsed = game_file.parsed
            if not isinstance(parsed, Yed):
                raise TypeError("asset did not decode to Yed")
            reports.append(audit_yed(parsed, skeleton=skeleton))
        except Exception as exc:  # noqa: BLE001 - audits record malformed inputs.
            reports.append(
                YedAuditReport(
                    path=str(getattr(asset, "path", "")),
                    issues=[
                        YedValidationIssue(
                            "read-error",
                            f"could not read YED from cache: {exc}",
                        )
                    ],
                )
            )
    return reports


__all__ = [
    "YedAuditReport",
    "audit_yed",
    "audit_yed_cache",
    "audit_yed_file",
    "audit_yed_paths",
    "iter_yed_files",
]
