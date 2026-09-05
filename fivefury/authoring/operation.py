from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Event


class AuthoringStage(StrEnum):
    BUILD = "build"
    VALIDATE = "validate"
    WRITE = "write"


@dataclass(frozen=True, slots=True)
class AuthoringProgress:
    stage: AuthoringStage
    asset: str
    completed: int
    total: int


class AuthoringCancelled(RuntimeError):
    """An authoring operation was cancelled before its next unit of work."""


class AuthoringOperation:
    """Thread-safe cancellation with synchronous, optional progress delivery.

    Progress callbacks execute on the authoring thread, not a UI thread.
    Cancellation is cooperative and never interrupts an atomic file replacement.
    """

    def __init__(
        self, progress: Callable[[AuthoringProgress], None] | None = None
    ) -> None:
        self.progress = progress
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def checkpoint(self, progress: AuthoringProgress | None = None) -> None:
        if self._cancelled.is_set():
            raise AuthoringCancelled("Authoring operation cancelled")
        if progress is not None and self.progress is not None:
            self.progress(progress)
            if self._cancelled.is_set():
                raise AuthoringCancelled("Authoring operation cancelled")
