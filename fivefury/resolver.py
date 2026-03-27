from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .hashing import jenk_hash
from .metahash import MetaHash


def _normalize_name(value: str) -> str:
    return str(value).strip()


def _iter_text_names(
    path: str | Path,
    *,
    encoding: str = "utf-8",
    comment_prefixes: tuple[str, ...] = ("#", ";", "//"),
) -> Iterable[str]:
    with Path(path).open("r", encoding=encoding) as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if any(line.startswith(prefix) for prefix in comment_prefixes):
                continue
            yield line


@dataclass(slots=True)
class HashResolver:
    hash_to_name: dict[int, str] = field(default_factory=dict)
    name_to_hash: dict[str, int] = field(default_factory=dict)

    def clear(self) -> None:
        self.hash_to_name.clear()
        self.name_to_hash.clear()

    def hash(self, value: int | str | MetaHash) -> int:
        return jenk_hash(value) if isinstance(value, str) else int(value)

    def register_name(self, name: str) -> int | None:
        normalized = _normalize_name(name)
        if not normalized:
            return None
        name_hash = jenk_hash(normalized)
        self.name_to_hash[normalized] = name_hash
        self.hash_to_name.setdefault(name_hash, normalized)
        return name_hash

    def register_names(self, names: Iterable[str]) -> list[int]:
        hashes: list[int] = []
        for name in names:
            name_hash = self.register_name(name)
            if name_hash is not None:
                hashes.append(name_hash)
        return hashes

    def register_names_file(
        self,
        path: str | Path,
        *,
        encoding: str = "utf-8",
        comment_prefixes: tuple[str, ...] = ("#", ";", "//"),
    ) -> list[int]:
        return self.register_names(
            _iter_text_names(path, encoding=encoding, comment_prefixes=comment_prefixes)
        )

    def register_path_name(self, path: str | Path) -> list[int]:
        pure = Path(str(path).replace("\\", "/"))
        names: list[str] = []
        if pure.stem:
            names.append(pure.stem)
        if pure.name and pure.suffix == "":
            names.append(pure.name)
        return self.register_names(names)

    def register_path_names(self, root: str | Path, *, recursive: bool = True) -> list[int]:
        root_path = Path(root)
        if root_path.is_file():
            return self.register_path_name(root_path)
        hashes: list[int] = []
        iterator = root_path.rglob("*") if recursive else root_path.iterdir()
        for path in iterator:
            if path.is_file():
                hashes.extend(self.register_path_name(path))
        return hashes

    def resolve_hash(self, value: int | MetaHash) -> str | None:
        return self.hash_to_name.get(int(value))

    def resolve(self, value: int | str | MetaHash) -> int | str:
        if isinstance(value, str):
            return value
        if isinstance(value, MetaHash):
            return value.resolved
        resolved = self.resolve_hash(value)
        return resolved if resolved is not None else int(value)

    def resolve_or_none(self, value: int | str | MetaHash) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, MetaHash):
            return value.text
        return self.resolve_hash(value)

    def matches(self, left: int | str | MetaHash, right: int | str | MetaHash) -> bool:
        return self.hash(left) == self.hash(right)


_GLOBAL_HASH_RESOLVER = HashResolver()


def get_hash_resolver() -> HashResolver:
    return _GLOBAL_HASH_RESOLVER


def clear_hash_resolver() -> None:
    _GLOBAL_HASH_RESOLVER.clear()


def register_name(name: str) -> int | None:
    return _GLOBAL_HASH_RESOLVER.register_name(name)


def register_names(names: Iterable[str]) -> list[int]:
    return _GLOBAL_HASH_RESOLVER.register_names(names)


def register_names_file(
    path: str | Path,
    *,
    encoding: str = "utf-8",
    comment_prefixes: tuple[str, ...] = ("#", ";", "//"),
) -> list[int]:
    return _GLOBAL_HASH_RESOLVER.register_names_file(
        path,
        encoding=encoding,
        comment_prefixes=comment_prefixes,
    )


def register_path_name(path: str | Path) -> list[int]:
    return _GLOBAL_HASH_RESOLVER.register_path_name(path)


def register_path_names(root: str | Path, *, recursive: bool = True) -> list[int]:
    return _GLOBAL_HASH_RESOLVER.register_path_names(root, recursive=recursive)


def resolve_hash(value: int | MetaHash) -> str | None:
    return _GLOBAL_HASH_RESOLVER.resolve_hash(value)


def resolve_name(value: int | str | MetaHash) -> int | str:
    return _GLOBAL_HASH_RESOLVER.resolve(value)


def hash_matches(left: int | str | MetaHash, right: int | str | MetaHash) -> bool:
    return _GLOBAL_HASH_RESOLVER.matches(left, right)


__all__ = [
    "HashResolver",
    "clear_hash_resolver",
    "get_hash_resolver",
    "hash_matches",
    "register_name",
    "register_names",
    "register_names_file",
    "register_path_name",
    "register_path_names",
    "resolve_hash",
    "resolve_name",
]
