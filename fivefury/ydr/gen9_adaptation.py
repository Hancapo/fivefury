from __future__ import annotations

import dataclasses
from collections.abc import Callable

from .gen9 import ShaderGen9Definition, ShaderGen9Library, load_gen9_shader_library
from .gen9_shader_enums import YdrGen9Shader
from .shader_enums import YdrShader
from .shaders import (
    ShaderDefinition,
    ShaderLibrary,
    load_shader_library,
    resolve_shader_reference,
)


@dataclasses.dataclass(slots=True, frozen=True)
class Gen9ShaderAdaptation:
    legacy_definition: ShaderDefinition
    legacy_file_name: str
    gen9_definition: ShaderGen9Definition
    render_bucket: int


def adapt_shader_to_gen9(
    shader: str | YdrShader | YdrGen9Shader,
    render_bucket: int = 0,
    *,
    layout_shader: str | YdrShader | None = None,
    gen9_definition: ShaderGen9Definition | None = None,
    shader_library: ShaderLibrary | None = None,
    gen9_library: ShaderGen9Library | None = None,
    resolve_shader: Callable = resolve_shader_reference,
) -> Gen9ShaderAdaptation:
    """Resolve a public shader reference to its Legacy layout and native Gen9 shader."""
    legacy_library = shader_library or load_shader_library()
    enhanced_library = gen9_library or load_gen9_shader_library()

    legacy_definition: ShaderDefinition | None = None
    legacy_file_name = ""
    resolved_render_bucket = int(render_bucket)
    legacy_error: Exception | None = None
    for candidate in (layout_shader, shader):
        if candidate is None:
            continue
        try:
            legacy_definition, legacy_file_name, resolved_render_bucket = resolve_shader(
                candidate,
                int(render_bucket),
                legacy_library,
            )
            break
        except (TypeError, ValueError) as exc:
            legacy_error = exc

    resolved_gen9 = gen9_definition
    if resolved_gen9 is None:
        candidates = [shader]
        if legacy_definition is not None:
            candidates.extend((legacy_definition.name, legacy_file_name))
        for candidate in candidates:
            resolved_gen9 = enhanced_library.get_shader(candidate)
            if resolved_gen9 is not None:
                break
    if resolved_gen9 is None:
        raise ValueError(f"Unknown YDR Gen9 shader adaptation for '{shader}'")

    if legacy_definition is None:
        for candidate in (layout_shader, resolved_gen9.file_name, resolved_gen9.name):
            if candidate is None:
                continue
            try:
                legacy_definition, legacy_file_name, resolved_render_bucket = resolve_shader(
                    candidate,
                    int(render_bucket),
                    legacy_library,
                )
                break
            except (TypeError, ValueError) as exc:
                legacy_error = exc
    if legacy_definition is None:
        if legacy_error is not None:
            raise ValueError(
                f"Unable to resolve a Legacy vertex layout for Gen9 shader '{resolved_gen9.file_name}'"
            ) from legacy_error
        raise ValueError(f"Unable to resolve a Legacy vertex layout for Gen9 shader '{resolved_gen9.file_name}'")

    return Gen9ShaderAdaptation(
        legacy_definition=legacy_definition,
        legacy_file_name=legacy_file_name,
        gen9_definition=resolved_gen9,
        render_bucket=int(resolved_render_bucket),
    )


__all__ = ["Gen9ShaderAdaptation", "adapt_shader_to_gen9"]
