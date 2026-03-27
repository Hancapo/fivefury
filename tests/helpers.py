from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class ResolvedSymbol:
    module_name: str
    symbol_name: str
    value: Any


def import_module_candidates(module_names: Sequence[str]) -> Any | None:
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
    return None


def resolve_symbol(
    module_names: Sequence[str],
    symbol_names: Sequence[str],
) -> ResolvedSymbol | None:
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        for symbol_name in symbol_names:
            if hasattr(module, symbol_name):
                return ResolvedSymbol(module_name, symbol_name, getattr(module, symbol_name))
    return None


def call_if_present(obj: Any, method_names: Sequence[str], *args: Any, **kwargs: Any) -> Any:
    for method_name in method_names:
        method = getattr(obj, method_name, None)
        if callable(method):
            return method(*args, **kwargs)
    raise AttributeError(f"No callable method found in {method_names!r}")


def touch(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
