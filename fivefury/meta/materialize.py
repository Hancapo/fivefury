"""Schema-checked domain materialization using the shared native scalar decoder."""

from collections.abc import Mapping
from typing import Any

from .. import _native_abi3
from . import MetaStructInfo
from .codec import camel_to_snake, scalar_plan
from .defs import META_TYPE_NAME_ARRAYINFO, MetaDataType
from .utils import array_info_for_field

_ARRAY_SCALARS = frozenset((MetaDataType.FLOAT, MetaDataType.UNSIGNED_INT, MetaDataType.HASH,
                          MetaDataType.UNSIGNED_SHORT, MetaDataType.UNSIGNED_BYTE))


def _layout(info: MetaStructInfo) -> tuple:
    return (info.name_hash, info.key, info.unknown, info.unknown_ch, info.unknown_1ch,
            info.structure_size, tuple(info.entries))


class MetaModelCodec:
    """Internal binding for a known model; converters establish its constructor invariants.

    Snapshots schema layout and bindings. Complex references share the META resolver.
    Bind a root or an explicit child array, never all occurrences of a type in an inspection graph.
    """

    def __init__(self, info: MetaStructInfo, model_type: type, *,
                 converters: Mapping[str, Any], attributes: Mapping[str, str] | None = None,
                 array_items: Mapping[str, Any] | None = None,
                 array_codecs: Mapping[str, dict[int, 'MetaModelCodec']] | None = None):
        attributes = attributes or {}
        array_items = array_items or {}
        array_codecs = array_codecs or {}
        def attribute(name):
            return attributes.get(name, camel_to_snake(name))
        scalars, complex_fields = scalar_plan(info.structure_size, tuple(info.entries))
        complex_indices = {index for index, _, _ in complex_fields}
        bindings = [(attribute(entry.name), converters.get(entry.name)) for index, entry in enumerate(info.entries)
                    if entry.name_hash != META_TYPE_NAME_ARRAYINFO and index not in complex_indices]
        self._layout = _layout(info)
        complex_bindings = []
        references = []
        opaque_fields = False
        for index, entry, name in complex_fields:
            convert = converters.get(name)
            # Packed inline float arrays also carry nominal vectors in some schemas.
            if isinstance(convert, tuple):
                convert = convert[0].from_iterable
            complex_bindings.append((index, entry, attribute(name), convert, array_items.get(name), array_codecs.get(name)))
            if entry.data_type is MetaDataType.ARRAY:
                array_info = array_info_for_field(info, index)
                element_type = int(array_info.data_type) if array_info is not None and array_info.data_type in _ARRAY_SCALARS and convert is None else 0
                references.append((attribute(name), entry.data_offset, int(entry.data_type), element_type,
                                   array_items.get(name) if element_type else None))
            elif entry.data_type is MetaDataType.CHAR_POINTER and convert is None:
                references.append((attribute(name), entry.data_offset, int(entry.data_type), 0, None))
            else:
                opaque_fields = True
        self._complex = tuple(complex_bindings)
        self._plan = _native_abi3.meta_model_new(scalars, model_type, bindings, references, opaque_fields)

    def matches(self, info: MetaStructInfo) -> bool:
        return _layout(info) == self._layout

    def read(self, reader, info: MetaStructInfo, raw: bytes):
        model = _native_abi3.meta_model_read(self._plan, raw, reader._data_buffers)
        return self.complete(reader, info, model, raw)

    def complete(self, reader, info: MetaStructInfo, model, raw: bytes):
        for index, entry, attribute, convert, convert_item, codecs in self._complex:
            if hasattr(model, attribute):
                continue
            value = reader._decode_field(info, index, entry, raw, codecs=codecs)
            if convert_item is not None:
                # Empty decoded arrays are already fresh owned lists.
                if value:
                    value = [convert_item(item) for item in value]
            elif convert is not None:
                value = convert(value)
            setattr(model, attribute, value)
        return model
