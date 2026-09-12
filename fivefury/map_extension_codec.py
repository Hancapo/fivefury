"""Bindings for known extension models, shared by their owning map formats."""

from functools import lru_cache, partial
from typing import get_origin

from .colors import parse_css_rgb
from .map_extensions import KNOWN_EXTENSION_TYPES, LightAttrDef
from .meta.backed import _VALUE_TYPES, _model_annotations, _model_fields, _snake_to_camel
from .meta.defs import meta_name
from .meta.materialize import MetaModelCodec

_decoded_rgb = lru_cache(maxsize=512)(parse_css_rgb)


def extension_model_codecs(schemas, model_types=KNOWN_EXTENSION_TYPES):
    codecs = {}

    def bind(cls):
        name_hash = meta_name(cls.META_NAME)
        if name_hash in codecs:
            return codecs[name_hash]
        attributes, converters, arrays = {}, {}, {}
        hints = _model_annotations(cls)
        for field in _model_fields(cls):
            name = cls.META_FIELD_MAP.get(field.name, _snake_to_camel(field.name))
            attributes[name] = field.name
            annotation = hints[field.name]
            if annotation in _VALUE_TYPES:
                converters[name] = (annotation, tuple(item.name for item in _model_fields(annotation)))
            elif get_origin(annotation) is list:
                converters[name] = partial(cls._deserialize_field, field.name)
            if (item_type := cls.META_LIST_TYPES.get(field.name)) is not None:
                arrays[name] = {meta_name(item_type.META_NAME): bind(item_type)}
        # Preserve the constructor's interpretation of component 1, including byte inputs.
        if cls is LightAttrDef:
            converters.update(colour=_decoded_rgb, volOuterColour=_decoded_rgb)
        codec = MetaModelCodec(schemas[name_hash], cls, converters=converters,
            attributes=attributes, array_codecs=arrays)
        codecs[name_hash] = codec
        return codec

    return {meta_name(cls.META_NAME): bind(cls) for cls in model_types}
