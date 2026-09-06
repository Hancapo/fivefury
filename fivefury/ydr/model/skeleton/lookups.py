from __future__ import annotations

import operator
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, Self
from weakref import WeakSet

if TYPE_CHECKING:
    from .bone import YdrBone


class _BoneLookups:
    __slots__ = ("__weakref__", "by_name", "by_tag", "dirty", "last_child_by_parent")

    def __init__(self) -> None:
        self.by_tag: dict[int, YdrBone] = {}
        self.by_name: dict[str, YdrBone] = {}
        self.last_child_by_parent: dict[int, int] = {}
        self.dirty = False

    def record(self, index: int, bone: YdrBone) -> None:
        self.by_tag.setdefault(int(bone.tag), bone)
        self.by_name.setdefault(bone.name.lower(), bone)
        self.last_child_by_parent[int(bone.parent_index)] = index

    def clear(self) -> None:
        self.by_tag.clear()
        self.by_name.clear()
        self.last_child_by_parent.clear()


class _BoneList(list["YdrBone"]):
    """Owned list storage; bone objects may subscribe to multiple lookup indexes."""

    __slots__ = ("__weakref__", "_members", "lookups")

    def __init__(self, bones: Iterable[YdrBone] = ()) -> None:
        # Materialize first, including when explicitly reinitializing this list.
        bones = list(bones)
        if hasattr(self, "_members"):
            self.clear()
        super().__init__()
        self.lookups = _BoneLookups()
        self._members: dict[int, tuple[YdrBone, int]] = {}
        self.extend(bones)

    def _register(self, bone: YdrBone) -> None:
        key = id(bone)
        member = self._members.get(key)
        if member is not None:
            self._members[key] = (bone, member[1] + 1)
            return
        if bone._lookup_owners is None:
            bone._lookup_owners = WeakSet()
        bone._lookup_owners.add(self.lookups)
        self._members[key] = (bone, 1)

    def _unregister(self, bone: YdrBone) -> None:
        key = id(bone)
        count = self._members[key][1]
        if count > 1:
            self._members[key] = (bone, count - 1)
        else:
            del self._members[key]
            bone._lookup_owners.discard(self.lookups)

    def append(self, bone: YdrBone) -> None:
        index = len(self)
        super().append(bone)
        self._register(bone)
        if not self.lookups.dirty:
            self.lookups.dirty = True
            self.lookups.record(index, bone)
            self.lookups.dirty = False

    def extend(self, bones: Iterable[YdrBone]) -> None:
        if bones is self:
            bones = list(self)
        # Like list.extend, keep the consumed prefix if iteration raises.
        for bone in bones:
            self.append(bone)

    def insert(self, index: int, bone: YdrBone) -> None:
        super().insert(index, bone)
        self._register(bone)
        self.lookups.dirty = True

    def __setitem__(self, index: int | slice, value: Any) -> None:
        added = list(value) if isinstance(index, slice) else [value]
        removed = self[index] if isinstance(index, slice) else [self[index]]
        super().__setitem__(index, added if isinstance(index, slice) else value)
        for bone in removed:
            self._unregister(bone)
        for bone in added:
            self._register(bone)
        self.lookups.dirty = True

    def __delitem__(self, index: int | slice) -> None:
        removed = self[index] if isinstance(index, slice) else [self[index]]
        super().__delitem__(index)
        for bone in removed:
            self._unregister(bone)
        self.lookups.dirty = True

    def pop(self, index: int = -1) -> YdrBone:
        bone = super().pop(index)
        self._unregister(bone)
        self.lookups.dirty = True
        return bone

    def remove(self, bone: YdrBone) -> None:
        self.pop(self.index(bone))

    def clear(self) -> None:
        for bone, _ in self._members.values():
            bone._lookup_owners.discard(self.lookups)
        self._members.clear()
        super().clear()
        self.lookups.clear()
        self.lookups.dirty = False

    def reverse(self) -> None:
        super().reverse()
        self.lookups.dirty = True

    def sort(
        self, *, key: Callable[[YdrBone], Any] | None = None, reverse: bool = False
    ) -> None:
        self.lookups.dirty = True
        try:
            super().sort(key=key, reverse=reverse)
        finally:
            # sort may leave a partial order on error; callbacks can also read or
            # attempt to mutate the temporarily empty list exposed by CPython.
            for bone, _ in self._members.values():
                bone._lookup_owners.discard(self.lookups)
            self._members.clear()
            for bone in self:
                self._register(bone)
            self.lookups.dirty = True

    def __iadd__(self, bones: Iterable[YdrBone]) -> Self:
        self.extend(bones)
        return self

    def __imul__(self, count: int) -> Self:
        count = operator.index(count)
        if count <= 0:
            self.clear()
        elif count != 1:
            super().__imul__(count)
            self._members = {
                key: (bone, occurrences * count)
                for key, (bone, occurrences) in self._members.items()
            }
            self.lookups.dirty = True
        return self

    def __reduce_ex__(self, protocol: int) -> tuple:
        # Copies and pickle reconstruct registrations, never derived indexes.
        return type(self), (list(self),)
