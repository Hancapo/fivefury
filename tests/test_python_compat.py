from __future__ import annotations

import ast
from pathlib import Path

from fivefury.hashing import jenk_hash, jenk_partial_hash


def test_native_hash_bindings_accept_unicode_on_supported_python_versions() -> None:
    assert jenk_hash("FloatXYZ") == 0x93996598
    assert jenk_partial_hash("FloatXYZ") == 0x8AC1F1BF


def test_slotted_dataclasses_do_not_use_zero_argument_super() -> None:
    package_root = Path(__file__).parents[1] / "fivefury"
    offenders: list[str] = []

    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_slotted_dataclass(node):
                continue
            for child in ast.walk(node):
                if _is_zero_argument_super(child):
                    offenders.append(
                        f"{path.relative_to(package_root)}:{child.lineno}:{node.name}"
                    )

    assert offenders == []


def _is_slotted_dataclass(node: ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        name = getattr(decorator.func, "id", None) or getattr(
            decorator.func, "attr", None
        )
        if name != "dataclass":
            continue
        return any(
            keyword.arg == "slots"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in decorator.keywords
        )
    return False


def _is_zero_argument_super(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "super"
        and not node.args
        and not node.keywords
    )
