from __future__ import annotations

from pathlib import Path

from .model import CutFile, CutSummary
from .pso import read_cut
from .xml import read_cutxml


def analyze_cut(data: CutFile | bytes | str | Path) -> CutSummary:
    if isinstance(data, CutFile):
        cut = data
    else:
        path = Path(data) if isinstance(data, (str, Path)) else None
        if path is not None and path.suffix.lower() == ".cutxml":
            cut = read_cutxml(path)
        else:
            cut = read_cut(data)
    return cut.summary()
