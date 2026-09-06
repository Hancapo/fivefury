"""Synthetic skeleton construction and warm lookup scaling measurements."""

import pytest

from fivefury.ydr import YdrBone, YdrSkeleton

pytestmark = pytest.mark.performance


@pytest.mark.parametrize("count", [100, 1000, 10000])
def test_factory(benchmark, count):
    def construct():
        skeleton = YdrSkeleton()
        for index in range(count):
            skeleton.bone(str(index), tag=index, parent="0" if index else None)
        return skeleton

    assert benchmark(construct).bone_count == count


@pytest.mark.parametrize("count", [100, 1000, 10000])
def test_append_and_lookup(benchmark, count):
    bones = [YdrBone(name=str(index), tag=index) for index in range(count)]

    def construct():
        skeleton = YdrSkeleton()
        for bone in bones:
            skeleton.bones.append(bone)
            skeleton.get_bone_by_tag(bone.tag)
        return skeleton

    assert benchmark(construct).bone_count == count


@pytest.mark.parametrize("count", [100, 1000, 10000])
def test_warm_lookups(benchmark, count):
    skeleton = YdrSkeleton(bones=[YdrBone(name=str(i), tag=i) for i in range(count)])
    bone = skeleton.bones[-1]
    skeleton.get_bone_by_tag(bone.tag)

    def lookup():
        for _ in range(1000):
            skeleton.get_bone_by_tag(bone.tag)
            skeleton.get_bone_by_name(bone.name)
            skeleton.get_bone_by_tag(-1)
            skeleton.get_bone_by_name("absent")

    benchmark(lookup)


@pytest.mark.parametrize("count", [100, 1000, 10000])
def test_build(benchmark, count):
    skeleton = YdrSkeleton(bones=[
        YdrBone(name=str(i), tag=i, parent_index=0 if i else -1)
        for i in range(count)
    ])
    assert benchmark(skeleton.build) is skeleton
