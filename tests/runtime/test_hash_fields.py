import copy
import dataclasses
import pickle

import pytest

from fivefury.metahash import MetaHash, MetaHashFieldsMixin
from fivefury.ymap import Entity


@dataclasses.dataclass(slots=True)
class HashRecord(MetaHashFieldsMixin):
    _hash_fields = ('name',)
    _hash_list_fields = ('names',)
    name: object = 0
    names: list = dataclasses.field(default_factory=list)
    count: int = 0


@dataclasses.dataclass(slots=True)
class ChildRecord(HashRecord):
    extra: int = 0


def test_inherited_hash_fields_preserve_assignment_and_deletion():
    record = ChildRecord(name='initial', names=['a', 17], count=4, extra=9)
    assert isinstance(record.name, MetaHash)
    assert all(isinstance(name, MetaHash) for name in record.names)
    record.name = 42
    record.names = (name for name in [11, 'b'])
    record.count = 7
    assert record.name.raw == 42
    assert [name.raw for name in record.names] == [11, 'b']
    assert record.count == 7 and record.extra == 9
    del record.name
    with pytest.raises(AttributeError):
        _ = record.name
    with pytest.raises(AttributeError):
        record.unknown = 0


def test_hash_fields_copy_and_pickle_preserve_nominal_types():
    entity = Entity(archetype_name='prop_test')
    for restored in (copy.copy(entity), copy.deepcopy(entity), pickle.loads(pickle.dumps(entity))):
        assert restored == entity
        assert isinstance(restored.archetype_name, MetaHash)
        restored.archetype_name = 17
        assert restored.archetype_name.raw == 17
    assert entity.archetype_name.raw == 'prop_test'


def test_native_setter_obeys_descriptors():
    class DescriptorRecord(HashRecord):
        @property
        def doubled(self):
            return self.count * 2

        @doubled.setter
        def doubled(self, value):
            self.count = value // 2

    record = DescriptorRecord()
    record.doubled = 12
    assert record.count == 6
