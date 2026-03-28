from __future__ import annotations

from typing import Any

import pytest


class PytestCompat:
    def skipTest(self, msg: str = "") -> None:
        pytest.skip(msg)

    def assertEqual(self, first: Any, second: Any, msg: str | None = None) -> None:
        assert first == second, msg or f"{first!r} != {second!r}"

    def assertNotEqual(self, first: Any, second: Any, msg: str | None = None) -> None:
        assert first != second, msg or f"{first!r} == {second!r}"

    def assertTrue(self, expr: Any, msg: str | None = None) -> None:
        assert expr, msg or f"Expected truthy value, got {expr!r}"

    def assertFalse(self, expr: Any, msg: str | None = None) -> None:
        assert not expr, msg or f"Expected falsy value, got {expr!r}"

    def assertIsNone(self, obj: Any, msg: str | None = None) -> None:
        assert obj is None, msg or f"Expected None, got {obj!r}"

    def assertIsNotNone(self, obj: Any, msg: str | None = None) -> None:
        assert obj is not None, msg or "Unexpected None value"

    def assertIn(self, member: Any, container: Any, msg: str | None = None) -> None:
        assert member in container, msg or f"{member!r} not found in {container!r}"

    def assertNotIn(self, member: Any, container: Any, msg: str | None = None) -> None:
        assert member not in container, msg or f"{member!r} unexpectedly found in {container!r}"

    def assertIsInstance(self, obj: Any, cls: Any, msg: str | None = None) -> None:
        assert isinstance(obj, cls), msg or f"{obj!r} is not an instance of {cls!r}"

    def assertGreater(self, first: Any, second: Any, msg: str | None = None) -> None:
        assert first > second, msg or f"{first!r} is not greater than {second!r}"

    def assertGreaterEqual(self, first: Any, second: Any, msg: str | None = None) -> None:
        assert first >= second, msg or f"{first!r} is not greater than or equal to {second!r}"

    def assertLess(self, first: Any, second: Any, msg: str | None = None) -> None:
        assert first < second, msg or f"{first!r} is not less than {second!r}"

    def assertLessEqual(self, first: Any, second: Any, msg: str | None = None) -> None:
        assert first <= second, msg or f"{first!r} is not less than or equal to {second!r}"

    def assertAlmostEqual(
        self,
        first: float,
        second: float,
        places: int = 7,
        msg: str | None = None,
    ) -> None:
        tolerance = 10 ** (-places)
        assert abs(first - second) <= tolerance, msg or (
            f"{first!r} != {second!r} within {places} places"
        )
