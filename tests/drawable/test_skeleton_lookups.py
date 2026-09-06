import copy
import gc
import pickle
import weakref

import pytest

from fivefury import Vector3
from fivefury.ydr import YdrBone, YdrSkeleton
from fivefury.ydr.model.skeleton.lookups import _BoneList, _BoneLookups


def assert_lookups(skeleton, known_bones):
    for candidate in known_bones:
        expected_tag = next((b for b in skeleton.bones if b.tag == candidate.tag), None)
        expected_name = next(
            (b for b in skeleton.bones if b.name.lower() == candidate.name.lower()), None,
        )
        assert skeleton.get_bone_by_tag(candidate.tag) is expected_tag
        assert skeleton.get_bone_by_name(candidate.name.upper()) is expected_name
    assert skeleton.get_bone_by_tag(-100) is None
    assert skeleton.get_bone_by_name("missing") is None


def test_direct_key_edits_and_duplicate_winners():
    first = YdrBone(name="Root", tag=10)
    second = YdrBone(name="ROOT", tag=10)
    skeleton = YdrSkeleton(bones=[first, second])
    assert skeleton.get_bone_by_name("root") is first
    assert skeleton.get_bone_by_tag(10) is first

    first.name = "renamed"
    first.tag = 20
    assert skeleton.get_bone_by_name("root") is second
    assert skeleton.get_bone_by_tag(10) is second
    assert skeleton.get_bone_by_name("RENAMED") is first
    assert skeleton.get_bone_by_tag(20) is first

    second.name = "ReNaMeD"
    second.tag = 20
    assert skeleton.get_bone_by_name("root") is None
    assert skeleton.get_bone_by_tag(10) is None
    skeleton.bones.reverse()
    assert skeleton.get_bone_by_name("renamed") is second
    assert skeleton.get_bone_by_tag(20) is second


@pytest.mark.parametrize("operation", [
    "append", "extend", "self_extend", "insert", "replace", "slice", "extended_slice",
    "delete", "delete_slice", "delete_extended_slice", "pop", "remove", "clear",
    "reverse", "sort", "iadd", "self_iadd", "imul", "zero_imul", "negative_imul",
    "assign", "reinitialize",
])
def test_list_mutations(operation):
    a, b, c = (YdrBone(name=name, tag=tag) for name, tag in [("z", 1), ("Z", 1), ("a", 2)])
    replacement = YdrBone(name="new", tag=3)
    skeleton = YdrSkeleton(bones=[a, b, c])
    bones = skeleton.bones
    assert_lookups(skeleton, [a, b, c, replacement])

    if operation == "append":
        bones.append(replacement)
    elif operation == "extend":
        bones.extend(iter([replacement, a]))
    elif operation == "self_extend":
        bones.extend(bones)
    elif operation == "insert":
        bones.insert(-1, replacement)
    elif operation == "replace":
        bones[0] = replacement
    elif operation == "slice":
        bones[:2] = [replacement, c]
    elif operation == "extended_slice":
        bones[::-2] = [replacement, c]
    elif operation == "delete":
        del bones[0]
    elif operation == "delete_slice":
        del bones[:2]
    elif operation == "delete_extended_slice":
        del bones[::-2]
    elif operation == "pop":
        assert bones.pop(0) is a
    elif operation == "remove":
        bones.remove(a)
    elif operation == "clear":
        bones.clear()
    elif operation == "reverse":
        bones.reverse()
    elif operation == "sort":
        bones.sort(key=lambda bone: bone.name)
    elif operation == "iadd":
        skeleton.bones += [replacement]
    elif operation == "self_iadd":
        skeleton.bones += skeleton.bones
    elif operation == "imul":
        skeleton.bones *= 3
    elif operation == "zero_imul":
        skeleton.bones *= 0
    elif operation == "negative_imul":
        skeleton.bones *= -2
    elif operation == "assign":
        skeleton.bones = [replacement, c, b]
    elif operation == "reinitialize":
        bones.__init__([replacement, c, b])

    if operation != "assign":
        assert skeleton.bones is bones
    assert_lookups(skeleton, [a, b, c, replacement])
    # New, retained and repeated objects must still notify after each operation.
    for index, bone in enumerate([a, b, c, replacement]):
        bone.name = f"edited{index}"
        bone.tag = 100 + index
    assert_lookups(skeleton, [a, b, c, replacement])
    assert skeleton.get_bone_by_tag(1) is None
    assert skeleton.get_bone_by_name("z") is None


def test_collection_ownership_and_shared_bones():
    bone = YdrBone(name="root", tag=10)
    source = [bone]
    first = YdrSkeleton(bones=source)
    second = YdrSkeleton()
    second.bones = first.bones
    assert first.bones is not source
    assert second.bones is not first.bones
    assert first.bones[0] is second.bones[0] is bone
    source.clear()
    assert first.bone_count == second.bone_count == 1

    assert first.get_bone_by_name("root") is second.get_bone_by_tag(10) is bone
    bone.name = "shared"
    bone.tag = 20
    for skeleton in (first, second):
        assert skeleton.get_bone_by_name("root") is None
        assert skeleton.get_bone_by_tag(10) is None
        assert skeleton.get_bone_by_name("shared") is bone
        assert skeleton.get_bone_by_tag(20) is bone

    first.bones.clear()
    bone.name = "still_shared"
    assert first.get_bone_by_name("still_shared") is None
    assert second.get_bone_by_name("still_shared") is bone


