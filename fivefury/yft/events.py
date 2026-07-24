from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Sequence

YFT_EVENT_SET_RESOURCE_TAG = 0x74536353


@dataclasses.dataclass(frozen=True, slots=True)
class YftEventSet:
    pointer: int = 0
    resource_tag: int = YFT_EVENT_SET_RESOURCE_TAG
    resource_state: int = 0
    reserved_08: int = 0
    instance_pointers: tuple[int, ...] = ()
    capacity: int = 0
    new_instance_type: int = 0
    bank_pointer: int = 0
    group_pointer: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.instance_pointers

    @property
    def can_rebuild(self) -> bool:
        return (
            self.resource_tag == YFT_EVENT_SET_RESOURCE_TAG
            and self.resource_state == 0
            and self.reserved_08 == 0
            and self.is_empty
            and self.capacity == 0
            and self.new_instance_type == 0
            and not self.bank_pointer
            and not self.group_pointer
        )

    @classmethod
    def declare(cls) -> YftEventSet:
        return cls()


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsGroupEvents:
    death: YftEventSet | None = None
    death_player_pointer: int = 0

    @property
    def has_any(self) -> bool:
        return self.death is not None or self.death_player_pointer != 0

    @property
    def can_rebuild(self) -> bool:
        return (
            self.death_player_pointer == 0
            and (self.death is None or self.death.can_rebuild)
        )

    def event_sets(self) -> Iterator[YftEventSet]:
        if self.death is not None:
            yield self.death

    @classmethod
    def declare(
        cls,
        *,
        death: YftEventSet | None = None,
    ) -> YftPhysicsGroupEvents:
        return cls(death=death)


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsChildEvents:
    continuous: YftEventSet | None = None
    collision: YftEventSet | None = None
    break_event: YftEventSet | None = None
    break_from_root: YftEventSet | None = None
    collision_player_pointer: int = 0
    break_player_pointer: int = 0
    break_from_root_player_pointer: int = 0

    @property
    def has_any(self) -> bool:
        return any(self.event_sets()) or any(self.player_pointers())

    @property
    def can_rebuild(self) -> bool:
        return not any(self.player_pointers()) and all(
            event_set.can_rebuild for event_set in self.event_sets()
        )

    def event_sets(self) -> tuple[YftEventSet, ...]:
        return tuple(
            event_set
            for event_set in (
                self.continuous,
                self.collision,
                self.break_event,
                self.break_from_root,
            )
            if event_set is not None
        )

    def player_pointers(self) -> tuple[int, int, int]:
        return (
            self.collision_player_pointer,
            self.break_player_pointer,
            self.break_from_root_player_pointer,
        )

    def items(self) -> tuple[tuple[str, YftEventSet | int], ...]:
        values: Sequence[tuple[str, YftEventSet | int | None]] = (
            ("continuous", self.continuous),
            ("collision", self.collision),
            ("break", self.break_event),
            ("break_from_root", self.break_from_root),
            ("collision_player", self.collision_player_pointer),
            ("break_player", self.break_player_pointer),
            ("break_from_root_player", self.break_from_root_player_pointer),
        )
        return tuple((name, value) for name, value in values if value)

    @classmethod
    def declare(
        cls,
        *,
        continuous: YftEventSet | None = None,
        collision: YftEventSet | None = None,
        break_event: YftEventSet | None = None,
        break_from_root: YftEventSet | None = None,
    ) -> YftPhysicsChildEvents:
        return cls(
            continuous=continuous,
            collision=collision,
            break_event=break_event,
            break_from_root=break_from_root,
        )


__all__ = [
    "YFT_EVENT_SET_RESOURCE_TAG",
    "YftEventSet",
    "YftPhysicsChildEvents",
    "YftPhysicsGroupEvents",
]
