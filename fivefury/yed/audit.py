from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Iterable

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
    report = YedAuditReport(path=yed.path, expression_count=len(yed.expressions), issues=validate_yed(yed, skeleton=skeleton))
    for expression in yed.expressions:
        report.stream_count += len(expression.streams)
        for stream in expression.streams:
            report.instruction_count += len(stream.instructions)
            for instruction in stream.instructions:
                report.opcodes[instruction.name] = report.opcodes.get(instruction.name, 0) + 1
                if not instruction.parsed:
                    report.unresolved_instruction_count += 1
    return report


def audit_yed_file(path: str | Path, *, skeleton: object | None = None) -> YedAuditReport:
    yed = read_yed(path)
    return audit_yed(yed, skeleton=skeleton)


def iter_yed_files(paths: Iterable[str | Path]) -> Iterable[Path]:
    for path in paths:
        current = Path(path)
        if current.is_dir():
            yield from current.rglob("*.yed")
        elif current.suffix.lower() == ".yed":
            yield current


def audit_yed_paths(paths: Iterable[str | Path], *, skeleton: object | None = None) -> list[YedAuditReport]:
    reports: list[YedAuditReport] = []
    for path in iter_yed_files(paths):
        try:
            reports.append(audit_yed_file(path, skeleton=skeleton))
        except Exception as exc:
            reports.append(
                YedAuditReport(
                    path=str(path),
                    issues=[YedValidationIssue("read-error", f"could not read YED: {exc}")],
                )
            )
    return reports


def audit_yed_cache(cache: object, *, skeleton: object | None = None, limit: int | None = None) -> list[YedAuditReport]:
    reports: list[YedAuditReport] = []
    yed_assets = list(getattr(cache, "YedDict", {}).values())
    for asset in yed_assets[:limit]:
        try:
            game_file = cache.get_file(asset)
            if game_file is None or game_file.kind is not GameFileType.YED:
                continue
            parsed = game_file.parsed
            if isinstance(parsed, Yed):
                reports.append(audit_yed(parsed, skeleton=skeleton))
        except Exception as exc:
            reports.append(
                YedAuditReport(
                    path=str(getattr(asset, "path", "")),
                    issues=[YedValidationIssue("read-error", f"could not read YED from cache: {exc}")],
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
