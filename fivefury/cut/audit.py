from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from ..common import JsonReport
from ..gamefile import GameFileType
from .resolution.runtime import (
    CutsceneResolutionCancellation,
    CutsceneResolutionCancelled,
    CutsceneResolutionTrace,
    check_cutscene_resolution_cancelled,
)

if TYPE_CHECKING:
    from ..cache import AssetRecord, GameFileCache


@dataclass(slots=True, frozen=True)
class CutsceneAuditEntry:
    path: str
    elapsed_seconds: float
    binding_count: int = 0
    section_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    exception: str | None = None
    trace: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.exception is None and self.error_count == 0


@dataclass(slots=True)
class CutsceneAuditReport(JsonReport):
    root: str | None
    started_at: float
    elapsed_seconds: float = 0.0
    entries: list[CutsceneAuditEntry] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def passed(self) -> int:
        return sum(entry.ok for entry in self.entries)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "started_at": self.started_at,
            "elapsed_seconds": self.elapsed_seconds,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "entries": [asdict(entry) | {"ok": entry.ok} for entry in self.entries],
        }

def audit_cutscene_resolution(
    cache: GameFileCache,
    assets: Iterable[AssetRecord] | None = None,
    *,
    subtitle_language: str = "american",
    include_traces: bool = False,
    cancellation: CutsceneResolutionCancellation | None = None,
    progress: Callable[[int, int, CutsceneAuditEntry], None] | None = None,
) -> CutsceneAuditReport:
    selected = list(
        cache.iter_assets(kind=GameFileType.CUT) if assets is None else assets
    )
    started = time.perf_counter()
    report = CutsceneAuditReport(
        root=str(cache.root) if cache.root is not None else None,
        started_at=time.time(),
    )
    for index, asset in enumerate(selected, start=1):
        check_cutscene_resolution_cancelled(cancellation)
        trace = CutsceneResolutionTrace(source=asset.path)
        try:
            bundle = cache.resolve_cutscene(
                asset,
                subtitle_language=subtitle_language,
                cancellation=cancellation,
                trace=trace,
            )
            entry = CutsceneAuditEntry(
                path=asset.path,
                elapsed_seconds=trace.elapsed_seconds,
                binding_count=len(bundle.bindings),
                section_count=len(bundle.ycd_by_section),
                warning_count=sum(issue.severity == "warning" for issue in bundle.issues),
                error_count=sum(issue.severity == "error" for issue in bundle.issues),
                trace=trace.to_dict() if include_traces else None,
            )
        except CutsceneResolutionCancelled:
            trace.finish()
            raise
        except Exception as exc:  # noqa: BLE001
            trace.finish()
            entry = CutsceneAuditEntry(
                path=asset.path,
                elapsed_seconds=trace.elapsed_seconds,
                exception=f"{type(exc).__name__}: {exc}",
                trace=trace.to_dict() if include_traces else None,
            )
        report.entries.append(entry)
        if progress is not None:
            progress(index, len(selected), entry)
    report.elapsed_seconds = time.perf_counter() - started
    return report


def benchmark_cutscene_resolution(
    cache: GameFileCache,
    query: Any,
    *,
    iterations: int = 5,
    clear_loaded_files: bool = False,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> list[CutsceneResolutionTrace]:
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero")
    traces: list[CutsceneResolutionTrace] = []
    for _ in range(iterations):
        check_cutscene_resolution_cancelled(cancellation)
        if clear_loaded_files:
            cache.clear_runtime_cache(loaded_files=True)
        trace = CutsceneResolutionTrace()
        cache.resolve_cutscene(query, cancellation=cancellation, trace=trace)
        traces.append(trace)
    return traces


__all__ = [
    "CutsceneAuditEntry",
    "CutsceneAuditReport",
    "audit_cutscene_resolution",
    "benchmark_cutscene_resolution",
]