def test_removed_duplicate_remains_registered_until_last_occurrence(monkeypatch):
    bone = YdrBone(name="root", tag=10)
    skeleton = YdrSkeleton(bones=[bone, bone])
    skeleton.bones.pop()
    assert skeleton.get_bone_by_name("root") is bone
    bone.name = "renamed"
    assert skeleton.get_bone_by_name("renamed") is bone
    skeleton.bones.pop()
    assert skeleton.get_bone_by_name("renamed") is None

    def unexpected_rebuild(self):
        raise AssertionError("Removed bones must not invalidate this collection")

    monkeypatch.setattr(YdrSkeleton, "_rebuild_bone_lookups", unexpected_rebuild)
    bone.name = "detached"
    assert skeleton.get_bone_by_name("detached") is None


def test_partial_extend_and_failed_slice():
    root, extra = YdrBone(name="root", tag=10), YdrBone(name="extra", tag=20)
    skeleton = YdrSkeleton(bones=[root])

    def values():
        yield extra
        raise ValueError("iterator failure")

    with pytest.raises(ValueError, match="iterator failure"):
        skeleton.bones.extend(values())
    assert skeleton.bones == [root, extra]
    assert_lookups(skeleton, [root, extra])
    with pytest.raises(ValueError):
        skeleton.bones[::2] = [extra, root]
    assert skeleton.bones == [root, extra]
    extra.name = "changed"
    assert skeleton.get_bone_by_name("changed") is extra


def test_sort_callback_lookup_and_failure():
    bones = [YdrBone(name=str(i), tag=i) for i in range(3)]
    skeleton = YdrSkeleton(bones=bones)

    def key(bone):
        assert skeleton.get_bone_by_tag(0) is None
        if bone.tag == 2:
            raise ValueError("key failure")
        return -bone.tag

    with pytest.raises(ValueError, match="key failure"):
        skeleton.bones.sort(key=key)
    assert_lookups(skeleton, bones)
    skeleton.bones.sort(key=lambda bone: -bone.tag)
    assert skeleton.bones == bones[::-1]
    assert_lookups(skeleton, bones)


def test_factory_uses_edited_name_tag_and_parent_membership():
    skeleton = YdrSkeleton()
    root = skeleton.bone("root", tag=100)
    other = skeleton.bone("other", tag=200)
    child = skeleton.bone("child", parent="root")
    root.name = "renamed"
    root.tag = 300
    child.parent_index = other.index
    new_root_child = skeleton.bone("new_root_child", parent="renamed")
    assert new_root_child.parent_index == root.index
    assert child.next_sibling_index == -1
    new_other_child = skeleton.bone("new_other_child", parent=200)
    assert child.next_sibling_index == new_other_child.index
    sibling = skeleton.bone("sibling", parent=300)
    assert new_root_child.next_sibling_index == sibling.index
    with pytest.raises(KeyError):
        skeleton.bone("invalid", parent="root")
    with pytest.raises(KeyError):
        skeleton.bone("invalid", parent=100)


def test_factory_after_same_length_replacement_and_reorder():
    skeleton = YdrSkeleton()
    root = skeleton.bone("root", tag=100)
    a = skeleton.bone("a", parent=root)
    b = skeleton.bone("b", parent=root)
    replacement = YdrBone(name="replacement", tag=200, index=0)
    skeleton.bones[0] = replacement
    skeleton.bones[1:] = [b, a]
    child = skeleton.bone("new", parent="replacement")
    assert child.parent_index == 0
    assert a.next_sibling_index == child.index
    assert b.next_sibling_index == -1
    assert skeleton.get_bone_by_tag(100) is None
    assert skeleton.get_bone_by_tag(200) is replacement


@pytest.mark.parametrize("clone", [copy.copy, copy.deepcopy, lambda value: pickle.loads(pickle.dumps(value))])
def test_copy_and_pickle_reconstruct_observers(clone):
    original = YdrSkeleton(bones=[YdrBone(name="root", tag=10)])
    duplicate = clone(original)
    assert duplicate == original
    assert duplicate.bones is not original.bones
    assert (duplicate.bones[0] is original.bones[0]) is (clone is copy.copy)
    duplicate.bones[0].name = "copied"
    assert duplicate.get_bone_by_name("copied") is duplicate.bones[0]
    assert_lookups(original, [original.bones[0]])
    original.bones[0].tag = 20
    assert_lookups(duplicate, [duplicate.bones[0]])

    bone_copy = clone(original.bones[0])
    assert bone_copy._lookup_owners is None
    third = YdrSkeleton(bones=[bone_copy])
    bone_copy.name = "third"
    assert third.get_bone_by_name("third") is bone_copy
    assert original.get_bone_by_name("third") is None


