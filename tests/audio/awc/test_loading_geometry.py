import pytest
from fivefury.awc import Awc, AwcStream, build_awc_bytes, read_awc
from fivefury.awc.loading_geometry import inspect_loading_geometry, compact_mono_payloads


def fixture():
    return Awc([AwcStream.from_pcm(name, bytes(32000), sample_rate=32000)
                for name in ('alpha', 'beta', 'gamma')])


def test_compact_preserves_payload_and_reduces_spans():
    original = build_awc_bytes(fixture())
    compact = build_awc_bytes(fixture(), compact_streams=True)
    reports = [inspect_loading_geometry(raw, len(raw), alignment=2048)
               for raw in (original, compact)]
    assert max(s['span_bytes'] for s in reports[1]['streams']) < max(s['span_bytes'] for s in reports[0]['streams'])
    snapshots = [[(s.hash, [(c.type_value, c.to_payload()) for c in s.chunks])
                  for s in read_awc(raw).streams] for raw in (original, compact)]
    assert snapshots[0] == snapshots[1]
    assert all(s['exceeds_budget'] is None for s in reports[1]['streams'])


def test_exact_budget_and_one_byte_over():
    raw = build_awc_bytes(fixture(), compact_streams=True)
    r = inspect_loading_geometry(raw, len(raw), alignment=2048)
    maximum = max(s['required_bytes'] for s in r['streams'])
    assert not any(s['exceeds_budget'] for s in inspect_loading_geometry(raw, len(raw), alignment=2048, budget_bytes=maximum)['streams'])
    assert any(s['exceeds_budget'] for s in inspect_loading_geometry(raw, len(raw), alignment=2048, budget_bytes=maximum-1)['streams'])


def test_truncation_rejected():
    raw = build_awc_bytes(fixture())
    with pytest.raises(ValueError):
        inspect_loading_geometry(raw[:16], len(raw), alignment=2048)
    with pytest.raises(ValueError):
        inspect_loading_geometry(raw, 16, alignment=2048)


def test_opaque_compaction_preserves_every_payload():
    raw=build_awc_bytes(fixture())
    compact=compact_mono_payloads(raw)
    def snap(data):
        return [(s.hash,[(c.type_value,c.to_payload()) for c in s.chunks])
                for s in read_awc(data).streams]
    assert snap(raw)==snap(compact)
    assert compact_mono_payloads(compact)==compact


def test_streaming_not_qualified_as_mono():
    import struct
    raw=bytearray(build_awc_bytes(fixture()))
    flags=struct.unpack_from('<H',raw,6)[0]
    struct.pack_into('<H',raw,6,flags|4)
    r=inspect_loading_geometry(raw,len(raw),alignment=2048,budget_bytes=9999999)
    assert not r['budget_qualified']
    assert all(s['required_bytes'] is None for s in r['streams'])
    with pytest.raises(ValueError,match='mono'):
        compact_mono_payloads(raw)


@pytest.mark.parametrize('endian',['<','>'])
def test_encrypted_mono_default_already_compact(endian):
    bank=fixture()
    bank.endian=endian
    bank.flags |= 2
    default=build_awc_bytes(bank)
    explicit=build_awc_bytes(bank,compact_streams=True)
    assert default==explicit
    opaque=compact_mono_payloads(default)
    assert opaque==default
    assert [s.pcm_bytes() for s in read_awc(opaque).streams]==[s.pcm_bytes() for s in bank.streams]


@pytest.mark.parametrize('file_size',[None,True,-1,15,16.5])
def test_invalid_file_size_rejected(file_size):
    raw=build_awc_bytes(fixture())
    with pytest.raises(ValueError,match='File size'):
        inspect_loading_geometry(raw,file_size,alignment=2048)
