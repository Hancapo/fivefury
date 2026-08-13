from __future__ import annotations

from pathlib import Path

from .model import CutFile, CutSummary
from .pso import read_cut


def analyze_cut(data: CutFile | bytes | str | Path) -> CutSummary:
    cut = data if isinstance(data, CutFile) else read_cut(data)
    return cut.summary()
