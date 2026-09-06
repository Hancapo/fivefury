"""Shared test infrastructure; format-specific samples stay with their tests."""

from .files import touch, write_bytes
from .paths import configured_path, reference_root, require_reference, retail_games
from .processes import run_python

__all__ = [
    "configured_path",
    "reference_root",
    "require_reference",
    "retail_games",
    "run_python",
    "touch",
    "write_bytes",
]
