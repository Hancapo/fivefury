from __future__ import annotations

import dataclasses
from collections.abc import MutableMapping
from typing import Any

_EXPRESSION_SET_NAME = (
    "ExpressionSetName",
    "expressionSetName",
    "0x8C3E474C",
    "hash_8C3E474C",
)
_EXPRESSION_DICTIONARY_NAME = (
    "ExpressionDictionaryName",
    "expressionDictionaryName",
    "0x68EFE1B7",
    "hash_68EFE1B7",
)
_EXPRESSION_NAME = (
    "ExpressionName",
    "expressionName",
    "0xB3212586",
    "hash_B3212586",
)


@dataclasses.dataclass(slots=True)
class YedPedExpressionBinding:
    expression_set_name: str = ""
    expression_dictionary_name: str = ""
    expression_name: str = ""

    @property
    def has_expression_dictionary(self) -> bool:
        return _is_present(self.expression_dictionary_name)

    @property
    def uses_expression_set(self) -> bool:
        return _is_present(self.expression_set_name)

    def validate(self) -> list[str]:
        issues: list[str] = []
        has_set = _is_present(self.expression_set_name)
        has_dictionary = _is_present(self.expression_dictionary_name)
        has_expression = _is_present(self.expression_name)
        if has_set and (has_dictionary or has_expression):
            issues.append(
                "ExpressionSetName cannot be combined with "
                "ExpressionDictionaryName or ExpressionName"
            )
        if has_dictionary != has_expression:
            issues.append(
                "ExpressionDictionaryName and ExpressionName must be specified together"
            )
        return issues

    def require_valid(self) -> YedPedExpressionBinding:
        issues = self.validate()
        if issues:
            raise ValueError("; ".join(issues))
        return self


def _is_present(value: object) -> bool:
    return str(value or "").strip().lower() not in {
        "",
        "null",
        "0",
        "0x00000000",
    }


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
        expression_name=str(_get(root, _EXPRESSION_NAME, "")),
    )


def set_ped_expression_binding(
    ymt: object,
    *,
    expression_set_name: str | None = None,
    expression_dictionary_name: str | None = None,
    expression_name: str | None = None,
) -> object:
    root = _mapping_root(ymt)
    if root is None:
        raise TypeError("ped expression binding requires a decoded YMT mapping")
    current = get_ped_expression_binding(root)
    proposed = YedPedExpressionBinding(
        expression_set_name=current.expression_set_name
        if expression_set_name is None
        else str(expression_set_name),
        expression_dictionary_name=current.expression_dictionary_name
        if expression_dictionary_name is None
        else str(expression_dictionary_name),
        expression_name=current.expression_name
        if expression_name is None
        else str(expression_name),
    ).require_valid()
    _set(root, _EXPRESSION_SET_NAME, proposed.expression_set_name)
    _set(
        root,
        _EXPRESSION_DICTIONARY_NAME,
        proposed.expression_dictionary_name,
    )
    _set(root, _EXPRESSION_NAME, proposed.expression_name)
    return ymt


def validate_ped_expression_binding(ymt: object) -> list[str]:
    return get_ped_expression_binding(ymt).validate()


__all__ = [
    "YedPedExpressionBinding",
    "get_ped_expression_binding",
    "set_ped_expression_binding",
    "validate_ped_expression_binding",
]
