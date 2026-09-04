import pytest

from fivefury import RpfArchive
from fivefury._native import CompactIndex, RpfReader, scan_rpf_into_index
from fivefury.hashing import _get_lut


@pytest.mark.parametrize('name', ['caf\u00e9.rpf', '\u5730\u56fe.rpf', '\U0001f30d.rpf'])
def test_native_reader_and_scanner_use_unicode_paths(tmp_path, name):
    parent = tmp_path / 'donn\u00e9es_\u5730\u56fe'
    parent.mkdir()
    path = parent / name
    archive = RpfArchive.empty(name)
    _, nested = archive.nested_archive('nested.rpf')
    nested.file('data.bin', b'unicode path')
    archive.save(path)
    reader = RpfReader(path, _get_lut())
    assert reader.read('nested.rpf/data.bin') == b'unicode path'
    assert reader.read_variants('nested.rpf/data.bin') == (b'unicode path', b'unicode path')
    index = CompactIndex()
    assert scan_rpf_into_index(index, str(path), name, _get_lut()) == 2
    assert index.find_path_id(name + '/nested.rpf/data.bin') is not None