@pytest.mark.parametrize("clone", [copy.deepcopy, lambda value: pickle.loads(pickle.dumps(value))])
def test_shared_graph_clone_keeps_sharing_without_original_observers(clone):
    bone = YdrBone(name="root", tag=10)
    first = YdrSkeleton(bones=[bone, bone])
    second = YdrSkeleton(bones=[bone])
    cloned_first, cloned_second, cloned_bone = clone((first, second, bone))
    assert cloned_bone is not bone
    assert cloned_first.bones[0] is cloned_first.bones[1] is cloned_second.bones[0] is cloned_bone
    assert set(bone._lookup_owners) == {first.bones.lookups, second.bones.lookups}
    assert set(cloned_bone._lookup_owners) == {
        cloned_first.bones.lookups, cloned_second.bones.lookups,
    }
    cloned_bone.name = "cloned"
    cloned_bone.tag = 20
    for skeleton in (cloned_first, cloned_second):
        assert skeleton.get_bone_by_name("root") is None
        assert skeleton.get_bone_by_tag(10) is None
        assert skeleton.get_bone_by_name("cloned") is cloned_bone
        assert skeleton.get_bone_by_tag(20) is cloned_bone
    for skeleton in (first, second):
        assert not skeleton.bones.lookups.dirty
        assert skeleton.get_bone_by_name("root") is bone
        assert skeleton.get_bone_by_tag(10) is bone
    del cloned_first, cloned_second, skeleton
    gc.collect()
    assert not cloned_bone._lookup_owners
    assert len(bone._lookup_owners) == 2


def test_shared_parent_edits_invalidate_each_factory():
    bones = [
        YdrBone(name="root", index=0),
        YdrBone(name="other", index=1),
        YdrBone(name="child", index=2, parent_index=0),
    ]
    first, second = YdrSkeleton(bones=bones), YdrSkeleton(bones=bones)
    bones[2].parent_index = 1
    for skeleton in (first, second):
        skeleton.bone("root_child", parent="root")
        assert bones[2].next_sibling_index == -1
    for skeleton in (first, second):
        child = skeleton.bone("other_child", parent="other")
        assert bones[2].next_sibling_index == child.index


def test_sort_rejected_mutation_does_not_keep_discarded_bone_registered():
    skeleton = YdrSkeleton(bones=[YdrBone(name="root", tag=10)])
    discarded = YdrBone(name="discarded", tag=20)

    def key(bone):
        skeleton.bones.append(discarded)
        return bone.tag

    with pytest.raises(ValueError, match="list modified during sort"):
        skeleton.bones.sort(key=key)
    assert skeleton.bone_count == 1
    assert skeleton.get_bone_by_tag(20) is None
    discarded.name = "edited"
    assert not skeleton.bones.lookups.dirty


def test_observers_do_not_keep_collections_alive():
    bone = YdrBone(name="root")
    skeleton = YdrSkeleton(bones=[bone])
    collection_ref = weakref.ref(skeleton.bones)
    lookup_ref = weakref.ref(skeleton.bones.lookups)
    skeleton.bones = []
    gc.collect()
    assert collection_ref() is None
    assert lookup_ref() is None
    assert not bone._lookup_owners
    bone.name = "detached"


def test_linear_registration_and_no_warm_lookup_scans(monkeypatch):
    recorded = 0
    rebuilt = 0
    record = _BoneLookups.record
    rebuild = YdrSkeleton._rebuild_bone_lookups

    def count_record(self, index, bone):
        nonlocal recorded
        recorded += 1
        record(self, index, bone)

    def count_rebuild(self):
        nonlocal rebuilt
        rebuilt += 1
        rebuild(self)

    monkeypatch.setattr(_BoneLookups, "record", count_record)
    monkeypatch.setattr(YdrSkeleton, "_rebuild_bone_lookups", count_rebuild)
    skeleton = YdrSkeleton()
    for index in range(1000):
        bone = skeleton.bone(str(index), tag=index, parent="0" if index else None)
        assert skeleton.get_bone_by_tag(index) is bone
    for index in range(1000, 2000):
        bone = YdrBone(name=str(index), tag=index)
        skeleton.bones.append(bone)
        assert skeleton.get_bone_by_name(str(index)) is bone
    assert recorded == 2000
    assert rebuilt == 0

    skeleton.bones[0].name = "root"
    skeleton.bones[0].tag = 9999
    skeleton.bones.reverse()
    assert skeleton.get_bone_by_name("root") is skeleton.bones[-1]
    assert recorded == 4000
    assert rebuilt == 1

    def unexpected_iteration(self):
        raise AssertionError("Warm lookups must not scan or fingerprint bones")

    monkeypatch.setattr(_BoneList, "__iter__", unexpected_iteration)
    skeleton.bones[0].translation = Vector3(1, 2, 3)
    for _ in range(1000):
        assert skeleton.get_bone_by_tag(9999) is skeleton.bones[-1]
        assert skeleton.get_bone_by_name("ROOT") is skeleton.bones[-1]
        assert skeleton.get_bone_by_name("absent") is None
        assert skeleton.get_bone_by_tag(-1) is None
    assert rebuilt == 1
