from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class CutsceneResolutionCancelled(RuntimeError):
    pass


class CutsceneResolutionCancellation:
    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def check(self) -> None:
        if self.cancelled:
            raise CutsceneResolutionCancelled("CUT dependency resolution was cancelled")


@dataclass(slots=True, frozen=True)
class CutsceneResolutionSpan:
    name: str
    started_ns: int
    elapsed_ns: int

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_ns / 1_000_000_000.0


@dataclass(slots=True)
class CutsceneResolutionTrace:
    source: str = ""
    started_ns: int = field(default_factory=time.perf_counter_ns)
    elapsed_ns: int = 0
    spans: list[CutsceneResolutionSpan] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_ns / 1_000_000_000.0

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        started_ns = time.perf_counter_ns()
        try:
            yield
        finally:
            self.spans.append(
                CutsceneResolutionSpan(
                    name=str(name),
                    started_ns=started_ns - self.started_ns,
                    elapsed_ns=time.perf_counter_ns() - started_ns,
                )
            )

    def finish(self) -> None:
        self.elapsed_ns = time.perf_counter_ns() - self.started_ns

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "elapsed_ns": self.elapsed_ns,
            "elapsed_seconds": self.elapsed_seconds,
            "spans": [
                {
                    **asdict(span),
                    "elapsed_seconds": span.elapsed_seconds,
                }
                for span in self.spans
            ],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def save_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_json() + "\n", encoding="utf-8")
        return destination


def check_cutscene_resolution_cancelled(
    cancellation: CutsceneResolutionCancellation | None,
) -> None:
    if cancellation is not None:
        cancellation.check()


__all__ = [
    "CutsceneResolutionCancellation",
    "CutsceneResolutionCancelled",
    "CutsceneResolutionSpan",
    "CutsceneResolutionTrace",
    "check_cutscene_resolution_cancelled",
]
