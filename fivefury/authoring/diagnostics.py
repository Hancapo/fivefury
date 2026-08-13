from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from inspect import signature
from pathlib import Path
from typing import Any


class DiagnosticSeverity(IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    asset: str | None = None
    path: str | None = None

    def at(self, path: str) -> Diagnostic:
        return Diagnostic(
            code=self.code,
            message=self.message,
            severity=self.severity,
            asset=self.asset,
            path=path,
        )

    def for_asset(self, asset: str | Path) -> Diagnostic:
        return Diagnostic(
            code=self.code,
            message=self.message,
            severity=self.severity,
            asset=str(asset),
            path=self.path,
        )


@dataclass(slots=True)
class ValidationReport:
    issues: list[Diagnostic] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.issues)

    def __iter__(self):
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity >= DiagnosticSeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.severity == DiagnosticSeverity.WARNING
        )

    @property
    def valid(self) -> bool:
        return not self.errors

    def issue(
        self,
        code: str,
        message: str,
        *,
        severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
        asset: str | None = None,
        path: str | None = None,
    ) -> Diagnostic:
        diagnostic = Diagnostic(code, message, severity, asset, path)
        self.issues.append(diagnostic)
        return diagnostic

    def extend(
        self, diagnostics: ValidationReport | list[Diagnostic] | tuple[Diagnostic, ...]
    ) -> ValidationReport:
        self.issues.extend(
            diagnostics.issues
            if isinstance(diagnostics, ValidationReport)
            else diagnostics
        )
        return self

    def raise_for_errors(self) -> None:
        if self.valid:
            return
        lines = [
            f"{issue.asset + ': ' if issue.asset else ''}{issue.path + ': ' if issue.path else ''}"
            f"[{issue.code}] {issue.message}"
            for issue in self.errors
        ]
        raise ValidationError("Validation failed:\n- " + "\n- ".join(lines), self)


class ValidationError(ValueError):
    def __init__(self, message: str, report: ValidationReport) -> None:
        super().__init__(message)
        self.report = report


def validation_report(
    asset: Any,
    *,
    context: Any | None = None,
) -> ValidationReport:
    validator = getattr(asset, "validate", None)
    if validator is None:
        raise TypeError(f"{type(asset).__name__} does not expose validate()")

    parameters = signature(validator).parameters
    result = validator(context=context) if "context" in parameters else validator()
    if isinstance(result, ValidationReport):
        return result

    report = ValidationReport()
    code = f"{type(asset).__name__.lower()}.invalid"
    for issue in result or ():
        if isinstance(issue, Diagnostic):
            report.issues.append(issue)
        elif isinstance(issue, str):
            report.issue(code, issue)
        else:
            raise TypeError(
                f"{type(asset).__name__}.validate() returned unsupported "
                f"diagnostic type {type(issue).__name__}"
            )
    return report


__all__ = [
    "Diagnostic",
    "DiagnosticSeverity",
    "ValidationError",
    "ValidationReport",
    "validation_report",
]
