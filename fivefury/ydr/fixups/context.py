from __future__ import annotations

from typing import Protocol


class DrawableFixupValidator(Protocol):
    def error(self, path: str, message: str) -> None: ...

    def pointer(
        self,
        pointer: int,
        path: str,
        *,
        size: int = 1,
        section: str | None = "system",
        nullable: bool = True,
    ) -> int | None: ...

    def class_header(
        self,
        pointer: int,
        path: str,
        *,
        size: int,
        expected_vft: int | tuple[int, ...] | None,
        nullable: bool = False,
    ) -> int | None: ...

    def string(self, pointer: int, path: str) -> None: ...

    def u8(self, offset: int) -> int: ...

    def u16(self, offset: int) -> int: ...

    def u32(self, offset: int) -> int: ...

    def u64(self, offset: int) -> int: ...


__all__ = ["DrawableFixupValidator"]
