from __future__ import annotations

import dataclasses
from collections.abc import MutableMapping
from typing import Any


_EXPRESSION_SET_NAME = ("ExpressionSetName", "expressionSetName", "0x8C3B174C")
_EXPRESSION_DICTIONARY_NAME = ("ExpressionDictionaryName", "expressionDictionaryName", "0x414D9B0B")


@dataclasses.dataclass(slots=True)
class YedPedExpressionBinding:
    expression_set_name: str = ""
    expression_dictionary_name: str = ""

    @property
    def has_expression_dictionary(self) -> bool:
        return bool(self.expression_dictionary_name)


def _mapping_root(value: object) -> MutableMapping[str, Any] | None:
    root = getattr(value, "root_value", value)
    return root if isinstance(root, MutableMapping) else None


def _get(mapping: MutableMapping[str, Any], names: tuple[str, ...], default: Any = "") -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return default


def _set(mapping: MutableMapping[str, Any], names: tuple[str, ...], value: Any) -> None:
    for name in names:
        if name in mapping:
            mapping[name] = value
            return
    mapping[names[0]] = value


def get_ped_expression_binding(ymt: object) -> YedPedExpressionBinding:
    root = _mapping_root(ymt)
    if root is None:
        raise TypeError("ped expression binding requires a decoded YMT mapping")
    return YedPedExpressionBinding(
        expression_set_name=str(_get(root, _EXPRESSION_SET_NAME, "")),
        expression_dictionary_name=str(_get(root, _EXPRESSION_DICTIONARY_NAME, "")),
    )


def set_ped_expression_binding(
    ymt: object,
    *,
    expression_set_name: str | None = None,
    expression_dictionary_name: str | None = None,
) -> object:
    root = _mapping_root(ymt)
    if root is None:
        raise TypeError("ped expression binding requires a decoded YMT mapping")
    if expression_set_name is not None:
        _set(root, _EXPRESSION_SET_NAME, str(expression_set_name))
    if expression_dictionary_name is not None:
        _set(root, _EXPRESSION_DICTIONARY_NAME, str(expression_dictionary_name))
    return ymt


__all__ = [
    "YedPedExpressionBinding",
    "get_ped_expression_binding",
    "set_ped_expression_binding",
]
