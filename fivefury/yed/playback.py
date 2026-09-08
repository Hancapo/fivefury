from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .._native import NativeYedProgram
from ..authoring.diagnostics import Diagnostic
from ..vector import Vector4
from .evaluate import (
    DofKey,
    VariableKey,
    YedEvaluationIssue,
    YedEvaluationResult,
    _evaluate_program,
    _native_attachment_diagnostics,
    _program_signature,
    _resolve_expressions,
)

if TYPE_CHECKING:
    from .model import Yed


@dataclass(frozen=True, slots=True, init=False)
class YedEvaluator:
    """Owned immutable program/defaults snapshot with no implicit frame state."""

    expression_names: tuple[str, ...]
    _program: NativeYedProgram
    _issues: tuple[YedEvaluationIssue, ...]
    _diagnostics: tuple[Diagnostic, ...]

    def __init__(
        self,
        yed: Yed,
        expression_names: Iterable[str | int],
        *,
        skeleton: object | None = None,
    ):
        expressions, issues = _resolve_expressions(yed, tuple(expression_names))
        object.__setattr__(
            self, "expression_names", tuple(e.short_name for e in expressions)
        )
        object.__setattr__(
            self,
            "_program",
            NativeYedProgram(*_program_signature(expressions, skeleton)),
        )
        object.__setattr__(self, "_issues", tuple(issues))
        object.__setattr__(
            self, "_diagnostics", _native_attachment_diagnostics(expressions)
        )

    def evaluate(
        self,
        tracks: Mapping[DofKey, object],
        *,
        time: float = 0.0,
        delta_time: float = 0.0,
        variables: MutableMapping[VariableKey, Vector4] | None = None,
    ) -> YedEvaluationResult:
        return _evaluate_program(
            self._program,
            self.expression_names,
            self._issues,
            self._diagnostics,
            tracks,
            time=time,
            delta_time=delta_time,
            variables=variables,
        )
